"""The app's own 12-month price range, long-term intrinsic value, confidence and the model details."""

from __future__ import annotations

from engine.report.context import ReportContext
from engine.report.metric import metric, section
from engine.valuation.engine import value


def compute(ctx: ReportContext, include_analysts: bool | None = None) -> dict:
    key = "_valuation" if include_analysts is None else f"_valuation_{include_analysts}"
    return ctx.section(key, lambda c: value(c, include_analysts))


def build(ctx: ReportContext) -> dict:
    v = compute(ctx)
    if v.get("status") != "ok":
        return section("valuation", status="missing", reason=v.get("reason", "valuation unavailable"))
    t = v["target"]
    p0 = v["price"]
    src = "app valuation engine (model estimate)"
    asof = ctx.last_price_date
    wacc = v["wacc"]
    conf = v["confidence"]
    explain = (
        f"Model estimate for 12 months: median ${t['p50']:,.2f} (80% range ${t['p10']:,.2f}–${t['p90']:,.2f}), "
        f"{t['implied_return']:+.1%} from ${p0:,.2f}. Blend of {len(v['blend'])} methods; confidence {conf['level'].lower()}."
    )
    return section(
        "valuation",
        **v,
        target_explain=explain,
        metrics={
            "p50": metric(
                "target_p50", "App 12-month target (P50)", t["p50"], "usd_per_share", source=src, as_of=asof
            ),
            "p10": metric(
                "target_p10",
                "P10 (pessimistic end of the 80% range)",
                t["p10"],
                "usd_per_share",
                source=src,
                as_of=asof,
            ),
            "p90": metric(
                "target_p90",
                "P90 (optimistic end of the 80% range)",
                t["p90"],
                "usd_per_share",
                source=src,
                as_of=asof,
            ),
            "implied_return": metric(
                "implied_return", "Implied return to P50", t["implied_return"], "pct", source=src, as_of=asof
            ),
            "expected_return": metric(
                "expected_return",
                "Expected return (mean of the distribution)",
                t["expected_return"],
                "pct",
                source=src,
                as_of=asof,
            ),
            "prob_up": metric(
                "prob_up",
                "Probability price is higher in 12 months",
                t["prob_up"],
                "prob",
                source=src,
                as_of=asof,
            ),
            "prob_drawdown_20": metric(
                "prob_drawdown_20",
                "Probability of a ≥20% drawdown along the way",
                t["prob_drawdown_20"],
                "prob",
                source=src,
                as_of=asof,
            ),
            "intrinsic": metric(
                "intrinsic_value",
                "Long-term intrinsic value estimate",
                v["intrinsic"],
                "usd_per_share",
                source=src,
                as_of=asof,
                reason="no intrinsic-value method applied",
            ),
            "wacc": metric("wacc", "WACC", wacc["value"], "pct", source=src, as_of=asof),
            "cost_of_equity": metric(
                "cost_of_equity",
                "Cost of equity",
                wacc["cost_of_equity"],
                "pct",
                source=wacc["risk_free_source"],
                as_of=asof,
            ),
            "confidence": metric("confidence", "Confidence", conf["score"], "score", source=src, as_of=asof),
        },
        disclaimer="The app's target is a model estimate for education only, not investment advice. It can be wrong.",
        sources=[
            {"name": k, **ctx.sources[k]}
            for k in ("prices", "fundamentals", "macro", "estimates", "universe")
            if k in ctx.sources
        ],
    )
