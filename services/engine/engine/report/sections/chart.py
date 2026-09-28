"""Main price chart data: OHLCV, indicators, benchmark comparison, and event markers.

Indicators are computed here (not in the browser) so that every plotted number comes from tested code.
Later milestones add markers (earnings, news, insider, analysts) and the forward target cone.
"""

from __future__ import annotations

import math

import pandas as pd

from engine.analysis.technicals import bollinger, ema, macd, rsi, sma
from engine.report.context import ReportContext
from engine.report.metric import section


def _series(s: pd.Series, nd: int = 4) -> list:
    out = []
    for v in s.to_numpy():
        if v is None or (isinstance(v, float) and math.isnan(v)):
            out.append(None)
        else:
            out.append(round(float(v), nd))
    return out


def build(ctx: ReportContext) -> dict:
    df = ctx.prices
    if df.empty:
        return section("chart", status="missing", reason=ctx.missing.get("prices", "no price data"))
    close = df["close"]
    lo_bb, mid_bb, hi_bb = bollinger(close)
    m_line, m_sig, m_hist = macd(close)
    dates = [d.date().isoformat() for d in df.index]
    mkt_ticker, sector_etf, mkt_label = ctx.benchmark_tickers()
    comps = {}
    for label, frame, tk in (
        ("market", ctx.market_prices, mkt_ticker),
        ("sector", ctx.sector_prices, sector_etf),
    ):
        if frame is None or frame.empty:
            continue
        aligned = frame["adj_close"].reindex(df.index).ffill()
        comps[label] = {
            "ticker": tk,
            "label": mkt_label if label == "market" else f"{tk} ({ctx.sector.sector_label} sector proxy)",
            "adj_close": _series(aligned),
        }
    splits = [{"date": d.isoformat(), "ratio": r} for d, r in ctx.splits if d <= ctx.as_of]
    divs = [{"date": d.isoformat(), "amount": round(v, 4)} for d, v in ctx.dividends]
    return section(
        "chart",
        dates=dates,
        ohlc={
            "open": _series(df["open"]),
            "high": _series(df["high"]),
            "low": _series(df["low"]),
            "close": _series(close),
            "adj_close": _series(df["adj_close"]),
            "volume": _series(df["volume"], 0),
        },
        indicators={
            "sma20": _series(sma(close, 20)),
            "sma50": _series(sma(close, 50)),
            "sma200": _series(sma(close, 200)),
            "ema20": _series(ema(close, 20)),
            "bb_lower": _series(lo_bb),
            "bb_mid": _series(mid_bb),
            "bb_upper": _series(hi_bb),
            "rsi14": _series(rsi(close), 2),
            "macd": _series(m_line),
            "macd_signal": _series(m_sig),
            "macd_hist": _series(m_hist),
        },
        comparisons=comps,
        markers={"splits": splits, "dividends": divs},
        notes={
            "adjustment": "Prices are split-adjusted; the comparison lines use total-return (dividend-adjusted) prices.",
            "intraday": "Intraday bars and VWAP need an intraday feed, which is not configured, so 1D/5D ranges use daily bars.",
        },
        sources=[{"name": "prices", **ctx.sources.get("prices", {})}],
    )
