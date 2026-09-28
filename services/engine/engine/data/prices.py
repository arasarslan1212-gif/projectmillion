"""Price-series helpers (pandas)."""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from engine.providers.models import PriceHistory


def to_frame(h: PriceHistory | None, as_of: date | None = None) -> pd.DataFrame:
    if h is None or not h.bars:
        return pd.DataFrame(columns=["open", "high", "low", "close", "adj_close", "volume"])
    df = pd.DataFrame([b.model_dump() for b in h.bars]).set_index("date").sort_index()
    df.index = pd.to_datetime(df.index)
    df = df[~df.index.duplicated(keep="last")]
    if as_of is not None:
        df = df[df.index <= pd.Timestamp(as_of)]
    return df.astype(float)


def splits_of(h: PriceHistory | None) -> list[tuple[date, float]]:
    return [(a.date, a.value) for a in (h.actions if h else []) if a.kind == "split"]


def dividends_of(h: PriceHistory | None, as_of: date | None = None) -> list[tuple[date, float]]:
    out = [(a.date, a.value) for a in (h.actions if h else []) if a.kind == "dividend"]
    if as_of:
        out = [x for x in out if x[0] <= as_of]
    return sorted(out)


def log_returns(s: pd.Series) -> pd.Series:
    s = s.dropna()
    s = s[s > 0]
    return np.log(s).diff().dropna()


def weekly_returns(s: pd.Series) -> pd.Series:
    w = s.dropna().resample("W-FRI").last().dropna()
    return w.pct_change().dropna()


def price_on_or_before(df: pd.DataFrame, d: date, col: str = "close") -> float | None:
    if df.empty:
        return None
    sub = df[df.index <= pd.Timestamp(d)]
    if sub.empty:
        return None
    v = sub[col].iloc[-1]
    return float(v) if pd.notna(v) else None
