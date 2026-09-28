"""Peers: automatic selection (editable), comparison table, medians, ranks and scatter data."""

from __future__ import annotations

from engine.fundamentals.universe import peer_medians, peer_table, select_peers
from engine.report.context import ReportContext
from engine.report.metric import section

COLUMNS = [
    ("market_cap", "Market cap", "usd", True),
    ("revenue", "Revenue", "usd", True),
    ("revenue_growth", "Revenue growth", "pct", True),
    ("gross_margin", "Gross margin", "pct", True),
    ("operating_margin", "Operating margin", "pct", True),
    ("net_margin", "Net margin", "pct", True),
    ("fcf_margin", "FCF margin", "pct", True),
    ("roe", "ROE", "pct", True),
    ("debt_to_equity", "Debt / equity", "x", False),
    ("pe", "P/E", "x", False),
    ("ev_ebitda", "EV/EBITDA", "x", False),
    ("ev_sales", "EV/Sales", "x", False),
    ("p_fcf", "P/FCF", "x", False),
    ("p_b", "P/B", "x", False),
    ("return_1y", "1-year return", "pct", True),
]


def build(ctx: ReportContext) -> dict:
    uni = ctx.universe
    tickers, how = select_peers(ctx, uni, ctx.peer_override)
    if not tickers:
        return section(
            "peers",
            status="missing",
            reason="no comparable companies found in the SEC industry universe or the provider's peer list",
        )
    rows = peer_table(ctx, uni, tickers)
    med = peer_medians(rows)
    subject = rows[0]
    ranks = {}
    for key, _label, _unit, higher in COLUMNS:
        vals = [(r.metrics.get(key), r.is_subject) for r in rows if r.metrics.get(key) is not None]
        if subject.metrics.get(key) is None or len(vals) < 3:
            continue
        ordered = sorted(vals, key=lambda x: x[0], reverse=higher)
        rank = next(i for i, x in enumerate(ordered) if x[1]) + 1
        ranks[key] = {"rank": rank, "of": len(ordered), "better_is": "higher" if higher else "lower"}
    scatter = [
        {
            "ticker": r.ticker,
            "x": r.metrics.get("revenue_growth"),
            "y": r.metrics.get("ev_sales"),
            "size": r.metrics.get("market_cap"),
            "is_subject": r.is_subject,
        }
        for r in rows
        if r.metrics.get("revenue_growth") is not None and r.metrics.get("ev_sales") is not None
    ]
    year = uni.year if uni else None
    return section(
        "peers",
        columns=[{"key": k, "label": lbl, "unit": u, "higher_is_better": h} for k, lbl, u, h in COLUMNS],
        rows=[
            {"ticker": r.ticker, "name": r.name, "is_subject": r.is_subject, "metrics": r.metrics}
            for r in rows
        ],
        medians=med,
        ranks=ranks,
        scatter={"x": "revenue_growth", "y": "ev_sales", "size": "market_cap", "points": scatter},
        selection_note=f"Peers selected by {how}.",
        basis_note=(
            f"Fundamentals for every row, including this company, use calendar-year {year} SEC frames so they are "
            "comparable; price-based multiples use the latest close. Market caps for peers use weighted-average diluted shares."
            if year
            else "Industry data unavailable."
        ),
        editable=True,
        universe_note=uni.note if uni else None,
        sources=[{"name": k, **v} for k, v in ctx.sources.items() if k in ("universe", "prices")],
    )
