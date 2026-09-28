"""Earnings: surprises, the stock's reaction, beat rates, estimate revisions, the next date and post-earnings drift."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from engine.report.context import ReportContext
from engine.report.metric import metric, section


def _surprise(actual: float | None, est: float | None) -> float | None:
    if actual is None or est is None or est == 0:
        return None
    return (actual - est) / abs(est)


def reaction(adj: pd.Series, mkt: pd.Series | None, d: date, timing: str | None, days: int) -> dict:
    """Return from the last close before the news reached the market to the close `days` sessions after it.

    before open (bmo): base = the close before the report date; first reacting session = the report date.
    after close (amc): base = the close on the report date; first reacting session = the next session.
    unknown timing:    base = the close before the report date; the window runs through the session after the
                       report date, so it covers both cases (the UI labels this).
    """
    idx = adj.index
    ts = pd.Timestamp(d)
    left, right = int(idx.searchsorted(ts, side="left")), int(idx.searchsorted(ts, side="right"))
    if timing == "amc":
        base, first = right - 1, right
    elif timing == "bmo":
        base, first = left - 1, left
    else:
        base, first = left - 1, right
    end = first + days - 1
    if base < 0 or end >= len(idx) or first >= len(idx):
        return {"ret": None, "excess": None}
    r = float(adj.iloc[end] / adj.iloc[base] - 1)
    ex = None
    if mkt is not None and not mkt.empty:
        m0, m1 = mkt.asof(idx[base]), mkt.asof(idx[end])
        if pd.notna(m0) and pd.notna(m1) and m0 > 0:
            ex = r - float(m1 / m0 - 1)
    return {"ret": r, "excess": ex}


def build(ctx: ReportContext) -> dict:
    cfg = ctx.cfg["earnings"]
    fx = ctx.data.earnings(ctx.ticker)
    ctx.sources["earnings"] = fx.meta()
    if not fx.value:
        return section(
            "earnings", status="missing", reason=fx.reason or "no earnings history from the data provider"
        )
    cal = ctx.data.earnings_calendar(ctx.ticker)
    timing = {e.date: e.time_of_day for e in (cal.value or []) if e.time_of_day}
    events = sorted(fx.value, key=lambda e: e.date)
    reported = [e for e in events if e.date <= ctx.as_of and e.eps_actual is not None][
        -int(cfg["quarters"]) :
    ]
    upcoming = [e for e in events if e.date > ctx.as_of] if not ctx.pit else []
    adj = ctx.prices["adj_close"] if not ctx.prices.empty else pd.Series(dtype=float)
    mkt = ctx.market_prices["adj_close"] if not ctx.market_prices.empty else None
    rows = []
    for e in reported:
        t = timing.get(e.date)
        r1 = reaction(adj, mkt, e.date, t, 1) if len(adj) else {"ret": None, "excess": None}
        r5 = reaction(adj, mkt, e.date, t, 5) if len(adj) else {"ret": None, "excess": None}
        rd = (
            reaction(adj, mkt, e.date, t, int(cfg["drift_days"]))
            if len(adj)
            else {"ret": None, "excess": None}
        )
        rows.append(
            {
                "date": e.date.isoformat(),
                "timing": {"bmo": "before open", "amc": "after close"}.get(t or "", "not reported"),
                "eps_actual": e.eps_actual,
                "eps_estimate": e.eps_estimate,
                "eps_surprise": _surprise(e.eps_actual, e.eps_estimate),
                "revenue_actual": e.revenue_actual,
                "revenue_estimate": e.revenue_estimate,
                "revenue_surprise": _surprise(e.revenue_actual, e.revenue_estimate),
                "reaction_1d": r1["ret"],
                "reaction_5d": r5["ret"],
                "excess_1d": r1["excess"],
                "drift_excess": rd["excess"],
            }
        )
    eps_s = [r["eps_surprise"] for r in rows if r["eps_surprise"] is not None]
    rev_s = [r["revenue_surprise"] for r in rows if r["revenue_surprise"] is not None]
    beat = float(np.mean([s > 0 for s in eps_s])) if eps_s else None
    rbeat = float(np.mean([s > 0 for s in rev_s])) if rev_s else None
    moves = [abs(r["reaction_1d"]) for r in rows if r["reaction_1d"] is not None]
    drift_beat = [
        r["drift_excess"] for r in rows if r["drift_excess"] is not None and (r["eps_surprise"] or 0) > 0
    ]
    drift_miss = [
        r["drift_excess"] for r in rows if r["drift_excess"] is not None and (r["eps_surprise"] or 0) < 0
    ]
    nxt = upcoming[0].date if upcoming else None

    revisions = _revisions(ctx, [int(w) for w in cfg["revision_windows"]])
    src = fx.source
    as_of = ctx.as_of
    return section(
        "earnings",
        status="ok" if rows else "partial",
        reason=None if rows else "no reported quarters with actual EPS",
        quarters=list(reversed(rows)),
        next_date=nxt.isoformat() if nxt else None,
        next_in_days=(nxt - ctx.as_of).days if nxt else None,
        next_timing=timing.get(nxt) if nxt else None,
        revisions=revisions,
        guidance={
            "status": "not_available",
            "note": "No configured data source provides company guidance history, so guidance accuracy (and the "
            "management credibility score built on it) is not computed.",
        },
        implied_move={
            "status": "not_available",
            "note": "Options data is not configured, so the market-implied earnings move is unavailable; the "
            "historical average move is shown instead.",
        },
        metrics={
            "beat_rate": metric(
                "eps_beat_rate",
                "EPS beat rate",
                beat,
                "pct",
                source=src,
                as_of=as_of,
                extra={"n": len(eps_s)},
            ),
            "revenue_beat_rate": metric(
                "revenue_beat_rate",
                "Revenue beat rate",
                rbeat,
                "pct",
                source=src,
                as_of=as_of,
                extra={"n": len(rev_s)},
            ),
            "avg_eps_surprise": metric(
                "avg_eps_surprise",
                "Average EPS surprise",
                float(np.median(eps_s)) if eps_s else None,
                "pct",
                source=src,
                as_of=as_of,
                note="median",
            ),
            "avg_move": metric(
                "avg_earnings_move",
                "Average move after earnings",
                float(np.mean(moves)) if moves else None,
                "pct",
                source=f"{src}; prices",
                as_of=as_of,
                note="absolute, first session",
            ),
            "drift_beats": metric(
                "post_earnings_drift_beats",
                "Drift after beats",
                float(np.mean(drift_beat)) if drift_beat else None,
                "pct",
                source=f"{src}; prices",
                as_of=as_of,
                extra={"n": len(drift_beat)},
            ),
            "drift_misses": metric(
                "post_earnings_drift_misses",
                "Drift after misses",
                float(np.mean(drift_miss)) if drift_miss else None,
                "pct",
                source=f"{src}; prices",
                as_of=as_of,
                extra={"n": len(drift_miss)},
            ),
            "next_date": metric(
                "next_earnings_date",
                "Next earnings date",
                nxt.isoformat() if nxt else None,
                "date",
                source=cal.source if cal.value else src,
                as_of=as_of,
                reason=None
                if nxt
                else ("not known point-in-time" if ctx.pit else "not announced in the data"),
            ),
        },  # fmt: skip
        guidance_hit_rate=None,
        sources=[{"name": src, "as_of": as_of.isoformat()}],
    )


def _revisions(ctx: ReportContext, windows: list[int]) -> dict:
    """Consensus EPS change over each window, from the app's own daily snapshots (see DECISIONS D-029)."""
    if ctx.pit:
        return {"status": "not_available", "note": "estimate snapshots are not point-in-time", "rows": []}
    hist = [
        r
        for r in ctx.data.estimate_history(ctx.ticker)
        if r["metric"] == "annual:eps" and r["mean"] is not None
    ]
    periods = sorted({r["period_end"] for r in hist if r["period_end"] > ctx.as_of})[:2]
    if not periods:
        return {"status": "not_available", "note": "no EPS estimates for upcoming fiscal years", "rows": []}
    out = []
    first = min(r["as_of"] for r in hist)
    for label, p in zip(("Current fiscal year", "Next fiscal year"), periods, strict=False):
        pts = sorted((r["as_of"], r["mean"]) for r in hist if r["period_end"] == p)
        now = pts[-1][1]
        row = {"label": label, "period_end": p.isoformat(), "current": now}
        for w in windows:
            target = pts[-1][0] - timedelta(days=w)
            base = [v for d, v in pts if d <= target]
            row[f"d{w}"] = (now / base[-1] - 1) if base and base[-1] else None
        out.append(row)
    ok = any(r.get(f"d{w}") is not None for r in out for w in windows)
    return {
        "status": "ok" if ok else "building",
        "note": None
        if ok
        else f"The app keeps one consensus snapshot per day; revision history starts on {first.isoformat()}.",
        "rows": out,
        "windows": windows,
    }
