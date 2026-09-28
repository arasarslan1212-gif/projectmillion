"""Outcome scoring: grade each snapshot once its horizon has passed.

The realized price is the last close on or before the horizon date, converted to the snapshot's share basis by
applying the stock's return since the snapshot (so a later split cannot distort the grade). Grades:
- in_band: the realized price landed inside P10–P90;
- abs_pct_err: |realized ÷ P50 − 1|;
- realized_up and the Brier score (prob_up − realized_up)² for the probability that the price is higher.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select

from engine import clock
from engine.data.prices import to_frame
from engine.data.service import get_data
from engine.db import models as m
from engine.db.session import session_scope

log = logging.getLogger("engine.track")


def grade(price: float, p10: float, p50: float, p90: float, prob_up: float | None, ret: float) -> dict:
    realized = price * (1 + ret)
    up = realized > price
    return {
        "realized_price": realized,
        "realized_return": ret,
        "in_band": bool(p10 <= realized <= p90),
        "abs_pct_err": abs(realized / p50 - 1),
        "realized_up": bool(up),
        "brier": (prob_up - float(up)) ** 2 if prob_up is not None else None,
    }


def realized_return(closes: pd.Series, start: date, end: date) -> float | None:
    """Return from the last close on or before `start` to the last close on or before `end`."""
    if closes.empty:
        return None
    s = closes[closes.index <= pd.Timestamp(start)]
    e = closes[closes.index <= pd.Timestamp(end)]
    if s.empty or e.empty or e.index[-1] <= s.index[-1]:
        return None
    if (pd.Timestamp(end) - e.index[-1]).days > 7:  # no trading near the horizon: delisted or data gap
        return None
    a, b = float(s.iloc[-1]), float(e.iloc[-1])
    return b / a - 1 if a > 0 and np.isfinite(b) else None


def score_due(today: date | None = None, tickers: list[str] | None = None) -> dict:
    """Score every snapshot whose horizon has passed and that has no outcome yet. Idempotent."""
    today = today or clock.today()
    with session_scope() as s:
        scored = select(m.SnapshotOutcome.snapshot_id)
        q = select(m.AppSnapshot).where(m.AppSnapshot.id.not_in(scored))
        if tickers:
            q = q.where(m.AppSnapshot.ticker.in_([t.upper() for t in tickers]))
        due = [
            r
            for r in s.scalars(q)
            if r.as_of + timedelta(days=r.horizon_days) <= today and r.p10 and r.p50 and r.p90
        ]
        todo = [
            (r.id, r.ticker, r.as_of, r.horizon_days, r.price, r.p10, r.p50, r.p90, r.prob_up) for r in due
        ]
    closes: dict[str, pd.Series] = {}
    out, skipped = [], 0
    for sid, ticker, as_of, hz, price, p10, p50, p90, prob_up in todo:
        if ticker not in closes:
            h = get_data().prices(ticker).value
            df = to_frame(h)
            closes[ticker] = df["close"] if not df.empty else pd.Series(dtype=float)
        end = as_of + timedelta(days=hz)
        ret = realized_return(closes[ticker], as_of, end)
        if ret is None:
            skipped += 1
            continue
        out.append({"snapshot_id": sid, "horizon_date": end, **grade(price, p10, p50, p90, prob_up, ret)})
    if out:
        with session_scope() as s:
            s.add_all(m.SnapshotOutcome(**o) for o in out)
    log.info("scored %d snapshots (%d without a usable price at the horizon)", len(out), skipped)
    return {"scored": len(out), "skipped": skipped, "due": len(todo)}


COLUMNS = [
    "id", "ticker", "as_of", "price", "p10", "p50", "p90", "prob_up", "confidence", "trust_rating", "sector",
    "profile", "size_bucket", "vol_bucket", "is_backtest", "engine_version", "config_hash", "prob_up_raw",
    "sigma_total_raw", "sigma_total", "methods", "horizon_date", "realized_price", "realized_return", "in_band",
    "abs_pct_err", "realized_up", "brier",
]  # fmt: skip


def outcomes_frame(
    *, synthetic: bool | None = None, backtest: bool | None = None, cutoff: date | None = None
) -> pd.DataFrame:
    """Scored snapshots joined with their outcomes. `cutoff` keeps only outcomes known by that date."""
    with session_scope() as s:
        q = select(m.AppSnapshot, m.SnapshotOutcome).join(
            m.SnapshotOutcome, m.SnapshotOutcome.snapshot_id == m.AppSnapshot.id
        )
        if synthetic is not None:
            q = q.where(m.AppSnapshot.is_synthetic.is_(synthetic))
        if backtest is not None:
            q = q.where(m.AppSnapshot.is_backtest.is_(backtest))
        if cutoff is not None:
            q = q.where(m.SnapshotOutcome.horizon_date <= cutoff)
        rows = []
        for a, o in s.execute(q):
            rj = a.report_json or {}
            rows.append({
                "id": a.id, "ticker": a.ticker, "as_of": a.as_of, "price": a.price, "p10": a.p10, "p50": a.p50,
                "p90": a.p90, "prob_up": a.prob_up, "confidence": a.confidence, "trust_rating": a.trust_rating,
                "sector": a.sector, "profile": rj.get("profile"), "size_bucket": a.size_bucket,
                "vol_bucket": a.vol_bucket, "is_backtest": a.is_backtest, "engine_version": a.engine_version,
                "config_hash": a.config_hash, "prob_up_raw": rj.get("prob_up_raw", a.prob_up),
                "sigma_total_raw": rj.get("sigma_total_raw"), "sigma_total": rj.get("sigma_total"),
                "methods": rj.get("methods") or [], "horizon_date": o.horizon_date,
                "realized_price": o.realized_price, "realized_return": o.realized_return, "in_band": o.in_band,
                "abs_pct_err": o.abs_pct_err, "realized_up": o.realized_up, "brier": o.brier,
            })  # fmt: skip
    return pd.DataFrame(rows, columns=COLUMNS)
