"""Views across several tickers: compare mode and the watchlist (portfolio) summary.

Both reuse the report sections, so every number here is the same one the single-stock report shows, with the
same definitions, sources and as-of dates. Tickers are computed in parallel; one failing never blocks the rest.
"""

from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from engine.config import load_metric_defs
from engine.report.builder import contexts, run_section
from engine.report.context import ReportContext, TickerNotFound

COMPARE_METRICS: list[tuple[str, str]] = [
    ("company", "market_cap"),
    ("company", "pe"),
    ("company", "ev_ebitda"),
    ("company", "dividend_yield"),
    ("trust", "revenue_growth"),
    ("trust", "operating_margin"),
    ("trust", "roic"),
    ("trust", "roe"),
    ("trust", "net_debt_to_ebitda"),
    ("risk", "beta"),
    ("risk", "volatility_1y"),
    ("risk", "max_drawdown_3y"),
]
RANGES = {"6m": 126, "1y": 252, "3y": 756, "5y": 1260}


def _ok(sec: dict | None) -> dict | None:
    return sec if sec and sec.get("status") in ("ok", "partial") else None


def _trust_metric(trust: dict | None, mid: str) -> dict | None:
    for p in (trust or {}).get("pillars") or []:
        for m in p.get("metrics") or []:
            if m.get("id") == mid:
                return m
    return None


def _risk_metric(risk: dict | None, mid: str) -> dict | None:
    return next((m for m in (risk or {}).get("metrics") or [] if m.get("id") == mid), None)


def _one(ticker: str, names: tuple[str, ...]) -> tuple[ReportContext | None, dict]:
    try:
        ctx = contexts.get(ticker, None, False)
        _ = ctx.symbol
    except TickerNotFound:
        return None, {"ticker": ticker.upper(), "error": f"'{ticker.upper()}' is not a US-listed ticker"}
    secs = {n: _ok(run_section(ctx, n)) for n in names}
    return ctx, secs


def _summary(ctx: ReportContext, secs: dict) -> dict:
    comp, head, trust = secs.get("company") or {}, secs.get("headline") or {}, secs.get("trust")
    ident = comp.get("identity") or {}
    return {
        "ticker": ctx.ticker,
        "name": ident.get("name"),
        "sector": ident.get("sector_label"),
        "profile": ident.get("profile_label"),
        "synthetic": ctx.synthetic,
        "price": (comp.get("price") or {}).get("price"),
        "change_pct": (comp.get("price") or {}).get("change_pct"),
        "trust": head.get("trust"),
        "target": head.get("target"),
        "confidence": head.get("confidence"),
        "consensus": head.get("consensus"),
        "pillars": [
            {"id": p["id"], "label": p["label"], "score": p.get("score")}
            for p in (trust or {}).get("pillars", [])
        ],
    }


def _parallel(tickers: list[str], names: tuple[str, ...]):
    with ThreadPoolExecutor(max_workers=min(4, len(tickers))) as ex:
        return list(ex.map(lambda t: _one(t, names), tickers))


def _returns_frame(ctxs: list[ReportContext], days: int) -> pd.DataFrame:
    cols = {}
    for c in ctxs:
        px = c.prices
        if not px.empty:
            cols[c.ticker] = px["adj_close"]
    if not cols:
        return pd.DataFrame()
    df = pd.DataFrame(cols).dropna()
    return df.iloc[-(days + 1) :]


def compare(tickers: list[str], rng: str = "1y") -> dict:
    tickers = list(dict.fromkeys(t.upper() for t in tickers))[:4]
    res = _parallel(tickers, ("company", "headline", "trust", "risk"))
    rows, ctxs, errors = [], [], []
    defs = load_metric_defs()
    for ctx, secs in res:
        if ctx is None:
            errors.append(secs)
            continue
        ctxs.append(ctx)
        metrics = []
        for src, mid in COMPARE_METRICS:
            if src == "company":
                m = ((secs.get("company") or {}).get("stats") or {}).get(mid)
            elif src == "trust":
                m = _trust_metric(secs.get("trust"), mid)
            else:
                m = _risk_metric(secs.get("risk"), mid)
            metrics.append(m or {
                "id": mid, "label": (defs.get(mid) or {}).get("label", mid), "value": None,
                "status": "insufficient_data", "reason": "not used for this company's profile or not available",
            })  # fmt: skip
        rows.append({**_summary(ctx, secs), "metrics": metrics})
    # normalized price chart: common dates, rebased to 100, with the market benchmark
    days = RANGES.get(rng, 252)
    px = _returns_frame(ctxs, days)
    series, dates, bench = {}, [], None
    if not px.empty and len(px) > 1:
        step = 5 if len(px) > 400 else 1
        px = px.iloc[::-1].iloc[::step].iloc[::-1]  # keep the latest close when thinning
        dates = [d.date().isoformat() for d in px.index]
        series = {t: [float(v) for v in (px[t] / px[t].iloc[0] * 100)] for t in px.columns}
        m = ctxs[0].market_prices
        if not m.empty:
            mp = m["adj_close"].reindex(px.index).ffill()
            if mp.notna().all():
                bench = {"ticker": ctxs[0].benchmark_tickers()[0], "label": ctxs[0].benchmark_tickers()[2],
                         "values": [float(v) for v in mp / mp.iloc[0] * 100]}  # fmt: skip
    return {
        "tickers": [r["ticker"] for r in rows],
        "rows": rows,
        "errors": errors,
        "range": rng,
        "chart": {"dates": dates, "series": series, "benchmark": bench},
    }


