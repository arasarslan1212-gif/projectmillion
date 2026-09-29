"""Quantitative views: factor exposures, macro sensitivity and month-of-year seasonality.

- Factor exposures: OLS of the stock's weekly returns on the market and on long-short factor returns (size, value,
  momentum, quality, low volatility), each factor the return spread between two funds set in config.
- Macro sensitivity: for each macro series, OLS of weekly returns on the market and the series' weekly change, so the
  coefficient is the reaction beyond the market's own move.
- Seasonality: average return by calendar month; with twelve months tested at once a month is flagged only past a
  Bonferroni-adjusted threshold, because most apparent seasonal patterns are noise.

Everything is historical association over the stated window, labelled with its t-statistic and sample size.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
from scipy.stats import norm

from engine.report.context import ReportContext
from engine.report.metric import section

FACTOR_LABELS = {
    "market": "Market",
    "size": "Size (small minus large)",
    "value": "Value (value minus growth)",
    "momentum": "Momentum",
    "quality": "Quality",
    "low_vol": "Low volatility",
}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def ols(y: np.ndarray, X: np.ndarray) -> dict:
    """OLS with an intercept. Returns coefficients (intercept first), standard errors, t-stats and R²."""
    Xc = np.column_stack([np.ones(len(y)), X])
    beta, *_ = np.linalg.lstsq(Xc, y, rcond=None)
    resid = y - Xc @ beta
    dof = max(len(y) - Xc.shape[1], 1)
    s2 = float(resid @ resid) / dof
    cov = s2 * np.linalg.pinv(Xc.T @ Xc)
    se = np.sqrt(np.clip(np.diag(cov), 0, None))
    tss = float(((y - y.mean()) ** 2).sum())
    return {
        "beta": beta,
        "se": se,
        "t": np.divide(beta, se, out=np.zeros_like(beta), where=se > 0),
        "r2": 1 - float(resid @ resid) / tss if tss > 0 else None,
        "n": len(y),
    }


def weekly(px: pd.Series) -> pd.Series:
    return np.log(px.resample("W-FRI").last().dropna()).diff().dropna()


def _factor_block(ctx: ReportContext, cfg: dict, stock: pd.Series, mkt: pd.Series) -> dict:
    fmap = cfg["synthetic_factors"] if ctx.synthetic else cfg["factors"]
    cols = {"market": mkt}
    used, missing = {"market": [ctx.benchmark_tickers()[0]]}, []
    for f, (long, short) in fmap.items():
        a, b = ctx.other_prices(long), ctx.other_prices(short)
        if a.empty or b.empty:
            missing.append(f)
            continue
        cols[f] = weekly(a["adj_close"]) - weekly(b["adj_close"])
        used[f] = [long, short]
    df = pd.concat({"y": stock, **cols}, axis=1, sort=True).dropna().iloc[-int(cfg["window_weeks"]) :]
    if len(df) < int(cfg["min_weeks"]):
        return {"status": "missing", "reason": f"only {len(df)} weeks of overlapping returns"}
    names = [c for c in df.columns if c != "y"]
    r = ols(df["y"].to_numpy(), df[names].to_numpy())
    tcut = float(cfg["t_significant"])
    rows = []
    for i, f in enumerate(names, start=1):
        b, t = float(r["beta"][i]), float(r["t"][i])
        rows.append({"id": f, "label": FACTOR_LABELS.get(f, f), "beta": b, "t": t, "significant": abs(t) >= tcut,
                     "funds": used.get(f)})  # fmt: skip
    alpha, talpha = float(r["beta"][0]) * 52, float(r["t"][0])
    return {
        "status": "ok",
        "rows": rows,
        "alpha_annual": alpha,
        "alpha_t": talpha,
        "r2": r["r2"],
        "n_weeks": r["n"],
        "start": df.index[0].date().isoformat(),
        "end": df.index[-1].date().isoformat(),
        "missing_factors": missing,
    }


def _macro_block(ctx: ReportContext, cfg: dict, stock: pd.Series, mkt: pd.Series) -> dict:
    rows, missing = [], []
    tcut = float(cfg["t_significant"])
    for sid, spec in cfg["macro"].items():
        fx = ctx.data.macro(sid)
        if not fx.value or not fx.value.points:
            missing.append(sid)
            continue
        s = pd.Series({pd.Timestamp(p.date): p.value for p in fx.value.points}).sort_index()
        s = s[s.index <= pd.Timestamp(ctx.as_of)].resample("W-FRI").last().dropna()
        chg = s.diff() if spec["change"] == "diff" else np.log(s).diff()
        df = (
            pd.concat({"y": stock, "mkt": mkt, "x": chg}, axis=1, sort=True)
            .dropna()
            .iloc[-int(cfg["window_weeks"]) :]
        )
        if len(df) < int(cfg["min_weeks"]) or df["x"].std() == 0:
            missing.append(sid)
            continue
        r = ols(df["y"].to_numpy(), df[["mkt", "x"]].to_numpy())
        per = float(spec["per"])
        b, t = float(r["beta"][2]) * per, float(r["t"][2])
        rows.append({
            "id": sid, "label": spec["label"], "unit": spec["unit"], "effect": b, "t": t, "significant": abs(t) >= tcut,
            "correlation": float(df["y"].corr(df["x"])), "n_weeks": r["n"], "source": fx.value.source,
        })  # fmt: skip
    return {"rows": rows, "missing": missing}


def _seasonality(ctx: ReportContext, cfg: dict) -> dict:
    px = ctx.prices["adj_close"] if not ctx.prices.empty else pd.Series(dtype=float)
    m = np.log(px.resample("ME").last().dropna()).diff().dropna()
    m = m[m.index > pd.Timestamp(ctx.as_of) - pd.DateOffset(years=int(cfg["seasonality_years"]))]
    mk = ctx.market_prices["adj_close"] if not ctx.market_prices.empty else pd.Series(dtype=float)
    mm = np.log(mk.resample("ME").last().dropna()).diff().dropna() if len(mk) else pd.Series(dtype=float)
    if len(m) < 36:
        return {"status": "missing", "reason": f"only {len(m)} months of returns"}
    alpha = float(cfg["seasonality_alpha"]) / 12
    tcut = float(norm.ppf(1 - alpha / 2))
    rows = []
    for k in range(1, 13):
        g = m[m.index.month == k]
        ex = (g - mm.reindex(g.index)).dropna() if len(mm) else pd.Series(dtype=float)
        n = len(g)
        sd = float(g.std(ddof=1)) if n > 1 else None
        t = float(g.mean() / (sd / math.sqrt(n))) if sd else None
        rows.append({
            "month": MONTHS[k - 1], "n": n, "mean": float(np.expm1(g.mean())) if n else None,
            "positive_share": float((g > 0).mean()) if n else None,
            "excess_mean": float(np.expm1(ex.mean())) if len(ex) else None, "t": t,
            "significant": t is not None and abs(t) >= tcut,
        })  # fmt: skip
    best = max(rows, key=lambda r: r["mean"] if r["mean"] is not None else -9)
    worst = min(rows, key=lambda r: r["mean"] if r["mean"] is not None else 9)
    return {
        "status": "ok",
        "rows": rows,
        "years": round(len(m) / 12, 1),
        "t_threshold": tcut,
        "any_significant": any(r["significant"] for r in rows),
        "best": best["month"],
        "worst": worst["month"],
    }


def build(ctx: ReportContext) -> dict:
    cfg = ctx.cfg["quant"]
    if ctx.prices.empty or ctx.market_prices.empty:
        return section(
            "quant", status="missing", reason="price history for the stock or the market is unavailable"
        )
    stock, mkt = weekly(ctx.prices["adj_close"]), weekly(ctx.market_prices["adj_close"])
    factors = _factor_block(ctx, cfg, stock, mkt)
    macro = _macro_block(ctx, cfg, stock, mkt)
    seas = _seasonality(ctx, cfg)
    ok = sum(1 for b in (factors, seas) if b.get("status") == "ok") + (1 if macro["rows"] else 0)
    return section(
        "quant",
        status="ok" if ok == 3 else "partial" if ok else "missing",
        reason=None if ok == 3 else "some quantitative views lack data (see each block)",
        factors=factors,
        macro=macro,
        seasonality=seas,
        note="Historical associations over the stated windows, not forecasts. Weekly log returns; t-statistics from OLS.",
        sources=[{"name": "prices and FRED macro series", "as_of": ctx.as_of.isoformat()}],
    )
