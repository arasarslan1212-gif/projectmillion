"""The three headline badges plus the consensus pair, for the sticky header."""

from __future__ import annotations

from engine.analysis.trust_rating import _safe_section
from engine.report.context import ReportContext
from engine.report.metric import section


def build(ctx: ReportContext) -> dict:
    t = _safe_section(ctx, "trust")
    trust = None
    if t:
        trust = {
            "score": t["score"],
            "grade": t["grade"],
            "coverage": t["coverage"],
            "explain": (
                f"Trust Rating {t['score']:.0f}/100 ({t['grade']}): business strength, reliability and valuation relative to the sector, "
                f"from {sum(1 for p in t['pillars'] if p['score'] is not None)} of {len(t['pillars'])} pillars. Not a buy/sell recommendation."
                if t["score"] is not None
                else "Insufficient data to compute a Trust Rating."
            ),
        }
    v = _safe_section(ctx, "valuation")
    target = conf = None
    if v:
        tg = v.get("target") or {}
        target = {
            "p10": tg.get("p10"),
            "p50": tg.get("p50"),
            "p90": tg.get("p90"),
            "implied_return": tg.get("implied_return"),
            "explain": v.get("target_explain", "The app's 12-month price range (model estimate)."),
        }
        c = v.get("confidence") or {}
        conf = {"score": c.get("score"), "level": c.get("level"), "explain": c.get("explain", "")}
    a = _safe_section(ctx, "analysts")
    cons = None
    if a:
        cons = {
            "all": a.get("consensus_all"),
            "trusted": a.get("consensus_trusted"),
            "explain": a.get("consensus_explain", ""),
        }
    missing = {
        k: why
        for k, why in (
            ("valuation", None if v else "valuation not available"),
            ("analysts", None if a else "analyst data not available"),
        )
        if why
    }
    return section("headline", trust=trust, target=target, confidence=conf, consensus=cons, missing=missing)
