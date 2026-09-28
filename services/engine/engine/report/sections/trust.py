"""The app's Trust Rating: pillars, sector percentiles, radar data and the accounting scores behind it."""

from __future__ import annotations

from engine.analysis.red_flags import run_red_flags
from engine.analysis.trust_rating import compute_trust, quality_scores
from engine.report.context import ReportContext
from engine.report.metric import section


def quality(ctx: ReportContext) -> dict:
    return ctx.section("_quality", quality_scores)


def flags(ctx: ReportContext) -> dict:
    return ctx.section("_flags", lambda c: run_red_flags(c, quality(c), c.cfg["red_flags"]))


def trust(ctx: ReportContext) -> dict:
    return ctx.section("_trust", lambda c: compute_trust(c, quality(c), flags(c)))


def build(ctx: ReportContext) -> dict:
    if not ctx.fin.annual and not ctx.fin.quarterly:
        return section("trust", status="missing", reason="no financial statements to rate")
    t = trust(ctx)
    qs = quality(ctx)
    return section(
        "trust",
        **t,
        radar=[{"id": p["id"], "label": p["label"], "score": p["score"]} for p in t["pillars"]],
        accounting_scores={k: v for k, v in qs.items() if k in ("altman", "piotroski", "beneish")},
        flag_counts=flags(ctx)["counts"],
        universe_note=ctx.universe.note
        if ctx.universe
        else "No SEC industry universe: all metrics use anchors.",
        disclaimer="The Trust Rating is the app's model estimate of business strength, reliability and valuation relative to the sector. It is not a recommendation to buy or sell.",
        sources=[
            {"name": k, **v}
            for k, v in ctx.sources.items()
            if k in ("fundamentals", "prices", "universe", "insiders", "short_interest", "earnings")
        ],
    )