def portfolio(tickers: list[str]) -> dict:
    """Equal-weight view of a watchlist: each holding's headline numbers, plus aggregate score and risk."""
    tickers = list(dict.fromkeys(t.upper() for t in tickers))[:30]
    if not tickers:
        return {"holdings": [], "aggregate": None, "errors": []}
    res = _parallel(tickers, ("company", "headline", "trust", "risk"))
    holdings, ctxs, errors = [], [], []
    for ctx, secs in res:
        if ctx is None:
            errors.append(secs)
            continue
        ctxs.append(ctx)
        risk = secs.get("risk") or {}
        flags = ((risk.get("red_flags") or {}).get("triggered")) or []
        vol, beta = _risk_metric(risk, "volatility_1y"), _risk_metric(risk, "beta")
        holdings.append({
            **_summary(ctx, secs),
            "volatility": (vol or {}).get("value"),
            "beta": (beta or {}).get("value"),
            "red_flags": len(flags),
            "severe_flags": sum(1 for f in flags if f.get("severity") == "high"),
        })  # fmt: skip
    return {"holdings": holdings, "aggregate": _aggregate(holdings, ctxs), "errors": errors}


def _mean(xs: list) -> float | None:
    v = [x for x in xs if x is not None and not (isinstance(x, float) and math.isnan(x))]
    return float(np.mean(v)) if v else None


def _aggregate(holdings: list[dict], ctxs: list[ReportContext]) -> dict:
    n = len(holdings)
    trust = [(h.get("trust") or {}).get("score") for h in holdings]
    grades: dict[str, int] = {}
    for h in holdings:
        g = (h.get("trust") or {}).get("grade")
        if g:
            grades[g] = grades.get(g, 0) + 1
    sectors: dict[str, int] = {}
    for h in holdings:
        sectors[h.get("sector") or "Unknown"] = sectors.get(h.get("sector") or "Unknown", 0) + 1
    out = {
        "n": n,
        "weighting": "equal weight",
        "trust_mean": _mean(trust),
        "trust_min": min((t for t in trust if t is not None), default=None),
        "grades": grades,
        "implied_return_mean": _mean([(h.get("target") or {}).get("implied_return") for h in holdings]),
        "confidence_mean": _mean([(h.get("confidence") or {}).get("score") for h in holdings]),
        "beta_mean": _mean([h.get("beta") for h in holdings]),
        "sectors": sorted(
            ({"sector": k, "n": v, "share": v / n} for k, v in sectors.items()), key=lambda r: -r["n"]
        ),
        "red_flags": sum(h["red_flags"] for h in holdings),
        "vol": None,
        "vol_avg_holding": None,
        "diversification_ratio": None,
        "avg_correlation": None,
        "correlation": None,
        "window_days": None,
    }
    px = _returns_frame(ctxs, 252)
    if len(px.columns) >= 2 and len(px) >= 60:
        r = np.log(px).diff().dropna()
        cov = r.cov().to_numpy() * 252
        w = np.full(len(px.columns), 1 / len(px.columns))
        port = float(math.sqrt(w @ cov @ w))
        vols = np.sqrt(np.diag(cov))
        corr = r.corr().to_numpy()
        iu = np.triu_indices(len(px.columns), 1)
        out.update({
            "vol": port,
            "vol_avg_holding": float(vols.mean()),
            "diversification_ratio": float(vols.mean() / port) if port > 0 else None,
            "avg_correlation": float(corr[iu].mean()),
            "correlation": {"tickers": list(px.columns), "matrix": [[float(x) for x in row] for row in corr]}
            if len(px.columns) <= 15 else None,
            "window_days": len(r),
        })  # fmt: skip
    return out
