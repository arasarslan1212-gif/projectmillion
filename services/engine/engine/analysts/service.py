"""Loading analyst history and computing scores for a report.

Analysts' cross-stock records come from the local database. Opening a report ingests the subject and its peers
(sector coverage overlaps heavily), and the nightly job ingests the configured universe. Scores are computed
point-in-time for the report date and cached in memory.
"""

from __future__ import annotations

import logging
import threading
from collections import OrderedDict
from datetime import date, timedelta

from sqlalchemy import func, select

from engine.analysts.calls import Call, build_calls
from engine.analysts.scoring import PriceBook, all_scope_scores, herding, score_calls, trust_scores
from engine.data.prices import splits_of, to_frame
from engine.db import models as m
from engine.db.session import session_scope
from engine.fundamentals.sector import sector_for_sic

log = logging.getLogger("engine.analysts")

_cache: OrderedDict[tuple, dict] = OrderedDict()
_lock = threading.Lock()


def universe_tickers(data, cfg, synthetic: bool) -> list[str]:
    acfg = cfg["analysts"]
    if synthetic:
        return list(acfg["synthetic_universe"])
    if acfg.get("universe") == "index_members":
        fx = data.index_members()
        return list(fx.value or [])
    return list(acfg.get("universe") or [])


def ingest(data, tickers: list[str]) -> dict[str, str | None]:
    """Fetch (and persist) analyst actions for each ticker. Returns {ticker: failure reason or None}."""
    out = {}
    for t in dict.fromkeys(x.upper() for x in tickers if x):
        fx = data.analyst_actions(t)
        out[t] = None if fx.ok else (fx.reason or "unavailable")
    return out


def load_records(as_of: date, tickers: list[str] | None = None) -> list[dict]:
    with session_scope() as s:
        q = select(m.AnalystActionRow).where(m.AnalystActionRow.date <= as_of)
        if tickers:
            q = q.where(m.AnalystActionRow.ticker.in_([t.upper() for t in tickers]))
        rows = s.execute(q).scalars().all()
        return [
            {
                "ticker": r.ticker,
                "date": r.date,
                "firm": r.firm,
                "analyst_key": r.analyst_key,
                "analyst_name": r.analyst_name,
                "target": r.target,
                "target_prior": r.target_prior,
                "rating": r.rating,
                "rating_prior": r.rating_prior,
                "action": r.action,
                "url": r.url,
                "headline": r.headline,
                "source": r.source,
            }
            for r in rows
        ]


def _db_state() -> tuple[int, int]:
    with session_scope() as s:
        n, mx = s.execute(select(func.count(m.AnalystActionRow.id), func.max(m.AnalystActionRow.id))).one()
        return int(n or 0), int(mx or 0)


def ticker_sector(data, ticker: str, cfg) -> str:
    sym = data.resolve(ticker)
    if sym is None or sym.cik is None:
        return "unknown"
    fx = data.submissions(sym.cik)
    meta = (fx.value or {}).get("meta") if fx.value else None
    return sector_for_sic(getattr(meta, "sic", None), cfg)


def compute(ctx) -> dict:
    """Everything the analysts section needs for this ticker, memoized on the report context."""
    return ctx.section("_analyst_scores", _compute)


def prepare(data, cfg, as_of: date, synthetic: bool) -> dict:
    """All calls in the database, each scored on horizons that have passed by `as_of`. Cached per database state."""
    acfg = cfg["analysts"]
    key = (as_of, _db_state(), cfg.hash, data.p.tier, synthetic)
    with _lock:
        hit = _cache.get(key)
        if hit is not None:
            _cache.move_to_end(key)
            return hit
    records = load_records(as_of)
    tickers = sorted({r["ticker"] for r in records})
    books: dict[str, PriceBook] = {}
    splits: dict[str, list] = {}
    sectors: dict[str, str] = {}
    benches: dict[str, tuple[str | None, str | None]] = {}
    bcfg = cfg["benchmarks"]["synthetic"] if synthetic else cfg["benchmarks"]
    for t in tickers:
        ph = data.prices(t).value
        sec = ticker_sector(data, t, cfg)
        splits[t] = splits_of(ph)
        b = PriceBook.from_frame(to_frame(ph, as_of))
        if b is not None:
            books[t] = b
        sectors[t] = sec
        benches[t] = (bcfg["market"], bcfg["sector_etfs"].get(sec))
    for bt in {x for pair in benches.values() for x in pair if x}:
        if bt not in books:
            b = PriceBook.from_frame(to_frame(data.prices(bt).value, as_of))
            if b is not None:
                books[bt] = b
    calls = build_calls(records, splits, int(acfg["grade_join_days"]), int(acfg["rating_stale_months"]) * 30)
    df = score_calls(calls, books, benches, as_of, acfg, sectors)
    result = {
        "calls": calls,
        "df": df,
        "herding": herding(calls, int(acfg["stale_months"]) * 30),
        "sectors": sectors,
        "n_records": len(records),
        "n_tickers": len({c.ticker for c in calls}),
        "n_calls_scored": int(df["scored"].sum()) if not df.empty else 0,
    }
    with _lock:
        _cache[key] = result
        while len(_cache) > 8:
            _cache.popitem(last=False)
    return result


