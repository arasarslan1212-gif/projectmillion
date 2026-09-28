"""Explain: the reasoning behind the report, backed by the facts JSON, in Plain and Analyst modes.

Structure (spec §4.15): the view in three sentences; how the numbers led here (pillars → Trust Rating, methods →
target); bear/base/bull cases; what the market is pricing in; key drivers; the case against the app's view; what would
change the view; why confidence is what it is; data gaps. Plus the header Verdict.
"""

from __future__ import annotations

import logging

from engine.explain import narrative, templates
from engine.explain.facts import build_facts
from engine.explain.triggers import build_triggers
from engine.legal import DISCLAIMER_SHORT
from engine.llm.client import llm_available, report_budget, report_id
from engine.report.context import ReportContext
from engine.report.metric import section
from engine.settings import get_settings

log = logging.getLogger("engine.explain")

INPUTS = ("company", "trust", "valuation", "analysts", "news", "risk", "earnings", "dividends", "ownership")


def _section_any(ctx: ReportContext, name: str) -> dict | None:
    """A section's output whatever its status (Explain reports partial and not-applicable sections as such)."""
    from engine.report.builder import _REGISTRY, _ensure_registered

    _ensure_registered()
    fn = _REGISTRY.get(name)
    try:
        return ctx.section(name, fn) if fn else None
    except Exception:
        log.exception("explain: section %s failed", name)
        return None


def build(ctx: ReportContext) -> dict:
    secs = {name: _section_any(ctx, name) for name in INPUTS}
    F = build_facts(ctx, secs)
    triggers = build_triggers(ctx, F, secs)
    T = {
        "verdict": templates.verdict(F),
        "view": templates.view(F),
        "trust_path": templates.trust_path(F, secs.get("trust")),
        "target_path": templates.target_path(F, secs.get("valuation")),
        "pricing_in": templates.pricing_in(F),
        "drivers": templates.drivers(F),
        "against": templates.against(F),
        "confidence": templates.confidence(F),
    }
    cases = templates.cases(F)
    gaps = templates.gaps(F)

    # templates must pass the same fact check as model text; a failure here is a bug, logged loudly
    template_problems = []
    for name, part in T.items():
        for mode in ("plain", "analyst"):
            for i, s in enumerate(part.get(mode) or []):
                template_problems += [f"{name}.{mode}[{i}]: {p}" for p in narrative.check_sentence(s, F)]
    for c in cases:
        for mode in ("plain", "analyst"):
            for s in c[mode]:
                template_problems += [f"case.{c['name']}.{mode}: {p}" for p in narrative.check_sentence(s, F)]
    for tr in triggers:
        for mode in ("plain", "analyst"):
            s = {"text": tr[mode], "facts": tr["facts"]}
            template_problems += [f"trigger.{tr['id']}.{mode}: {p}" for p in narrative.check_sentence(s, F)]
    if template_problems:
        log.error("template narratives failed validation for %s: %s", ctx.ticker, template_problems[:5])

    parts = {k: dict(v, written_by="template") for k, v in T.items()}
    validation = {"checked": 0, "failed_first": 0, "regenerated": [], "fallback": [], "problems": [],
                  "template_problems": template_problems}  # fmt: skip
    cost = None
    model = get_settings().reasoning_model
    if llm_available():
        llm_parts, summary, calls = narrative.write(
            F, T, model=model, ticker=ctx.ticker, report_id=report_id(ctx), budget=report_budget(ctx)
        )
        for k, v in llm_parts.items():
            parts[k] = dict(parts[k], plain=v["plain"], analyst=v["analyst"], written_by=v["written_by"])
        validation.update({k: v for k, v in summary.items() if k != "template_problems"})
        paid = [c for c in calls if not c.cached and (c.input_tokens or c.output_tokens)]
        cost = {"calls": len(paid), "usd": round(sum(c.cost_usd for c in paid), 6),
                "errors": sorted({c.error for c in calls if c.error})}  # fmt: skip
    writers = {p["written_by"] for p in parts.values()}
    method = "template" if writers == {"template"} else "llm" if "template" not in writers else "mixed"
    return section(
        "explain",
        status="ok" if F.has("val.p50") or F.has("trust.score") else "partial",
        reason=None
        if F.has("val.p50")
        else "valuation unavailable; the explanation covers what could be computed",
        method=method,
        method_note={
            "template": "Written from templates: every number comes from the facts below. Set ANTHROPIC_API_KEY for "
            f"model-written text ({model}), which is checked against the same facts.",
            "llm": f"Written by {model} from the facts below; every number was checked against the facts it cites.",
            "mixed": f"Written by {model}; parts that failed the fact check fell back to templates.",
        }[method],
        verdict=parts["verdict"],
        parts=parts,
        cases=cases,
        triggers=triggers,
        gaps=gaps,
        facts=F.to_list(),
        validation=validation,
        cost=cost,
        disclaimer=DISCLAIMER_SHORT,
        sources=[{"name": "app facts (every section of this report)", "as_of": ctx.as_of.isoformat()}],
    )
