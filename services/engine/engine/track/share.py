"""Shareable snapshot links: a report frozen as it was, reachable at /s/{token}.

Sharing attaches the full report to today's live snapshot (the same row the track record grades), so the link
keeps showing what the app said that day, and later also how that estimate turned out. The first share of a day
freezes the report; later shares that day return the same link rather than silently changing what it shows.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import timedelta

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select

from engine import clock
from engine.config import ENGINE_VERSION, get_config
from engine.db import models as m
from engine.db.session import session_scope
from engine.report.builder import build_report, contexts
from engine.track.snapshots import record_live


class ShareError(Exception):
    pass


def _today_row(s, ticker: str):
    return s.scalars(
        select(m.AppSnapshot).where(
            m.AppSnapshot.ticker == ticker,
            m.AppSnapshot.as_of == clock.today(),
            m.AppSnapshot.is_backtest.is_(False),
            m.AppSnapshot.config_hash == get_config().hash,
        )
    ).first()


def share(ticker: str) -> dict:
    ctx = contexts.get(ticker, None, False)
    _ = ctx.symbol
    record_live(ctx)  # the graded snapshot for today, if the app produced a target
    with session_scope() as s:
        row = _today_row(s, ctx.ticker)
        if row is not None and (row.report_json or {}).get("report"):
            return {"token": row.share_token, "created": False, "as_of": row.as_of.isoformat()}
    report = build_report(ctx.ticker)
    with session_scope() as s:
        row = _today_row(s, ctx.ticker)
        # no target today (e.g. valuation unavailable): store an ungraded snapshot for the link
        if row is None:
            if ctx.last_price is None:
                raise ShareError("there is no price for this ticker, so there is nothing to share")
            row = m.AppSnapshot(
                id=str(uuid.uuid4()), share_token=secrets.token_urlsafe(12)[:16], ticker=ctx.ticker,
                created_at=clock.now().replace(tzinfo=None), as_of=clock.today(), price=ctx.last_price,
                engine_version=ENGINE_VERSION, config_hash=get_config().hash, is_backtest=False,
                is_synthetic=ctx.synthetic, horizon_days=int(get_config()["track"]["horizon_days"]), report_json={},
            )  # fmt: skip
            s.add(row)
        row.report_json = {**(row.report_json or {}), "report": jsonable_encoder(report)}
        return {"token": row.share_token, "created": True, "as_of": row.as_of.isoformat()}


def shared(token: str) -> dict | None:
    with session_scope() as s:
        row = s.scalars(select(m.AppSnapshot).where(m.AppSnapshot.share_token == token)).first()
        if row is None or not (row.report_json or {}).get("report"):
            return None
        o = s.get(m.SnapshotOutcome, row.id)
        return {
            "token": token,
            "ticker": row.ticker,
            "as_of": row.as_of.isoformat(),
            "created_at": row.created_at.isoformat(),
            "engine_version": row.engine_version,
            "config_hash": row.config_hash,
            "synthetic": row.is_synthetic,
            "due": (row.as_of + timedelta(days=row.horizon_days)).isoformat(),
            "target": {"price": row.price, "p10": row.p10, "p50": row.p50, "p90": row.p90},
            "outcome": None
            if o is None
            else {
                "horizon_date": o.horizon_date.isoformat(),
                "realized_price": o.realized_price,
                "in_band": o.in_band,
                "realized_return": o.realized_return,
            },  # fmt: skip
            "report": row.report_json["report"],
        }