def _compute(ctx) -> dict:
    cfg = ctx.cfg
    data = ctx.data
    try:
        from engine.analysis.trust_rating import _safe_section

        p = _safe_section(ctx, "peers") or {}
        peers = [r["ticker"] for r in p.get("rows", []) if not r.get("is_subject")]
    except Exception:  # peers only widen the cross-stock history; never a requirement
        peers = []
    wanted = [ctx.ticker, *peers]
    if ctx.synthetic:
        wanted += universe_tickers(data, cfg, True)
    failures = ingest(data, wanted)
    prep = prepare(data, cfg, ctx.as_of, ctx.synthetic)
    df, acfg = prep["df"], cfg["analysts"]
    sector = prep["sectors"].get(ctx.ticker, ctx.sector.sector)
    return {
        "calls": [c for c in prep["calls"] if c.ticker == ctx.ticker],
        "analysts": trust_scores(df, ctx.ticker, sector, acfg, "analyst") if not df.empty else {},
        "firms": trust_scores(df, ctx.ticker, sector, acfg, "firm") if not df.empty else {},
        "herding": prep["herding"],
        "n_records": prep["n_records"],
        "n_tickers": prep["n_tickers"],
        "n_calls_scored": prep["n_calls_scored"],
        "ingest_failures": {k: v for k, v in failures.items() if v},
        "calls_frame": df,
    }


def score_and_store(data, cfg, as_of: date, synthetic: bool) -> dict:
    """Nightly job body: ingest the universe, then store every analyst's and firm's all-stock score."""
    ingest(data, universe_tickers(data, cfg, synthetic))
    prep = prepare(data, cfg, as_of, synthetic)
    df, acfg = prep["df"], cfg["analysts"]
    if df.empty:
        return {"analysts": 0, "firms": 0}
    out = {}
    with session_scope() as s:
        for level, model, col in (("analyst", m.AnalystScore, "analyst_key"), ("firm", m.FirmScore, "firm")):
            rows = all_scope_scores(df, acfg, level)
            for who, r in rows.items():
                h = prep["herding"].get(who) if level == "analyst" else None
                s.merge(
                    model(
                        **{col: who},
                        scope="all",
                        n_calls=r["n_scored"],
                        hit_rate=r["metrics"]["hit_rate"],
                        mape=r["metrics"]["mape"],
                        excess_3m=r["excess"].get("3m"),
                        excess_6m=r["excess"].get("6m"),
                        excess_12m=r["excess"].get("12m"),
                        bullish_bias=r["metrics"]["optimism_bias"],
                        herding=h["value"] if h else None,
                        raw_score=r["raw_score"],
                        trust_score=r["score"],
                        config_hash=cfg.hash,
                    )
                )
            out[level + "s"] = len(rows)
    return out


def active_targets(calls: list[Call], on: date, stale_days: int) -> dict[str, Call]:
    """Latest call with a target per analyst (or firm) as of `on`, excluding stale ones."""
    latest: dict[str, Call] = {}
    dropped: dict[str, date] = {}
    for c in calls:
        if c.date > on:
            continue
        if c.action == "termination":
            dropped[c.who] = max(c.date, dropped.get(c.who, c.date))
        elif c.target is not None:
            prev = latest.get(c.who)
            if prev is None or c.date >= prev.date:
                latest[c.who] = c
    return {
        k: c
        for k, c in latest.items()
        if (on - c.date).days <= stale_days and not (k in dropped and dropped[k] >= c.date)
    }


def month_ends(as_of: date, months: int) -> list[date]:
    out = []
    d = as_of.replace(day=1) - timedelta(days=1)
    for _ in range(months):
        out.append(d)
        d = d.replace(day=1) - timedelta(days=1)
    return sorted(out) + [as_of]
