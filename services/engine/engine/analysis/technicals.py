"""Technical indicators. All functions take a price Series indexed by date and return Series."""

from __future__ import annotations

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def bollinger(s: pd.Series, n: int = 20, k: float = 2.0) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = sma(s, n)
    sd = s.rolling(n, min_periods=n).std(ddof=0)
    return mid - k * sd, mid, mid + k * sd


def rsi(s: pd.Series, n: int = 14) -> pd.Series:
    """Wilder's RSI."""
    d = s.diff()
    up = d.clip(lower=0.0)
    dn = (-d).clip(lower=0.0)
    au = up.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    ad = dn.ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = au / ad.replace(0.0, np.nan)
    out = 100 - 100 / (1 + rs)
    out[(ad == 0) & (au > 0)] = 100.0
    return out


def macd(
    s: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[pd.Series, pd.Series, pd.Series]:
    line = ema(s, fast) - ema(s, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return line, sig, line - sig


def momentum_12_1(adj: pd.Series) -> float | None:
    """Total return from 12 months ago to 1 month ago (skips the most recent month)."""
    s = adj.dropna()
    if len(s) < 260:
        return None
    return float(s.iloc[-22] / s.iloc[-253] - 1)


def total_return(adj: pd.Series, days: int) -> float | None:
    s = adj.dropna()
    if len(s) <= days:
        return None
    return float(s.iloc[-1] / s.iloc[-1 - days] - 1)


def trend_score(close: pd.Series) -> float | None:
    """0-100: price vs 50/200-day averages and the 200-day slope. 100 = strong uptrend."""
    s = close.dropna()
    if len(s) < 220:
        return None
    s50, s200 = sma(s, 50), sma(s, 200)
    p = s.iloc[-1]
    pts = 0.0
    pts += 30 if p > s200.iloc[-1] else 0
    pts += 20 if p > s50.iloc[-1] else 0
    pts += 25 if s50.iloc[-1] > s200.iloc[-1] else 0
    pts += 25 if s200.iloc[-1] > s200.iloc[-21] else 0
    return pts
