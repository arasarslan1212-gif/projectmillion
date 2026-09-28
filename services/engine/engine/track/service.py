"""The track record as the web app shows it: live results kept apart from backtests, with caveats."""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
from sqlalchemy import func, select

from engine import clock
from engine.config import ENGINE_VERSION, get_config
from engine.db import models as m
from engine.db.session import session_scope
from engine.track import calibration, metrics
from engine.track.backtest import CAVEATS, SYNTHETIC_CAVEAT
from engine.track.scoring import outcomes_frame


def _counts(synthetic: bool) -> dict:
    today = clock.today()
    with session_scope() as s:

        def n(backtest: bool, scored: bool | None = None) -> int:
            q = (
                select(func.count())
                .select_from(m.AppSnapshot)
                .where(m.AppSnapshot.is_synthetic.is_(synthetic), m.AppSnapshot.is_backtest.is_(backtest))
            )
            if scored is not None:
                sub = select(m.SnapshotOutcome.snapshot_id)
                q = q.where(m.AppSnapshot.id.in_(sub) if scored else m.AppSnapshot.id.not_in(sub))
            return int(s.scalar(q) or 0)

        first_live = s.scalar(
            select(func.min(m.AppSnapshot.as_of)).where(
                m.AppSnapshot.is_synthetic.is_(synthetic), m.AppSnapshot.is_backtest.is_(False)
            )
        )
        hz = int(get_config()["track"]["horizon_days"])
        return {
            "backtest": {"snapshots": n(True), "scored": n(True, True)},
            "live": {
                "snapshots": n(False),
                "scored": n(False, True),
                "first": first_live.isoformat() if first_live else None,
                "first_due": (first_live + timedelta(days=hz)).isoformat() if first_live else None,
                "days_until_first_due": (first_live + timedelta(days=hz) - today).days
                if first_live
                else None,
            },
        }


def track_record(kind: str = "backtest", profile: str | None = None) -> dict:
    """kind: 'backtest' | 'live' | 'all'."""
    cfg = get_config()
    synthetic = clock.is_synthetic()
    backtest = {"backtest": True, "live": False}.get(kind)
    df = outcomes_frame(synthetic=synthetic, backtest=backtest)
    profiles = sorted(df["profile"].dropna().unique().tolist()) if len(df) else []
    if profile and len(df):
        df = df[df["profile"] == profile]
    cur = calibration.current(clock.today(), synthetic)
    caveats = list(CAVEATS) if kind != "live" else []
    if kind == "live":
        caveats.append("Live results: estimates stored when reports were viewed, graded 12 months later.")
    if synthetic:
        caveats.insert(0, SYNTHETIC_CAVEAT)
    return {
        "kind": kind,
        "profile": profile,
        "profiles": profiles,
        "synthetic": synthetic,
        "counts": _counts(synthetic),
        "horizon_days": int(cfg["track"]["horizon_days"]),
        "results": metrics.full(df, cfg),
        "calibration": {
            "current": cur,
            "curve": calibration.prob_map_curve((cur or {}).get("prob_map")),
            "changes": calibration.changes(synthetic),
            "min_outcomes": cfg["track"]["min_outcomes"],
        },
        "caveats": caveats,
        "engine_version": ENGINE_VERSION,
        "config_hash": cfg.hash,
        "generated_at": clock.now().isoformat(),
    }


def snapshots_for(ticker: str, limit: int = 200) -> dict:
    """Every stored estimate for one ticker with its grade, newest first."""
    t = ticker.upper()
    with session_scope() as s:
        q = (
            select(m.AppSnapshot, m.SnapshotOutcome)
            .outerjoin(m.SnapshotOutcome, m.SnapshotOutcome.snapshot_id == m.AppSnapshot.id)
            .where(m.AppSnapshot.ticker == t)
            .order_by(m.AppSnapshot.as_of.desc())
            .limit(limit)
        )
        rows = [
            {"as_of": a.as_of.isoformat(), "is_backtest": a.is_backtest, "price": a.price, "p10": a.p10,
             "p50": a.p50, "p90": a.p90, "prob_up": a.prob_up, "confidence": a.confidence,
             "trust_rating": a.trust_rating, "engine_version": a.engine_version,
             "due": (a.as_of + timedelta(days=a.horizon_days)).isoformat(),
             "outcome": None if o is None else {
                 "horizon_date": o.horizon_date.isoformat(), "realized_price": o.realized_price,
                 "realized_return": o.realized_return, "in_band": o.in_band, "abs_pct_err": o.abs_pct_err,
                 "realized_up": o.realized_up, "brier": o.brier}}
            for a, o in s.execute(q)
        ]  # fmt: skip
    df = pd.DataFrame([{**r, **(r["outcome"] or {})} for r in rows if r["outcome"]])
    return {
        "ticker": t,
        "snapshots": rows,
        "summary": metrics.summary(df.assign(ticker=t)) if len(df) else {"n": 0},
    }
