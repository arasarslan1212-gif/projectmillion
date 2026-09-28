"""Risk statistics: beta, volatility, drawdowns, VaR, correlations."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from engine.data.prices import log_returns, weekly_returns


def beta_regression(stock: pd.Series, market: pd.Series, years: int = 3, min_weeks: int = 104) -> dict | None:
    """OLS beta of weekly simple returns over `years`, plus the Blume adjustment toward 1.

    Blume (1975): adjusted = 0.67 × raw + 0.33 × 1.
    """
    rs, rm = weekly_returns(stock), weekly_returns(market)
    df = pd.concat([rs, rm], axis=1, join="inner").dropna()
    if df.empty:
        return None
    cutoff = df.index[-1] - pd.DateOffset(years=years)
    df = df[df.index > cutoff]
    if len(df) < min_weeks:
        return None
    x, y = df.iloc[:, 1].to_numpy(), df.iloc[:, 0].to_numpy()
    vx = np.var(x, ddof=1)
    if vx == 0:
        return None
    raw = float(np.cov(y, x, ddof=1)[0, 1] / vx)
    resid = y - (y.mean() - raw * x.mean()) - raw * x
    se = float(np.sqrt(np.sum(resid**2) / (len(x) - 2) / np.sum((x - x.mean()) ** 2)))
    r2 = float(np.corrcoef(x, y)[0, 1] ** 2)
    return {
        "raw": raw,
        "adjusted": 0.67 * raw + 0.33,
        "se": se,
        "r2": r2,
        "n_weeks": int(len(df)),
        "start": df.index[0].date().isoformat(),
        "end": df.index[-1].date().isoformat(),
    }


def realized_vol(adj: pd.Series, days: int = 252) -> float | None:
    r = log_returns(adj).iloc[-days:]
    if len(r) < min(days, 60):
        return None
    return float(r.std(ddof=1) * math.sqrt(252))


def downside_deviation(adj: pd.Series, days: int = 252, mar: float = 0.0) -> float | None:
    r = log_returns(adj).iloc[-days:]
    if len(r) < 60:
        return None
    d = np.minimum(r.to_numpy() - mar / 252, 0.0)
    return float(np.sqrt(np.mean(d**2)) * math.sqrt(252))


def max_drawdown(adj: pd.Series, days: int | None = None) -> dict | None:
    s = adj.dropna()
    if days:
        s = s.iloc[-days:]
    if len(s) < 20:
        return None
    peak = s.cummax()
    dd = s / peak - 1
    trough_i = int(np.argmin(dd.to_numpy()))
    trough = dd.index[trough_i]
    peak_date = s.iloc[: trough_i + 1].idxmax()
    after = s.iloc[trough_i:]
    rec = after[after >= s.loc[peak_date]]
    return {
        "max_drawdown": float(dd.iloc[trough_i]),
        "peak": peak_date.date().isoformat(),
        "trough": trough.date().isoformat(),
        "recovered": rec.index[0].date().isoformat() if len(rec) else None,
        "current_drawdown": float(dd.iloc[-1]),
    }


def historical_var(adj: pd.Series, days: int = 252, level: float = 0.95) -> float | None:
    """1-day historical VaR (loss as a positive fraction) at `level`."""
    r = adj.dropna().pct_change().dropna().iloc[-days:]
    if len(r) < 100:
        return None
    return float(-np.quantile(r.to_numpy(), 1 - level))


def correlation(a: pd.Series, b: pd.Series, days: int = 252) -> float | None:
    df = pd.concat([log_returns(a), log_returns(b)], axis=1, join="inner").dropna().iloc[-days:]
    if len(df) < 60:
        return None
    return float(df.corr().iloc[0, 1])


def avg_dollar_volume(df: pd.DataFrame, days: int = 63) -> float | None:
    if df.empty or "volume" not in df:
        return None
    sub = df.iloc[-days:]
    v = (sub["close"] * sub["volume"]).dropna()
    return float(v.mean()) if len(v) else None
