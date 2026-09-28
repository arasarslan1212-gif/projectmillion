"""Financial ratios, growth rates, quality metrics and sector KPIs from point-in-time statements.

All functions return None when inputs are missing or not meaningful (e.g. a margin on zero revenue,
a CAGR across a sign change). Callers turn None into an "insufficient data" metric with a reason.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from engine.fundamentals.statements import Financials, Period


def div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    r = a / b
    return None if math.isnan(r) or math.isinf(r) else r


def avg(a: float | None, b: float | None) -> float | None:
    if a is None:
        return b
    if b is None:
        return a
    return (a + b) / 2


def cagr(first: float | None, last: float | None, years: float) -> float | None:
    """Compound annual growth rate. Undefined when either end is non-positive or years <= 0."""
    if first is None or last is None or years <= 0 or first <= 0 or last <= 0:
        return None
    return (last / first) ** (1 / years) - 1


def yoy(cur: float | None, prev: float | None) -> float | None:
    """Year-over-year change; uses |prev| so a smaller loss reads as an improvement."""
    if cur is None or prev is None or prev == 0:
        return None
    return (cur - prev) / abs(prev)


def series_cagr(points: list[tuple], years: int) -> float | None:
    """CAGR over the last `years` years of an annual (date, value) series."""
    if len(points) < years + 1:
        return None
    first_d, first_v = points[-(years + 1)]
    last_d, last_v = points[-1]
    span = (last_d - first_d).days / 365.25
    return cagr(first_v, last_v, round(span)) if span > 0 else None


def tax_rate(p: Period) -> float | None:
    t = div(p.get("income_tax"), p.get("pretax_income"))
    if t is None or p.get("pretax_income", 0) <= 0:
        return None
    return min(max(t, 0.0), 0.5)


@dataclass
class RatioSet:
    values: dict[str, float | None]


RATIO_KEYS = [
    "gross_margin",
    "operating_margin",
    "net_margin",
    "ebitda_margin",
    "fcf_margin",
    "roe",
    "roa",
    "roic",
    "rotce",
    "debt_to_equity",
    "net_debt_to_ebitda",
    "interest_coverage",
    "debt_to_assets",
    "equity_to_assets",
    "current_ratio",
    "quick_ratio",
    "asset_turnover",
    "dso",
    "dio",
    "dpo",
    "ccc",
    "fcf_conversion",
    "sbc_pct_revenue",
    "capex_intensity",
    "nwc_pct_revenue",
    "effective_tax_rate",
    "nim",
    "efficiency_ratio",
    "loan_to_deposit",
    "combined_ratio",
    "ffo",
    "affo",
    "ffo_margin",
]


def period_ratios(p: Period, prev: Period | None, annualize: float = 1.0) -> dict[str, float | None]:
    """Ratios for one period. `prev` supplies opening balances for averages.

    `annualize` scales flow-based return ratios for quarters (×4) so they read as annual rates.
    """
    v = p.values
    pv = prev.values if prev else {}
    rev = v.get("revenue")
    out: dict[str, float | None] = {}
    out["gross_margin"] = div(v.get("gross_profit"), rev)
    out["operating_margin"] = div(v.get("operating_income"), rev)
    out["net_margin"] = div(v.get("net_income"), rev)
    out["ebitda_margin"] = div(v.get("ebitda"), rev)
    out["fcf_margin"] = div(v.get("fcf"), rev)

    eq_avg = avg(v.get("equity"), pv.get("equity"))
    assets_avg = avg(v.get("total_assets"), pv.get("total_assets"))
    ni = v.get("net_income")
    out["roe"] = div(ni * annualize, eq_avg) if (ni is not None and eq_avg and eq_avg > 0) else None
    out["roa"] = div(ni * annualize, assets_avg) if ni is not None else None
    t = tax_rate(p)
    ebit = v.get("ebit")
    nopat = ebit * (1 - (t if t is not None else 0.21)) if ebit is not None else None
    ic_avg = avg(v.get("invested_capital"), pv.get("invested_capital"))
    out["roic"] = div(nopat * annualize, ic_avg) if (nopat is not None and ic_avg and ic_avg > 0) else None
    te_avg = avg(v.get("tangible_equity"), pv.get("tangible_equity"))
    out["rotce"] = div(ni * annualize, te_avg) if (ni is not None and te_avg and te_avg > 0) else None

    debt = v.get("total_debt")
    eq = v.get("equity")
    out["debt_to_equity"] = div(debt, eq) if (eq and eq > 0) else None
    ebitda = v.get("ebitda")
    out["net_debt_to_ebitda"] = (
        div(v.get("net_debt"), ebitda * annualize) if (ebitda and ebitda > 0) else None
    )
    ie = v.get("interest_expense")
    out["interest_coverage"] = div(ebit, ie) if (ie and ie > 0 and ebit is not None) else None
    out["debt_to_assets"] = div(debt, v.get("total_assets"))
    out["equity_to_assets"] = div(eq, v.get("total_assets"))
    cl = v.get("current_liabilities")
    out["current_ratio"] = div(v.get("current_assets"), cl)
    quick = None
    if v.get("cash") is not None:
        quick = v.get("cash", 0.0) + v.get("st_investments", 0.0) + v.get("receivables", 0.0)
    out["quick_ratio"] = div(quick, cl)

    days = 365.0 / annualize
    out["asset_turnover"] = div(rev * annualize, assets_avg) if rev is not None else None
    out["dso"] = div(avg(v.get("receivables"), pv.get("receivables")), rev / days) if rev else None
    cogs = v.get("cost_of_revenue")
    out["dio"] = div(avg(v.get("inventory"), pv.get("inventory")), cogs / days) if cogs else None
    out["dpo"] = (
        div(avg(v.get("accounts_payable"), pv.get("accounts_payable")), cogs / days) if cogs else None
    )
    out["ccc"] = (
        (out["dso"] + out["dio"] - out["dpo"]) if None not in (out["dso"], out["dio"], out["dpo"]) else None
    )

    out["fcf_conversion"] = div(v.get("fcf"), ni) if (ni and ni > 0) else None
    out["sbc_pct_revenue"] = div(v.get("sbc"), rev)
    out["capex_intensity"] = div(v.get("capex"), rev)
    out["nwc_pct_revenue"] = div(v.get("working_capital"), rev * annualize) if rev else None
    out["effective_tax_rate"] = t

    # banks
    nii = v.get("net_interest_income")
    out["nim"] = (
        div(nii * annualize, assets_avg) if (nii is not None and v.get("loans") is not None) else None
    )
    nonie = v.get("noninterest_expense")
    rev_bank = (nii or 0) + (v.get("noninterest_income") or 0) if nii is not None else None
    out["efficiency_ratio"] = div(nonie, rev_bank) if nonie is not None else None
    out["loan_to_deposit"] = div(v.get("loans"), v.get("deposits"))
    # insurers
    pe = v.get("premiums_earned")
    if pe and v.get("losses_incurred") is not None:
        out["combined_ratio"] = div(v["losses_incurred"] + v.get("underwriting_expense", 0.0), pe)
    else:
        out["combined_ratio"] = None
    # REITs (NAREIT-style approximation from tagged items)
    if ni is not None and v.get("dna") is not None and v.get("revenue") is not None:
        ffo = ni + v["dna"] - (v.get("gain_on_sale_re") or 0.0)
        out["ffo"] = ffo
        out["affo"] = ffo - (v.get("capex") or 0.0)
        out["ffo_margin"] = div(ffo, rev)
    else:
        out["ffo"] = out["affo"] = out["ffo_margin"] = None
    return out


def ratio_history(fin: Financials) -> tuple[list[dict], list[dict]]:
    """(annual, quarterly) lists of {period, end, ratios}."""
    ann = []
    for i, p in enumerate(fin.annual):
        prev = fin.annual[i - 1] if i > 0 else None
        ann.append({"label": p.label, "end": p.end, "ratios": period_ratios(p, prev, 1.0)})
    qtr = []
    for i, p in enumerate(fin.quarterly):
        prev = fin.quarterly[i - 1] if i > 0 else None
        qtr.append({"label": p.label, "end": p.end, "ratios": period_ratios(p, prev, 4.0)})
    return ann, qtr


def ttm_ratios(fin: Financials) -> dict[str, float | None]:
    """Ratios on trailing-twelve-month flows and the latest balance sheet (opening balance a year earlier)."""
    if not fin.quarterly and not fin.annual:
        return {}
    ttm = Period("FY", fin.ttm_end or fin.as_of, fin.ttm_end or fin.as_of, fin.ttm_end or fin.as_of, None)
    ttm.values = dict(fin.ttm)
    # opening balance: the balance sheet four quarters earlier (or the prior fiscal year end)
    prev = None
    if len(fin.quarterly) >= 5:
        prev = fin.quarterly[-5]
    elif len(fin.annual) >= 2:
        prev = fin.annual[-2]
    return period_ratios(ttm, prev, 1.0)


def growth_metrics(fin: Financials) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for key, name in (
        ("revenue", "revenue"),
        ("eps_diluted", "eps"),
        ("fcf", "fcf"),
        ("net_income", "net_income"),
        ("dps", "dps"),
        ("shares_diluted", "shares"),
    ):
        s = fin.annual_series(key)
        for yrs in (1, 3, 5, 10):
            out[f"{name}_cagr_{yrs}y"] = (
                series_cagr(s, yrs) if yrs > 1 else (yoy(s[-1][1], s[-2][1]) if len(s) >= 2 else None)
            )
    q = fin.quarterly
    if len(q) >= 5:
        out["revenue_yoy_q"] = yoy(q[-1].get("revenue"), q[-5].get("revenue"))
        out["eps_yoy_q"] = yoy(q[-1].get("eps_diluted"), q[-5].get("eps_diluted"))
    return out


def stability(values: list[float]) -> float | None:
    """Standard deviation of a ratio series (lower = more stable)."""
    vals = [x for x in values if x is not None]
    if len(vals) < 4:
        return None
    return float(np.std(vals, ddof=1))


def revenue_growth_stability(fin: Financials, years: int = 8) -> float | None:
    s = fin.annual_series("revenue")[-(years + 1) :]
    g = [yoy(s[i][1], s[i - 1][1]) for i in range(1, len(s))]
    return stability([x for x in g if x is not None])
