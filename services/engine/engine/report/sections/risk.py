"""Risk metrics and the red-flags panel."""

from __future__ import annotations

import numpy as np

from engine.analysis.risk import (
    avg_dollar_volume,
    beta_regression,
    correlation,
    downside_deviation,
    historical_var,
    max_drawdown,
    realized_vol,
)
from engine.report.context import ReportContext
from engine.report.metric import metric, section
from engine.report.sections.trust import flags


def build(ctx: ReportContext) -> dict:
    px = ctx.prices
    if px.empty:
        return section("risk", status="missing", reason=ctx.missing.get("prices", "no price history"))
    adj = px["adj_close"]
    src = ctx.sources.get("prices", {}).get("source")
    mkt_t, sec_t, mkt_label = ctx.benchmark_tickers()
    mk = ctx.market_prices["adj_close"] if not ctx.market_prices.empty else None
    sk = ctx.sector_prices["adj_close"] if not ctx.sector_prices.empty else None
    beta = beta_regression(adj, mk, 3) if mk is not None else None
    dd3 = max_drawdown(adj, 756)
    dd_all = max_drawdown(adj)
    last = ctx.last_price_date
    m = [
        metric(
            "beta",
            "Beta (3y weekly, Blume-adjusted)",
            beta["adjusted"] if beta else None,
            "ratio",
            source=f"{src}; {mkt_label}",
            as_of=last,
            reason="fewer than 104 weeks of overlapping prices",
            extra={"raw": beta["raw"] if beta else None, "r2": beta["r2"] if beta else None},
        ),
        metric(
            "volatility_1y",
            "Realized volatility (1y, annualized)",
            realized_vol(adj),
            "pct",
            source=src,
            as_of=last,
        ),
        metric(
            "downside_deviation",
            "Downside deviation (1y)",
            downside_deviation(adj),
            "pct",
            source=src,
            as_of=last,
        ),
        metric(
            "max_drawdown_3y",
            "Max drawdown (3y)",
            dd3["max_drawdown"] if dd3 else None,
            "pct",
            source=src,
            as_of=last,
            note=f"Peak {dd3['peak']}, trough {dd3['trough']}"
            + (f", recovered {dd3['recovered']}" if dd3 and dd3["recovered"] else ", not yet recovered")
            if dd3
            else None,
        ),
        metric(
            "max_drawdown_all",
            "Max drawdown (full history)",
            dd_all["max_drawdown"] if dd_all else None,
            "pct",
            source=src,
            as_of=last,
        ),
        metric(
            "current_drawdown",
            "Current drawdown from peak",
            dd_all["current_drawdown"] if dd_all else None,
            "pct",
            source=src,
            as_of=last,
        ),
        metric(
            "var_95",
            "1-day VaR (95%, historical)",
            historical_var(adj),
            "pct",
            source=src,
            as_of=last,
            note="Loss exceeded on about 1 trading day in 20 over the past year.",
        ),
        metric(
            "corr_market",
            f"Correlation with {mkt_t} (1y)",
            correlation(adj, mk) if mk is not None else None,
            "ratio",
            source=src,
            as_of=last,
        ),
        metric(
            "corr_sector",
            f"Correlation with {sec_t} (1y)",
            correlation(adj, sk) if sk is not None else None,
            "ratio",
            source=src,
            as_of=last,
            reason="no sector proxy for this sector",
        ),
        metric(
            "avg_dollar_volume",
            "Average daily dollar volume (3m)",
            avg_dollar_volume(px),
            "usd",
            source=src,
            as_of=last,
        ),
    ]
    # underwater series (weekly) for the drawdown chart
    w = adj.resample("W-FRI").last().dropna().iloc[-260:]
    under = (w / w.cummax() - 1).round(4)
    fl = flags(ctx)
    return section(
        "risk",
        metrics=m,
        drawdown={
            "dates": [d.date().isoformat() for d in under.index],
            "values": [float(x) if not np.isnan(x) else None for x in under.to_numpy()],
        },
        red_flags=fl,
        notes=[
            "Risk statistics use total-return (dividend-adjusted) prices.",
            f"Market benchmark: {mkt_label}.",
        ],
        sources=[
            {"name": k, **v} for k, v in ctx.sources.items() if k in ("prices", "filings", "fundamentals")
        ],
    )
