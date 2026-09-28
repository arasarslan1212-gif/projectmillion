"""Header / snapshot: identity, price, key stats."""

from __future__ import annotations

from datetime import timedelta

import numpy as np

from engine.analysis.risk import beta_regression
from engine.report.context import ReportContext
from engine.report.metric import metric, safe_div, section


def build(ctx: ReportContext) -> dict:
    sym = ctx.symbol
    meta = ctx.meta
    fin = ctx.fin
    px = ctx.prices
    src_px = ctx.sources.get("prices", {}).get("source") if ctx.price_history else None
    last_date = ctx.last_price_date
    price = ctx.last_price

    change = change_pct = None
    if len(px) >= 2:
        prev = float(px["close"].iloc[-2])
        change = price - prev
        change_pct = price / prev - 1
    q = ctx.quote
    quote_note = None
    if q is not None:
        price, change, change_pct = q.price, q.change, q.change_pct
        quote_note = f"{q.source} quote"
    elif not px.empty:
        quote_note = f"end-of-day close on {last_date.isoformat()}"

    # 52-week range
    yr = px[px.index > px.index[-1] - np.timedelta64(365, "D")] if not px.empty else px
    lo52 = (
        float(yr["low"].min())
        if len(yr) and yr["low"].notna().any()
        else (float(yr["close"].min()) if len(yr) else None)
    )
    hi52 = (
        float(yr["high"].max())
        if len(yr) and yr["high"].notna().any()
        else (float(yr["close"].max()) if len(yr) else None)
    )
    pos52 = safe_div(
        (price - lo52) if (price is not None and lo52 is not None) else None,
        (hi52 - lo52) if hi52 and lo52 else None,
    )

    vol_today = float(px["volume"].iloc[-1]) if len(px) and px["volume"].notna().any() else None
    vol_avg = float(px["volume"].iloc[-63:].mean()) if len(px) >= 20 and px["volume"].notna().any() else None

    mcap = ctx.market_cap
    shares, shares_src = ctx.shares_outstanding
    ttm = fin.ttm
    eps = ttm.get("eps_diluted")
    pe = safe_div(price, eps) if eps and eps > 0 else None
    net_debt = ttm.get("net_debt")
    ev = (
        (mcap + net_debt + (ttm.get("minority_interest") or 0.0))
        if (mcap is not None and net_debt is not None)
        else None
    )
    ebitda = ttm.get("ebitda")
    ev_ebitda = safe_div(ev, ebitda) if ebitda and ebitda > 0 else None

    divs_12m = [v for d, v in ctx.dividends if d > ctx.as_of - timedelta(days=365)]
    dps = sum(divs_12m) if divs_12m else 0.0
    dy = safe_div(dps, price) if price else None

    beta = None
    if not ctx.market_prices.empty and not px.empty:
        beta = beta_regression(px["adj_close"], ctx.market_prices["adj_close"], years=3)
    mkt_label = ctx.benchmark_tickers()[2]

    fin_src = ctx.sources.get("fundamentals", {}).get("source")
    ttm_asof = fin.ttm_end.isoformat() if fin.ttm_end else None
    pe_reason = "EPS is negative or unavailable, so P/E is not meaningful" if pe is None else None
    ev_reason = "EBITDA is negative or unavailable" if ev_ebitda is None else None
    if ctx.sector.profile in ("bank", "insurer") and ev_ebitda is None:
        ev_reason = "EV/EBITDA is not meaningful for banks and insurers (debt is part of operations)"

    sector = ctx.sector
    return section(
        "company",
        synthetic=ctx.synthetic or bool(meta and meta.is_synthetic),
        identity={
            "ticker": sym.ticker,
            "name": meta.name if meta else sym.name,
            "exchange": sym.exchange or (meta.exchanges[0] if meta and meta.exchanges else None),
            "cik": sym.cik,
            "sic": sector.sic,
            "sic_description": sector.sic_description,
            "sector": sector.sector,
            "sector_label": sector.sector_label,
            "profile": sector.profile,
            "profile_label": sector.profile_label,
            "profile_reason": sector.overlay_reason,
            "sector_note": sector.method_note,
            "fiscal_year_end": meta.fiscal_year_end if meta else None,
            "hq": ", ".join(
                x
                for x in [
                    meta.hq_city.title() if meta and meta.hq_city else None,
                    meta.hq_state if meta else None,
                ]
                if x
            )
            or None,
            "sec_url": f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={sym.cik}"
            if sym.cik
            else None,
        },
        price={
            "price": metric(
                "price", "Price", price, "usd_per_share", source=src_px, as_of=last_date, note=quote_note
            ),
            "change": metric(
                "change", "Daily change", change, "usd_per_share", source=src_px, as_of=last_date
            ),
            "change_pct": metric(
                "change_pct", "Daily change %", change_pct, "pct", source=src_px, as_of=last_date
            ),
            "after_hours": metric(
                "after_hours",
                "After-hours",
                q.after_hours_price if q else None,
                "usd_per_share",
                reason="not available from the configured price feed",
            ),
        },
        stats={
            "market_cap": metric(
                "market_cap",
                "Market cap",
                mcap,
                "usd",
                source=f"{src_px} × shares ({shares_src})",
                as_of=last_date,
                reason="price or share count unavailable",
            ),
            "shares_outstanding": metric(
                "shares_outstanding", "Shares outstanding", shares, "shares", source=fin_src, note=shares_src
            ),
            "low_52w": metric(
                "low_52w", "52-week low", lo52, "usd_per_share", source=src_px, as_of=last_date
            ),
            "high_52w": metric(
                "high_52w", "52-week high", hi52, "usd_per_share", source=src_px, as_of=last_date
            ),
            "pos_52w": metric(
                "pos_52w", "Position in 52-week range", pos52, "pct", source=src_px, as_of=last_date
            ),
            "volume": metric("volume", "Volume", vol_today, "shares", source=src_px, as_of=last_date),
            "avg_volume": metric(
                "avg_volume", "Average volume (3 months)", vol_avg, "shares", source=src_px, as_of=last_date
            ),
            "volume_ratio": metric(
                "volume_ratio",
                "Volume vs. 3-month average",
                safe_div(vol_today, vol_avg),
                "x",
                source=src_px,
                as_of=last_date,
            ),
            "pe": metric(
                "pe_ttm",
                "P/E (TTM)",
                pe,
                "x",
                source=f"{src_px}; {fin_src}",
                as_of=ttm_asof,
                reason=pe_reason,
            ),
            "ev_ebitda": metric(
                "ev_ebitda_ttm",
                "EV/EBITDA (TTM)",
                ev_ebitda,
                "x",
                source=f"{src_px}; {fin_src}",
                as_of=ttm_asof,
                reason=ev_reason,
            ),
            "dividend_yield": metric(
                "dividend_yield",
                "Dividend yield (TTM)",
                dy,
                "pct",
                source=src_px,
                as_of=last_date,
                reason="no price available",
            ),
            "beta": metric(
                "beta",
                "Beta (3y weekly, Blume-adjusted)",
                beta["adjusted"] if beta else None,
                "ratio",
                source=f"{src_px}; benchmark {mkt_label}",
                as_of=last_date,
                reason="fewer than 104 weeks of overlapping prices",
                extra={"raw": beta} if beta else None,
            ),
            "enterprise_value": metric(
                "enterprise_value",
                "Enterprise value",
                ev,
                "usd",
                source=f"{src_px}; {fin_src}",
                as_of=ttm_asof,
            ),
        },
        ttm_note=fin.ttm_note,
        sources=[{"name": k, **v} for k, v in ctx.sources.items()],
        as_of=ctx.as_of.isoformat(),
    )
