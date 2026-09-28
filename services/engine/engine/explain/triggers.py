"""'What would change the view': specific, measurable triggers with thresholds computed in code.

Thresholds come from the company's own history (for example two standard deviations below its recent margin) or
from the app's outputs (the P10/P90 band, the price). The LLM never sets a threshold; it may only rephrase these.
"""

from __future__ import annotations

import numpy as np

from engine.explain.facts import Facts, fmt
from engine.report.context import ReportContext


def _quarterly(ctx: ReportContext, key: str, denom: str | None = None, n: int = 12) -> list[float]:
    out = []
    for p in ctx.fin.quarterly[-n:]:
        v = p.get(key)
        d = p.get(denom) if denom else 1.0
        if v is not None and d:
            out.append(v / d)
    return out


def _yoy_growth(ctx: ReportContext, n: int = 12) -> list[float]:
    q = ctx.fin.quarterly
    out = []
    for i in range(max(4, len(q) - n), len(q)):
        a, b = q[i].get("revenue"), q[i - 4].get("revenue")
        if a and b:
            out.append(a / b - 1)
    return out


def build_triggers(ctx: ReportContext, F: Facts, sections: dict) -> list[dict]:
    trig: list[dict] = []

    def add(tid, text_plain, text_analyst, facts: dict[str, tuple], effect: str):
        for fid, (label, value, unit) in facts.items():
            F.add(f"trigger.{tid}.{fid}", label, value, unit, "triggers")
        trig.append({
            "id": tid,
            "plain": text_plain,
            "analyst": text_analyst,
            "effect": effect,
            "facts": [f"trigger.{tid}.{fid}" for fid in facts],
        })  # fmt: skip

    # 1. price leaves the model's 80% band
    if F.has("val.p10", "val.p90"):
        p10, p90 = F.get("val.p10"), F.get("val.p90")
        add(
            "band",
            f"The price closing above {fmt(p90, 'usd_per_share')} or below {fmt(p10, 'usd_per_share')} would mean "
            "the stock has moved outside the range the app expected.",
            f"A close above P90 ({fmt(p90, 'usd_per_share')}) or below P10 ({fmt(p10, 'usd_per_share')}) before the "
            "12-month horizon would put the price outside the model's 80% band and prompt a re-check of its inputs.",
            {"p90": ("P90", p90, "usd_per_share"), "p10": ("P10", p10, "usd_per_share")},
            "the model's range would have been wrong so far; the inputs behind it deserve a fresh look",
        )
        trig[-1]["facts"] += ["val.range_coverage", "val.horizon_months"]

    # 2. operating margin breaks below its recent range (not for banks/insurers)
    if not ctx.sector.is_financial:
        om = _quarterly(ctx, "operating_income", "revenue")
        if len(om) >= 8:
            mu, sd = float(np.mean(om)), float(np.std(om, ddof=1))
            thr = mu - 2 * max(sd, 0.01)
            add(
                "margin",
                f"Operating margin falling below {fmt(thr, 'pct')} for two quarters in a row (it has averaged "
                f"{fmt(mu, 'pct')} recently) would suggest the business is weakening.",
                f"Quarterly operating margin below {fmt(thr, 'pct')} for two consecutive quarters, two standard "
                f"deviations under its {len(om)}-quarter mean of {fmt(mu, 'pct')}, would lower the profitability "
                "pillar and the DCF margin path.",
                {
                    "threshold": ("Operating margin trigger", thr, "pct"),
                    "mean": ("Recent average operating margin", mu, "pct"),
                    "quarters": ("Quarters in the margin history", len(om), "count"),
                },  # fmt: skip
                "lower Trust Rating (profitability) and a lower DCF value",
            )

    # 3. revenue growth stalls
    g = _yoy_growth(ctx)
    has_dcf = F.has("val.dcf.years")
    if len(g) >= 6:
        mu, sd = float(np.mean(g)), float(np.std(g, ddof=1))
        thr = min(mu - 2 * max(sd, 0.01), 0.0) if mu > 0 else mu - 2 * max(sd, 0.01)
        add(
            "growth",
            f"{'Sales' if not ctx.sector.is_financial else 'Revenue'} growth dropping below {fmt(thr, 'pct')} compared "
            "with a year earlier, two quarters in a row, would undercut the growth the app assumes.",
            f"Year-over-year revenue growth below {fmt(thr, 'pct')} for two consecutive quarters (recent mean "
            f"{fmt(mu, 'pct')}) would cut the growth pillar"
            + (" and the near-term growth input to the DCF." if has_dcf else "."),
            {
                "threshold": ("Revenue growth trigger", thr, "pct"),
                "mean": ("Recent average revenue growth", mu, "pct"),
            },
            "lower growth pillar and a lower DCF value" if has_dcf else "lower growth pillar",
        )

    # 4. leverage
    if not ctx.sector.is_financial:
        nd, eb = ctx.fin.ttm.get("net_debt"), ctx.fin.ttm.get("ebitda")
        if eb and eb > 0 and nd is not None:
            cur = nd / eb
            thr = max(3.0, cur + 1.5)
            add(
                "leverage",
                f"Debt rising to more than {fmt(thr, 'x')} yearly operating cash earnings "
                + ("(today it holds more cash than debt)" if cur < 0 else f"(now {fmt(cur, 'x')})")
                + " would make the company more fragile.",
                f"Net debt ÷ EBITDA above {fmt(thr, 'x')} (currently {fmt(cur, 'x')}"
                + (", a net cash position" if cur < 0 else "")
                + ") would weaken the financial health pillar and raise the cost of debt.",
                {
                    "threshold": ("Leverage trigger (net debt ÷ EBITDA)", thr, "x"),
                    "current": ("Net debt ÷ EBITDA", cur, "x"),
                },
                "lower financial health score and a higher discount rate",
            )

    # 5. the better analysts turn
    a = sections.get("analysts") or {}
    if a.get("consensus_trusted") and ctx.last_price:
        tc, p0 = a["consensus_trusted"], ctx.last_price
        side = "below" if tc > p0 else "above"
        add(
            "analysts",
            f"The analysts with the best records moving their average target {side} today's price of "
            f"{fmt(p0, 'usd_per_share')} (it is {fmt(tc, 'usd_per_share')} now) would flip their signal.",
            f"The trusted consensus crossing {side} {fmt(p0, 'usd_per_share')} (now {fmt(tc, 'usd_per_share')}) would "
            "reverse the analyst input to the blend and the analyst pillar.",
            {
                "price": ("Price at report date", p0, "usd_per_share"),
                "consensus": ("Trusted consensus", tc, "usd_per_share"),
            },
            "the analyst method in the blend would pull the target the other way",
        )

    # 6. news tone
    n = sections.get("news") or {}
    s30 = n.get("sentiment_30d")
    if s30 is not None:
        thr = -0.3 if s30 > -0.3 else 0.1
        word = "below" if thr < 0 else "back above"
        add(
            "news",
            f"The tone of news coverage falling {word} {fmt(thr, 'ratio', 1)} on the app's −1 to +1 scale "
            f"(now {fmt(s30, 'ratio')}) would change the sentiment input.",
            f"30-day weighted news sentiment {word} {fmt(thr, 'ratio', 1)} (now {fmt(s30, 'ratio')}) would move the "
            "sentiment pillar.",
            {
                "threshold": ("News sentiment trigger", thr, "ratio"),
                "current": ("News sentiment, 30 days", s30, "ratio"),
            },
            "the sentiment pillar would move",
        )
    return trig
