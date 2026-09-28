"""Snapshots: what the app said about a stock on a date, stored so it can be graded later.

A live report stores at most one snapshot per ticker per day and config. Backtest snapshots come from point-in-time
reports built for past dates and are flagged `is_backtest`. Snapshots keep the displayed numbers and, in
`report_json`, the raw model outputs (before recalibration) and each valuation method's 12-month figure, so the
track record can grade the model, the calibration and each method separately.
"""

from __future__ import annotations

import logging
import secrets
import uuid

from sqlalchemy import delete, select

from engine import clock
from engine.config import ENGINE_VERSION, get_config
from engine.db import models as m
from engine.db.session import session_scope
from engine.report.context import ReportContext

log = logging.getLogger("engine.track")


def bucket(value: float | None, edges: list[float], labels=("low", "mid", "high")) -> str | None:
    if value is None:
        return None
    for edge, label in zip(edges, labels, strict=False):
        if value < edge:
            return label
    return labels[len(edges)]


def vol_bucket(vol: float | None) -> str | None:
    return bucket(vol, get_config()["track"]["vol_buckets"])


def size_bucket(mcap: float | None) -> str | None:
    return bucket(mcap, get_config()["track"]["size_buckets"], ("small", "mid", "large"))


def snapshot_row(ctx: ReportContext, is_backtest: bool) -> dict | None:
    """The snapshot for a context, or None when the app produced no target for it."""
    from engine.report.builder import run_section

    v = run_section(ctx, "valuation")
    if v.get("status") != "ok":
        return None
    t = run_section(ctx, "trust")
    tg, sg, conf = v["target"], v["sigma"], v["confidence"]
    trust_ok = t.get("status") == "ok"
    pillars = (
        {p["id"]: p["score"] for p in t.get("pillars", []) if p.get("score") is not None}
        if trust_ok
        else None
    )
    cfg = get_config()
    return {
        "ticker": ctx.ticker,
        "as_of": ctx.as_of,
        "price": v["price"],
        "p10": tg["p10"],
        "p50": tg["p50"],
        "p90": tg["p90"],
        "prob_up": tg["prob_up"],
        "confidence": conf["score"],
        "trust_rating": t.get("score") if trust_ok else None,
        "sector": ctx.sector.sector,
        "size_bucket": size_bucket(ctx.market_cap),
        "vol_bucket": vol_bucket(sg.get("market")),
        "pillars_json": pillars,
        "engine_version": ENGINE_VERSION,
        "config_hash": cfg.hash,
        "is_backtest": is_backtest,
        "is_synthetic": ctx.synthetic,
        "horizon_days": int(cfg["track"]["horizon_days"]),
        "report_json": {
            "profile": ctx.sector.profile,
            "profile_label": ctx.sector.profile_label,
            "sector_label": ctx.sector.sector_label,
            "trust_grade": t.get("grade") if trust_ok else None,
            "confidence_level": conf["level"],
            "implied_return": tg["implied_return"],
            "sigma_total": sg["total"],
            "sigma_total_raw": sg.get("total_raw", sg["total"]),
            "sigma_market": sg.get("market"),
            "prob_up_raw": tg.get("prob_up_raw", tg["prob_up"]),
            "calibration_id": (tg.get("calibration") or {}).get("id"),
            "market_cap": ctx.market_cap,
            "methods": [
                {"id": b["id"], "label": b["label"], "target_12m": b["target_12m"], "weight": b["weight"]}
                for b in v["blend"]
            ],
        },
    }


def insert(rows: list[dict], replace_backtest: bool = True) -> int:
    """Store snapshot rows. Backtest rows replace earlier backtest rows for the same ticker, date and config."""
    if not rows:
        return 0
    with session_scope() as s:
        for r in rows:
            if r["is_backtest"] and replace_backtest:
                old = select(m.AppSnapshot.id).where(
                    m.AppSnapshot.ticker == r["ticker"],
                    m.AppSnapshot.as_of == r["as_of"],
                    m.AppSnapshot.is_backtest.is_(True),
                    m.AppSnapshot.config_hash == r["config_hash"],
                )
                ids = list(s.scalars(old))
                if ids:
                    s.execute(delete(m.SnapshotOutcome).where(m.SnapshotOutcome.snapshot_id.in_(ids)))
                    s.execute(delete(m.AppSnapshot).where(m.AppSnapshot.id.in_(ids)))
            s.add(
                m.AppSnapshot(
                    id=str(uuid.uuid4()),
                    share_token=secrets.token_urlsafe(12)[:16],
                    created_at=clock.now().replace(tzinfo=None),
                    **r,
                )
            )
    return len(rows)


def record_live(ctx: ReportContext) -> str | None:
    """Snapshot a live report once per ticker, day and config. Point-in-time views are never snapshotted."""
    if ctx.pit or ctx.as_of != clock.today() or not get_config()["track"]["snapshot_on_report"]:
        return None
    cfg_hash = get_config().hash
    with session_scope() as s:
        hit = s.scalar(
            select(m.AppSnapshot.id).where(
                m.AppSnapshot.ticker == ctx.ticker,
                m.AppSnapshot.as_of == ctx.as_of,
                m.AppSnapshot.is_backtest.is_(False),
                m.AppSnapshot.config_hash == cfg_hash,
            )
        )
    if hit:
        return hit
    row = snapshot_row(ctx, is_backtest=False)
    if row is None:
        return None
    insert([row])
    log.info("snapshot stored for %s as of %s", ctx.ticker, ctx.as_of)
    return "new"
