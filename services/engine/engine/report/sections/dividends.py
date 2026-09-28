"""Dividends: yield against its own history and the sector, payout ratios, growth streak, CAGR and a safety score."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

import numpy as np
import pandas as pd

from engine.fundamentals.ratios import div, ttm_ratios
from engine.report.context import ReportContext
from engine.report.metric import metric, section


def _lin(v: float | None, a: list[float]) -> float | None:
    if v is None or not np.isfinite(v):
        return None
    a0, a100 = a
    return float(min(100.0, max(0.0, (v - a0) / (a100 - a0) * 100.0)))


def ttm_dps(divs: list[tuple], on) -> float:
    return sum(v for d, v in divs if on - timedelta(days=365) < d <= on)


def build(ctx: ReportContext) -> dict:
    cfg = ctx.cfg["dividends"]
    divs = ctx.dividends
    p0 = ctx.last_price
    as_of = ctx.as_of
    recent = [x for x in divs if (as_of - x[0]).days <= 730]
    if not recent:
        return section(
            "dividends",
            status="not_applicable",
            reason="The company has not paid a dividend in the last two years.",
            pays_dividend=False,
        )
    src = ctx.sources.get("prices", {}).get("source") or "price history (dividend events)"
    dps = ttm_dps(divs, as_of)
    yld = dps / p0 if p0 else None

    # yield history: trailing-12-month dividends ÷ month-end close, point-in-time
    closes = ctx.prices["close"] if not ctx.prices.empty else pd.Series(dtype=float)
    hist_dates, hist_yield = [], []
    if len(closes):
        month_end = closes.resample("ME").last().dropna()
        for ts, px in month_end.items():
            d = ts.date()
            if d < divs[0][0] + timedelta(days=365):
                continue
            hist_dates.append(d.isoformat())
            hist_yield.append(ttm_dps(divs, d) / px if px else None)
    five = [
        y
        for d, y in zip(hist_dates, hist_yield, strict=True)
        if y is not None and d >= (as_of - timedelta(days=5 * 365)).isoformat()
    ]
    avg5 = float(np.mean(five)) if len(five) >= 24 else None
    pct_rank = float(np.mean([y <= yld for y in five])) if (five and yld is not None) else None

    # annual dividends per share by calendar year (complete years only), growth streak and CAGR
    by_year: dict[int, float] = defaultdict(float)
    for d, v in divs:
        by_year[d.year] += v
    years = sorted(y for y in by_year if y < as_of.year)
    streak = 0
    for a, b in zip(reversed(years[:-1]), reversed(years[1:]), strict=True):
        if b - a == 1 and by_year[b] > by_year[a] * 1.001:
            streak += 1
        else:
            break

    def cagr(n: int) -> float | None:
        if len(years) < n + 1 or by_year[years[-1 - n]] <= 0 or years[-1] - years[-1 - n] != n:
            return None
        return (by_year[years[-1]] / by_year[years[-1 - n]]) ** (1 / n) - 1

    # payout and coverage
    t = ctx.fin.ttm
    paid = t.get("dividends_paid")
    reit = ctx.sector.profile == "reit"
    ratios = ttm_ratios(ctx.fin)
    earnings_base = ratios.get("ffo") if reit else t.get("net_income")
    payout_e = div(paid, earnings_base) if (earnings_base or 0) > 0 else None
    payout_f = div(paid, t.get("fcf")) if (t.get("fcf") or 0) > 0 else None
    lev = None
    if not ctx.sector.is_financial and (t.get("ebitda") or 0) > 0:
        lev = div(t.get("net_debt"), t.get("ebitda"))
    eps = [v for _, v in ctx.fin.annual_series("eps_diluted")[-8:]]
    stability = float(np.mean([v > 0 for v in eps])) if eps else None
    prof = ctx.sector.profile
    a = {**cfg["anchors"], **(cfg.get("profile_anchors", {}).get(prof) or {})}
    skip = set(cfg.get("profile_skip", {}).get(prof) or [])
    comps = {
        "earnings_payout": _lin(payout_e if payout_e is not None else (5.0 if (earnings_base or 0) <= 0 else None), a["earnings_payout"]),
        "fcf_payout": _lin(payout_f if payout_f is not None else (5.0 if (t.get("fcf") or 0) <= 0 else None), a["fcf_payout"]),
        "leverage": _lin(lev, a["leverage"]),
        "stability": _lin(stability, a["stability"]),
        "streak": _lin(float(streak), a["streak"]),
    }  # fmt: skip
    w = cfg["safety_weights"]
    for k in skip:
        comps[k] = None
    have = {k: v for k, v in comps.items() if v is not None}
    safety = sum(w[k] * v for k, v in have.items()) / sum(w[k] for k in have) if have else None
    level = next((lbl for th, lbl in cfg["levels"] if safety is not None and safety >= th), None)

    # sector comparison: peers' dividend yield (calendar-year dividends paid ÷ current market cap)
    peer_yields = []
    try:
        from engine.analysis.trust_rating import _safe_section

        peers = _safe_section(ctx, "peers") or {}
        uni = {r.ticker: r for r in (ctx.universe.rows if ctx.universe else []) if r.ticker}
        for r in peers.get("rows", []):
            if r.get("is_subject"):
                continue
            mc = (r.get("metrics") or {}).get("market_cap")
            mc = mc.get("value") if isinstance(mc, dict) else mc
            u = uni.get(r["ticker"])
            dp = u.values.get("dividends_paid") if u else None
            if mc and dp and dp > 0:
                peer_yields.append(dp / mc)
    except Exception:  # the comparison is optional context
        peer_yields = []
    sector_med = float(np.median(peer_yields)) if len(peer_yields) >= 3 else None

    events = [{"ex_date": d.isoformat(), "amount": v} for d, v in reversed(divs[-12:])]
    return section(
        "dividends",
        status="ok",
        pays_dividend=True,
        metrics={
            "yield": metric(
                "dividend_yield", "Dividend yield (trailing 12 months)", yld, "pct", source=src, as_of=as_of
            ),
            "dps_ttm": metric(
                "dps_ttm",
                "Dividends per share (trailing 12 months)",
                dps,
                "usd_per_share",
                source=src,
                as_of=as_of,
            ),
            "yield_5y_avg": metric(
                "dividend_yield_5y_avg", "5-year average yield", avg5, "pct", source=src, as_of=as_of
            ),
            "yield_percentile": metric(
                "dividend_yield_percentile",
                "Yield vs. own 5-year history",
                pct_rank,
                "pct",
                source=src,
                as_of=as_of,
                note="share of months with a lower or equal yield",
            ),
            "sector_yield": metric(
                "sector_dividend_yield",
                "Peer median yield",
                sector_med,
                "pct",
                source="SEC frames (dividends paid) ÷ market cap",
                as_of=as_of,
                reason=None if sector_med is not None else "fewer than 3 dividend-paying peers",
                extra={"n": len(peer_yields)},
            ),
            "payout_earnings": metric(
                "payout_ratio" if not reit else "payout_ratio_ffo",
                "Payout ratio (FFO)" if reit else "Payout ratio (earnings)",
                payout_e,
                "pct",
                source="SEC filings",
                as_of=as_of,
                reason=None if payout_e is not None else "earnings not positive",
            ),
            "payout_fcf": metric(
                "payout_ratio_fcf",
                "Payout ratio (free cash flow)",
                payout_f,
                "pct",
                source="SEC filings",
                as_of=as_of,
                reason=None if payout_f is not None else "free cash flow not positive",
            ),
            "streak": metric(
                "dividend_growth_streak",
                "Consecutive years of increases",
                streak,
                "years",
                source=src,
                as_of=as_of,
            ),
            "cagr_5y": metric(
                "dividend_cagr_5y", "Dividend growth (5-year CAGR)", cagr(5), "pct", source=src, as_of=as_of
            ),
            "cagr_10y": metric(
                "dividend_cagr_10y",
                "Dividend growth (10-year CAGR)",
                cagr(10),
                "pct",
                source=src,
                as_of=as_of,
            ),
            "safety": metric(
                "dividend_safety",
                "Dividend safety score",
                safety,
                "score",
                source="app (see Methodology)",
                as_of=as_of,
                note=level,
            ),
        },  # fmt: skip
        safety_components=[
            {"id": k, "score": v, "weight": w[k], "skipped": k in skip, "anchors": a[k]}
            for k, v in comps.items()
        ],
        safety_level=level,
        annual=[{"year": y, "dps": by_year[y]} for y in years[-15:]],
        yield_history={"dates": hist_dates, "yield": hist_yield, "avg_5y": avg5, "sector": sector_med},
        events=events,
        pay_dates_note="Payment dates are not in the configured price feed; ex-dividend dates and amounts are shown.",
        sources=[{"name": src, "as_of": as_of.isoformat()}],
    )
