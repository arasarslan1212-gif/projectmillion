"""Accounting-based scores: Altman Z (right variant per company type), Piotroski F, Beneish M, accruals.

References:
- Altman (1968) Z = 1.2·X1 + 1.4·X2 + 3.3·X3 + 0.6·X4 + 1.0·X5 (public manufacturers);
  zones: > 2.99 safe, 1.81–2.99 grey, < 1.81 distress.
- Altman Z'' (1995, non-manufacturers/services) = 6.56·X1 + 3.26·X2 + 6.72·X3 + 1.05·X4 (book equity);
  zones: > 2.60 safe, 1.10–2.60 grey, < 1.10 distress.
- Piotroski (2000) F-score: nine binary signals on profitability, leverage/liquidity and efficiency.
- Beneish (1999) eight-variable M-score; values above −1.78 suggest a higher likelihood of manipulation.
- Sloan (1996) accruals: (net income − operating cash flow) ÷ average total assets.
None of these apply to banks, insurers or REITs; callers mark them "not applicable".
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine.fundamentals.ratios import avg, div
from engine.fundamentals.statements import Period


@dataclass
class Score:
    value: float | None
    variant: str | None = None
    zone: str | None = None
    components: dict[str, float | None] = field(default_factory=dict)
    note: str | None = None
    reason: str | None = None


def altman_z(p: Period, market_cap: float | None, manufacturer: bool) -> Score:
    v = p.values
    ta, tl = v.get("total_assets"), v.get("total_liabilities")
    wc = v.get("working_capital")
    re_ = v.get("retained_earnings")
    ebit = v.get("ebit")
    sales = v.get("revenue")
    if not ta or ta <= 0 or tl is None or tl <= 0 or wc is None or re_ is None or ebit is None:
        return Score(None, reason="missing working capital, retained earnings, EBIT, assets or liabilities")
    x1, x2, x3 = wc / ta, re_ / ta, ebit / ta
    if manufacturer:
        if market_cap is None or sales is None:
            return Score(None, reason="needs market value of equity and sales")
        x4, x5 = market_cap / tl, sales / ta
        z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
        zone = "safe" if z > 2.99 else "grey" if z >= 1.81 else "distress"
        return Score(z, "Altman Z (manufacturers)", zone, {"X1": x1, "X2": x2, "X3": x3, "X4": x4, "X5": x5})
    eq = v.get("equity")
    if eq is None:
        return Score(None, reason="needs book equity")
    x4 = eq / tl
    z = 6.56 * x1 + 3.26 * x2 + 6.72 * x3 + 1.05 * x4
    zone = "safe" if z > 2.60 else "grey" if z >= 1.10 else "distress"
    return Score(z, "Altman Z'' (non-manufacturers)", zone, {"X1": x1, "X2": x2, "X3": x3, "X4": x4})


def piotroski_f(cur: Period, prev: Period, prev2: Period | None) -> Score:
    c, p = cur.values, prev.values
    p2 = prev2.values if prev2 else {}
    needed = ("net_income", "cfo", "total_assets", "revenue")
    if any(c.get(k) is None for k in needed) or any(p.get(k) is None for k in needed):
        return Score(None, reason="needs two fiscal years of income, cash flow and assets")
    begin_c = p.get("total_assets")
    begin_p = p2.get("total_assets") or p.get("total_assets")
    roa_c = div(c["net_income"], begin_c)
    roa_p = div(p["net_income"], begin_p)
    signals: dict[str, float | None] = {}
    signals["roa_positive"] = 1.0 if (roa_c or 0) > 0 else 0.0
    signals["cfo_positive"] = 1.0 if c["cfo"] > 0 else 0.0
    signals["roa_improving"] = 1.0 if (roa_c is not None and roa_p is not None and roa_c > roa_p) else 0.0
    signals["cfo_exceeds_ni"] = 1.0 if c["cfo"] > c["net_income"] else 0.0
    ltd_c = div(c.get("debt_noncurrent", c.get("total_debt", 0.0)), avg(c["total_assets"], begin_c))
    ltd_p = div(p.get("debt_noncurrent", p.get("total_debt", 0.0)), avg(p["total_assets"], begin_p))
    signals["leverage_falling"] = 1.0 if (ltd_c is not None and ltd_p is not None and ltd_c <= ltd_p) else 0.0
    cr_c, cr_p = (
        div(c.get("current_assets"), c.get("current_liabilities")),
        div(p.get("current_assets"), p.get("current_liabilities")),
    )
    signals["liquidity_improving"] = 1.0 if (cr_c is not None and cr_p is not None and cr_c > cr_p) else 0.0
    sh_c, sh_p = c.get("shares_diluted"), p.get("shares_diluted")
    signals["no_dilution"] = 1.0 if (sh_c is not None and sh_p is not None and sh_c <= sh_p * 1.005) else 0.0
    gm_c, gm_p = div(c.get("gross_profit"), c["revenue"]), div(p.get("gross_profit"), p["revenue"])
    signals["margin_improving"] = 1.0 if (gm_c is not None and gm_p is not None and gm_c > gm_p) else 0.0
    at_c, at_p = div(c["revenue"], begin_c), div(p["revenue"], begin_p)
    signals["turnover_improving"] = 1.0 if (at_c is not None and at_p is not None and at_c > at_p) else 0.0
    missing = [
        k
        for k, (a, b) in {"gross margin": (gm_c, gm_p), "current ratio": (cr_c, cr_p)}.items()
        if a is None or b is None
    ]
    note = f"Signals without data scored 0: {', '.join(missing)}." if missing else None
    return Score(sum(v for v in signals.values() if v is not None), "Piotroski F (0–9)", None, signals, note)


def beneish_m(cur: Period, prev: Period) -> Score:
    c, p = cur.values, prev.values
    try:
        sales_c, sales_p = c["revenue"], p["revenue"]
        rec_c, rec_p = c["receivables"], p["receivables"]
        ta_c, ta_p = c["total_assets"], p["total_assets"]
        ni, cfo = c["net_income"], c["cfo"]
    except KeyError:
        return Score(
            None, reason="needs revenue, receivables, total assets, net income and cash flow for two years"
        )
    if min(sales_c, sales_p, ta_c, ta_p) <= 0 or rec_p <= 0:
        return Score(None, reason="non-positive revenue, receivables or assets")
    notes = []
    dsri = (rec_c / sales_c) / (rec_p / sales_p)
    gm_c, gm_p = div(c.get("gross_profit"), sales_c), div(p.get("gross_profit"), sales_p)
    if gm_c and gm_p and gm_c > 0:
        gmi = gm_p / gm_c
    else:
        gmi = 1.0
        notes.append("GMI set to 1 (gross margin unavailable)")

    def aq(v: dict, ta: float) -> float | None:
        if v.get("current_assets") is None or v.get("ppe") is None:
            return None
        return 1 - (v["current_assets"] + v["ppe"]) / ta

    aq_c, aq_p = aq(c, ta_c), aq(p, ta_p)
    if aq_c is not None and aq_p and aq_p > 0:
        aqi = aq_c / aq_p
    else:
        aqi = 1.0
        notes.append("AQI set to 1")
    sgi = sales_c / sales_p
    dep_c, dep_p, ppe_c, ppe_p = c.get("dna"), p.get("dna"), c.get("ppe"), p.get("ppe")
    if dep_c and dep_p and ppe_c and ppe_p:
        depi = (dep_p / (dep_p + ppe_p)) / (dep_c / (dep_c + ppe_c))
    else:
        depi = 1.0
        notes.append("DEPI set to 1")
    sga_c, sga_p = c.get("sga"), p.get("sga")
    if sga_c and sga_p:
        sgai = (sga_c / sales_c) / (sga_p / sales_p)
    else:
        sgai = 1.0
        notes.append("SGAI set to 1")
    tata = (ni - cfo) / ta_c

    def lev(v: dict, ta: float) -> float | None:
        if v.get("current_liabilities") is None:
            return None
        return (v["current_liabilities"] + v.get("debt_noncurrent", 0.0)) / ta

    lv_c, lv_p = lev(c, ta_c), lev(p, ta_p)
    lvgi = lv_c / lv_p if (lv_c is not None and lv_p) else 1.0
    if lv_c is None or not lv_p:
        notes.append("LVGI set to 1")
    m = (
        -4.84
        + 0.920 * dsri
        + 0.528 * gmi
        + 0.404 * aqi
        + 0.892 * sgi
        + 0.115 * depi
        - 0.172 * sgai
        + 4.679 * tata
        - 0.327 * lvgi
    )
    zone = "likely manipulator" if m > -1.78 else "unlikely"
    comps = {
        "DSRI": dsri,
        "GMI": gmi,
        "AQI": aqi,
        "SGI": sgi,
        "DEPI": depi,
        "SGAI": sgai,
        "TATA": tata,
        "LVGI": lvgi,
    }
    return Score(m, "Beneish M (8-variable)", zone, comps, "; ".join(notes) or None)


def accruals_ratio(cur: Period, prev: Period | None) -> float | None:
    c = cur.values
    if c.get("net_income") is None or c.get("cfo") is None:
        return None
    aa = avg(c.get("total_assets"), prev.values.get("total_assets") if prev else None)
    return div(c["net_income"] - c["cfo"], aa)
