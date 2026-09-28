"""Valuation methods other than the DCF: relative (peers, own history) and sector-specific models.

Each returns a MethodResult with an intrinsic value per share, an applicability weight in [0, 1] (how
well the method fits this company and its data), and the inputs used.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from engine.analysis.multiples_history import band_stats


@dataclass
class MethodResult:
    id: str
    label: str
    value: float | None
    applicability: float
    inputs: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    reason: str | None = None
    kind: str = "intrinsic"  # intrinsic | target (analyst targets are already 12-month prices)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def missing(id_: str, label: str, reason: str) -> MethodResult:
    return MethodResult(id_, label, None, 0.0, reason=reason)


def _per_share_from_ev(ev: float, net_debt: float, minority: float, shares: float) -> float | None:
    if shares <= 0:
        return None
    return max((ev - net_debt - minority) / shares, 0.0)


def relative_peers(ctx, peers: dict | None, profitability_score: float | None, cfg: dict) -> MethodResult:
    label = "Relative to peers"
    if not peers or peers.get("status") != "ok":
        return missing("relative_peers", label, "no peer set")
    med = peers["medians"]
    rows = [r for r in peers["rows"] if not r["is_subject"]]
    if len(rows) < cfg["min_peers"]:
        return missing("relative_peers", label, f"fewer than {cfg['min_peers']} peers")
    fin = ctx.fin
    t = fin.ttm
    shares = t.get("shares_diluted") or ctx.shares_outstanding[0]
    if not shares:
        return missing("relative_peers", label, "no share count")
    nd = t.get("net_debt") or 0.0
    mi = t.get("minority_interest") or 0.0
    subj = peers["rows"][0]["metrics"]
    g, g_med = subj.get("revenue_growth"), med.get("revenue_growth")
    adj = 1.0
    if g is not None and g_med is not None:
        adj *= 1 + cfg["growth_adjustment"] * (g - g_med)
    if profitability_score is not None:
        adj *= 1 + cfg["quality_adjustment"] * (profitability_score - 50) / 100
    lo, hi = cfg["adjustment_bounds"]
    adj = min(max(adj, lo), hi)
    implied: dict[str, float] = {}
    eps = t.get("eps_diluted")
    if med.get("pe") and eps and eps > 0:
        implied["P/E"] = med["pe"] * adj * eps
    ebitda = t.get("ebitda")
    if med.get("ev_ebitda") and ebitda and ebitda > 0 and not ctx.sector.is_financial:
        v = _per_share_from_ev(med["ev_ebitda"] * adj * ebitda, nd, mi, shares)
        if v is not None:
            implied["EV/EBITDA"] = v
    rev = t.get("revenue")
    if med.get("ev_sales") and rev and not ctx.sector.is_financial:
        v = _per_share_from_ev(med["ev_sales"] * adj * rev, nd, mi, shares)
        if v is not None:
            implied["EV/Sales"] = v
    fcf = t.get("fcf")
    if med.get("p_fcf") and fcf and fcf > 0 and not ctx.sector.is_financial:
        implied["P/FCF"] = med["p_fcf"] * adj * fcf / shares
    eq = t.get("equity")
    if ctx.sector.is_financial and med.get("p_b") and eq and eq > 0:
        implied["P/B"] = med["p_b"] * adj * eq / shares
    if not implied:
        return missing(
            "relative_peers",
            label,
            "no positive earnings, EBITDA, sales or book value to apply peer multiples to",
        )
    value = float(np.median(list(implied.values())))
    applic = min(1.0, len(rows) / 5.0) * (0.7 if len(implied) == 1 else 1.0)
    return MethodResult(
        "relative_peers",
        label,
        value,
        applic,
        {
            "implied_by_multiple": implied,
            "adjustment": adj,
            "peer_medians": {k: med.get(k) for k in ("pe", "ev_ebitda", "ev_sales", "p_fcf", "p_b")},
            "n_peers": len(rows),
        },
        [f"Peer median multiples scaled by {adj:.2f} for relative growth and profitability."],
    )


def relative_history(ctx, history: list, cfg: dict) -> MethodResult:
    label = "Relative to own history"
    t = ctx.fin.ttm
    shares = t.get("shares_diluted") or ctx.shares_outstanding[0]
    if not shares:
        return missing("relative_history", label, "no share count")
    nd, mi = t.get("net_debt") or 0.0, t.get("minority_interest") or 0.0
    implied: dict[str, float] = {}
    stats_out = {}
    years = int(cfg["history_years"])
    for key, lbl in (("pe", "P/E"), ("ev_ebitda", "EV/EBITDA"), ("ev_sales", "EV/Sales"), ("p_b", "P/B")):
        st = band_stats(history, key, years, ctx.as_of)
        if not st:
            continue
        stats_out[lbl] = st
        med = st["median"]
        if key == "pe" and (t.get("net_income") or 0) > 0:
            implied[lbl] = med * t["net_income"] / shares
        elif key == "ev_ebitda" and (t.get("ebitda") or 0) > 0 and not ctx.sector.is_financial:
            v = _per_share_from_ev(med * t["ebitda"], nd, mi, shares)
            if v is not None:
                implied[lbl] = v
        elif key == "ev_sales" and t.get("revenue") and not ctx.sector.is_financial:
            v = _per_share_from_ev(med * t["revenue"], nd, mi, shares)
            if v is not None:
                implied[lbl] = v
        elif key == "p_b" and ctx.sector.is_financial and (t.get("equity") or 0) > 0:
            implied[lbl] = med * t["equity"] / shares
    if not implied:
        return missing("relative_history", label, "fewer than 8 quarters of point-in-time multiple history")
    value = float(np.median(list(implied.values())))
    return MethodResult(
        "relative_history",
        label,
        value,
        1.0 if len(implied) > 1 else 0.7,
        {"implied_by_multiple": implied, "history": stats_out, "years": years},
        [f"Median {years}-year multiples (point-in-time) applied to trailing fundamentals."],
    )


def _ols(x: list[float], y: list[float]) -> tuple[float, float, float] | None:
    if len(x) < 5:
        return None
    xa, ya = np.array(x, float), np.array(y, float)
    if np.var(xa) == 0:
        return None
    b = float(np.cov(xa, ya, ddof=1)[0, 1] / np.var(xa, ddof=1))
    a = float(ya.mean() - b * xa.mean())
    r2 = float(np.corrcoef(xa, ya)[0, 1] ** 2)
    return a, b, r2


def pb_roe_regression(ctx, peers: dict | None) -> MethodResult:
    label = "P/B vs. ROE regression (peers)"
    if not peers or peers.get("status") != "ok":
        return missing("pb_roe_regression", label, "no peer set")
    pts = [
        (r["metrics"]["roe"], r["metrics"]["p_b"])
        for r in peers["rows"]
        if not r["is_subject"] and r["metrics"].get("roe") is not None and r["metrics"].get("p_b")
    ]
    fit = _ols([p[0] for p in pts], [p[1] for p in pts])
    t = ctx.fin.ttm
    from engine.fundamentals.ratios import ttm_ratios

    roe = ttm_ratios(ctx.fin).get("roe")
    shares = t.get("shares_diluted")
    if fit is None or roe is None or not t.get("equity") or not shares:
        return missing(
            "pb_roe_regression",
            label,
            "needs at least 5 peers with P/B and ROE, and the company's ROE and book value",
        )
    a, b, r2 = fit
    pb = max(a + b * roe, 0.2)
    value = pb * t["equity"] / shares
    return MethodResult(
        "pb_roe_regression",
        label,
        value,
        min(1.0, 0.4 + r2),
        {"intercept": a, "slope": b, "r2": r2, "roe": roe, "fitted_pb": pb, "n": len(pts)},
        [
            "Fitted P/B for the company's ROE from a cross-sectional regression on peers (P/B stands in for P/TBV, which peers do not report uniformly)."
        ],
    )


def excess_return(ctx, ke: float, cfg: dict, roe_override: float | None = None) -> MethodResult:
    label = "Excess return model"
    from engine.fundamentals.ratios import ttm_ratios

    t = ctx.fin.ttm
    shares = t.get("shares_diluted")
    eq = t.get("equity")
    roe = roe_override if roe_override is not None else ttm_ratios(ctx.fin).get("roe")
    if not shares or not eq or eq <= 0 or roe is None:
        return missing("excess_return", label, "needs book equity and ROE")
    ni = t.get("net_income") or 0.0
    payout = min(max((t.get("dividends_paid") or 0.0) / ni, 0.0), 1.0) if ni > 0 else 0.0
    n = int(cfg["years"])
    bv = eq / shares
    value = bv
    for yr in range(1, n + 1):
        r = roe + (ke - roe) * yr / n  # ROE fades to the cost of equity: excess returns compete away
        value += (r - ke) * bv / (1 + ke) ** yr
        bv *= 1 + r * (1 - payout)
    return MethodResult(
        "excess_return",
        label,
        value,
        1.0,
        {
            "book_value_per_share": eq / shares,
            "roe": roe,
            "cost_of_equity": ke,
            "payout": payout,
            "fade_years": n,
        },
        [
            "Book value plus the present value of returns above the cost of equity, fading to zero over the horizon."
        ],
    )


def ddm(ctx, ke: float, cfg: dict) -> MethodResult:
    label = "Dividend discount model"
    from engine.fundamentals.ratios import ttm_ratios

    divs = [v for d, v in ctx.dividends if (ctx.as_of - d).days <= 365]
    dps = sum(divs)
    if dps <= 0:
        return missing("ddm", label, "no dividends in the last 12 months")
    roe = ttm_ratios(ctx.fin).get("roe")
    t = ctx.fin.ttm
    ni = t.get("net_income") or 0.0
    payout = min((t.get("dividends_paid") or 0.0) / ni, 1.0) if ni > 0 else 1.0
    g = min(max((roe or 0.0) * (1 - payout), 0.0), cfg["max_growth"])
    if ke - g < 0.01:
        g = ke - 0.01
    value = dps * (1 + g) / (ke - g)
    return MethodResult(
        "ddm",
        label,
        value,
        1.0,
        {"dps_ttm": dps, "growth": g, "cost_of_equity": ke, "roe": roe, "payout": payout},
        [
            "Gordon growth: next year's dividend ÷ (cost of equity − sustainable growth), growth = ROE × retention, capped."
        ],
    )


def p_ffo_history(ctx, history: list, cfg: dict) -> MethodResult:
    label = "P/FFO vs. own history"
    st = band_stats(history, "p_ffo", int(cfg["history_years"]), ctx.as_of)
    t = ctx.fin.ttm
    shares = t.get("shares_diluted")
    if not st or not shares or t.get("net_income") is None or t.get("dna") is None:
        return missing("p_ffo_history", label, "needs FFO and 8+ quarters of P/FFO history")
    ffo = t["net_income"] + t["dna"] - (t.get("gain_on_sale_re") or 0.0)
    if ffo <= 0:
        return missing("p_ffo_history", label, "FFO is not positive")
    return MethodResult(
        "p_ffo_history",
        label,
        st["median"] * ffo / shares,
        1.0,
        {"median_p_ffo": st["median"], "ffo_per_share": ffo / shares, "n": st["n"]},
        ["Median point-in-time P/FFO over the history window × trailing FFO per share."],
    )


def p_ffo_peers(ctx, peers: dict | None) -> MethodResult:
    label = "P/FFO vs. peers"
    if not peers or peers.get("status") != "ok" or ctx.universe is None:
        return missing("p_ffo_peers", label, "no peer set")
    by = {r.ticker: r for r in ctx.universe.rows if r.ticker}
    vals = []
    for r in peers["rows"]:
        if r["is_subject"]:
            continue
        u = by.get(r["ticker"])
        mc = r["metrics"].get("market_cap")
        if not u or not mc or u.values.get("net_income") is None or u.values.get("dna") is None:
            continue
        ffo = u.values["net_income"] + u.values["dna"]
        if ffo > 0:
            vals.append(mc / ffo)
    t = ctx.fin.ttm
    shares = t.get("shares_diluted")
    if len(vals) < 3 or not shares or t.get("net_income") is None or t.get("dna") is None:
        return missing("p_ffo_peers", label, "fewer than 3 peers with FFO")
    ffo = t["net_income"] + t["dna"] - (t.get("gain_on_sale_re") or 0.0)
    if ffo <= 0:
        return missing("p_ffo_peers", label, "FFO is not positive")
    med = float(np.median(vals))
    return MethodResult(
        "p_ffo_peers",
        label,
        med * ffo / shares,
        min(1.0, len(vals) / 5),
        {"peer_median_p_ffo": med, "n": len(vals), "ffo_per_share": ffo / shares},
        ["Peer FFO approximated as net income + D&A (gains on sales are not available for peers)."],
    )


def ev_sales_regression(ctx, peers: dict | None) -> MethodResult:
    label = "EV/Sales vs. growth regression (peers)"
    if not peers or peers.get("status") != "ok":
        return missing("ev_sales_regression", label, "no peer set")
    pts = [
        (r["metrics"]["revenue_growth"], math.log(r["metrics"]["ev_sales"]))
        for r in peers["rows"]
        if not r["is_subject"]
        and r["metrics"].get("revenue_growth") is not None
        and (r["metrics"].get("ev_sales") or 0) > 0
    ]
    fit = _ols([p[0] for p in pts], [p[1] for p in pts])
    subj = peers["rows"][0]["metrics"]
    t = ctx.fin.ttm
    g = subj.get("revenue_growth")
    shares = t.get("shares_diluted")
    if fit is None or g is None or not t.get("revenue") or not shares:
        return missing("ev_sales_regression", label, "needs at least 5 peers with EV/Sales and growth")
    a, b, r2 = fit
    evs = math.exp(a + b * g)
    v = _per_share_from_ev(
        evs * t["revenue"], t.get("net_debt") or 0.0, t.get("minority_interest") or 0.0, shares
    )
    return MethodResult(
        "ev_sales_regression",
        label,
        v,
        min(1.0, 0.4 + r2),
        {"intercept": a, "slope": b, "r2": r2, "growth": g, "fitted_ev_sales": evs, "n": len(pts)},
        ["Fitted EV/Sales for the company's revenue growth from a log-linear regression across peers."],
    )
