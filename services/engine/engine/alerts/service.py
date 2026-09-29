"""Alerts for watched stocks: evaluated by a daily job (or on demand) into an in-app inbox.

Kinds (each can be switched off globally):
- band: the price left, or came back inside, the app's 80% range from its latest stored estimate;
- trigger: a "what would change the view" threshold from the Explain section was crossed (the thresholds are
  remembered when the stock is first evaluated and re-read after each firing);
- insider_cluster: a new insider cluster buy (several insiders buying on the open market within 30 days);
- analyst_change: an upgrade or downgrade by an analyst whose Trust Score is at or above the configured level;
- filing_8k: a new 8-K filing, with its items.

Every event links to its evidence and is stored once (a dedupe key per underlying fact). The server-side watchlist
is this deployment's single list (no accounts), synced from the browser.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import delete, func, select

from engine import clock
from engine.config import get_config
from engine.db import models as m
from engine.db.session import session_scope
from engine.report.builder import contexts, run_section
from engine.report.context import ReportContext, TickerNotFound

log = logging.getLogger("engine.alerts")
GLOBAL = "*"  # rule rows with this ticker hold the global on/off switch per kind

ITEM_LABELS = {
    "1.01": "material agreement", "1.02": "agreement terminated", "1.03": "bankruptcy",
    "2.01": "acquisition or disposal completed", "2.02": "results of operations", "2.03": "new debt obligation",
    "2.05": "restructuring costs", "2.06": "impairment", "3.01": "listing notice", "4.01": "auditor change",
    "4.02": "non-reliance on prior financials", "5.02": "officer or director change", "5.07": "shareholder vote",
    "7.01": "Regulation FD disclosure", "8.01": "other events",
}  # fmt: skip


def kinds() -> dict[str, str]:
    return dict(get_config()["alerts"]["kinds"])


# ---- watchlist and rules ----------------------------------------------------------------------------------------


def watchlist() -> list[str]:
    with session_scope() as s:
        return [r.ticker for r in s.scalars(select(m.WatchlistItem).order_by(m.WatchlistItem.added_at))]


def sync_watchlist(tickers: list[str]) -> list[str]:
    """Make the server list equal to the browser's. New stocks get one rule row per kind (holding its state)."""
    want = list(dict.fromkeys(t.strip().upper() for t in tickers if t.strip()))[:50]
    today = clock.today()
    since = (today - timedelta(days=int(get_config()["alerts"]["catch_up_days"]))).isoformat()
    with session_scope() as s:
        have = {r.ticker for r in s.scalars(select(m.WatchlistItem))}
        gone = have - set(want)
        if gone:
            s.execute(delete(m.WatchlistItem).where(m.WatchlistItem.ticker.in_(gone)))
            s.execute(delete(m.Alert).where(m.Alert.ticker.in_(gone)))
        for t in want:
            if t not in have:
                s.add(m.WatchlistItem(ticker=t))
                for k in kinds():
                    s.add(m.Alert(ticker=t, kind=k, params_json={"since": since}, enabled=True))
        for k in kinds():  # global switches
            if not s.scalar(select(m.Alert).where(m.Alert.ticker == GLOBAL, m.Alert.kind == k)):
                s.add(m.Alert(ticker=GLOBAL, kind=k, params_json={}, enabled=True))
    return want


def rules() -> list[dict]:
    sync_watchlist(watchlist())  # make sure the global rows exist
    with session_scope() as s:
        on = {r.kind: r.enabled for r in s.scalars(select(m.Alert).where(m.Alert.ticker == GLOBAL))}
    return [{"kind": k, "label": lbl, "enabled": on.get(k, True)} for k, lbl in kinds().items()]


def set_rule(kind: str, enabled: bool) -> None:
    if kind not in kinds():
        raise KeyError(kind)
    rules()
    with session_scope() as s:
        r = s.scalar(select(m.Alert).where(m.Alert.ticker == GLOBAL, m.Alert.kind == kind))
        r.enabled = enabled


# ---- evaluation -------------------------------------------------------------------------------------------------


def _band(ctx: ReportContext, state: dict) -> tuple[list[dict], dict]:
    from engine.track.snapshots import record_live

    record_live(ctx)
    with session_scope() as s:
        snap = s.scalars(
            select(m.AppSnapshot)
            .where(
                m.AppSnapshot.ticker == ctx.ticker,
                m.AppSnapshot.is_backtest.is_(False),
                m.AppSnapshot.p10.is_not(None),
            )
            .order_by(m.AppSnapshot.as_of.desc())
        ).first()
        band = (snap.as_of, snap.p10, snap.p90) if snap else None
    px = ctx.last_price
    if band is None or px is None:
        return [], state
    on, p10, p90 = band
    now = "above" if px > p90 else "below" if px < p10 else "inside"
    before = state.get("band")
    events = []
    if now != before and (before is not None or now != "inside"):
        verb = {"above": "rose above", "below": "fell below", "inside": "moved back inside"}[now]
        events.append({
            "key": f"band:{now}:{ctx.as_of}",
            "title": f"{ctx.ticker} {verb} the app's 80% range",
            "detail": f"Price ${px:,.2f}; the range from the estimate of {on} is ${p10:,.2f}–${p90:,.2f}.",
            "occurred_on": ctx.last_price_date, "url": None,
        })  # fmt: skip
    return events, {**state, "band": now}


def _trigger_baseline(ctx: ReportContext) -> dict:
    ex = run_section(ctx, "explain")
    facts = {f["id"]: f["value"] for f in ex.get("facts") or []}
    out = {}
    for tr in ex.get("triggers") or []:
        tid = tr["id"]
        if tid in ("margin", "growth", "leverage", "news") and f"trigger.{tid}.threshold" in facts:
            out[tid] = {"threshold": facts[f"trigger.{tid}.threshold"], "text": tr["plain"]}
            if tid == "news":
                cur = facts.get("trigger.news.current")
                out[tid]["side"] = "above" if cur is not None and cur > out[tid]["threshold"] else "below"
        elif tid == "analysts" and "trigger.analysts.consensus" in facts:
            side = (
                "above" if facts["trigger.analysts.consensus"] > facts["trigger.analysts.price"] else "below"
            )
            out[tid] = {"side": side, "text": tr["plain"]}
    return out


def _trigger_values(ctx: ReportContext) -> dict:
    from engine.explain.triggers import _quarterly, _yoy_growth

    vals: dict = {}
    om = _quarterly(ctx, "operating_income", "revenue")
    vals["margin"] = om[-2:] if len(om) >= 2 else None
    g = _yoy_growth(ctx)
    vals["growth"] = g[-2:] if len(g) >= 2 else None
    nd, eb = ctx.fin.ttm.get("net_debt"), ctx.fin.ttm.get("ebitda")
    vals["leverage"] = nd / eb if (eb and eb > 0 and nd is not None) else None
    a = run_section(ctx, "analysts")
    tc = a.get("consensus_trusted") if a.get("status") in ("ok", "partial") else None
    vals["analysts"] = ("above" if tc > ctx.last_price else "below") if (tc and ctx.last_price) else None
    n = run_section(ctx, "news")
    vals["news"] = n.get("sentiment_30d") if n.get("status") in ("ok", "partial") else None
    return vals


def _triggers(ctx: ReportContext, state: dict) -> tuple[list[dict], dict]:
    base = state.get("triggers")
    if base is None:  # first evaluation: remember today's thresholds
        return [], {**state, "triggers": _trigger_baseline(ctx)}
    vals, events = _trigger_values(ctx), []
    for tid, b in base.items():
        v, crossed = vals.get(tid), False
        if v is None:
            continue
        if tid in ("margin", "growth"):
            crossed = all(x < b["threshold"] for x in v)
        elif tid == "leverage":
            crossed = v > b["threshold"]
        elif tid == "analysts":
            crossed = v != b["side"]
        elif tid == "news":
            crossed = (v > b["threshold"]) != (b.get("side") == "above")
        if crossed:
            events.append({
                "key": f"trigger:{tid}:{ctx.as_of}",
                "title": f"{ctx.ticker}: a trigger that would change the app's view was crossed",
                "detail": f"When this stock was first watched, the app said: “{b['text']}” That condition is now met.",
                "occurred_on": ctx.as_of, "url": None,
            })  # fmt: skip
    if events:  # the view has moved: remember the new thresholds instead of firing every day
        state = {**state, "triggers": _trigger_baseline(ctx)}
    return events, state


def _insider(ctx: ReportContext, since: date) -> list[dict]:
    o = run_section(ctx, "ownership")
    out = []
    for c in (
        ((o.get("insiders") or {}).get("clusters") or []) if o.get("status") in ("ok", "partial") else []
    ):
        if date.fromisoformat(c["end"]) > since:
            out.append({
                "key": f"insider:{c['start']}:{c['end']}",
                "title": f"{ctx.ticker}: {len(c['insiders'])} insiders bought shares within a month",
                "detail": f"Open-market purchases {c['start']} to {c['end']}, about ${c['value']:,.0f} in total, by "
                          + ", ".join(c["insiders"][:4]) + ".",
                "occurred_on": date.fromisoformat(c["end"]), "url": None,
            })  # fmt: skip
    return out


def _analysts(ctx: ReportContext, since: date) -> list[dict]:
    a = run_section(ctx, "analysts")
    if a.get("status") not in ("ok", "partial"):
        return []
    cut = float(get_config()["alerts"]["high_trust_analyst"])
    out = []
    for r in a.get("rows") or []:
        if r.get("action") not in ("upgrade", "downgrade") or (r.get("trust_score") or 0) < cut:
            continue
        if not r.get("date") or date.fromisoformat(r["date"]) <= since:
            continue
        who = r.get("analyst") or r.get("firm")
        tgt = f", target ${r['target']:,.2f}" if r.get("target") else ""
        out.append({
            "key": f"analyst:{r.get('who')}:{r['date']}",
            "title": f"{ctx.ticker}: {r['action']} by {who} (Trust Score {r['trust_score']:.0f})",
            "detail": f"{r.get('firm')}: now {r.get('rating') or 'no rating'}{tgt}.",
            "occurred_on": date.fromisoformat(r["date"]), "url": r.get("url"),
        })  # fmt: skip
    return out


def _filings(ctx: ReportContext, since: date) -> list[dict]:
    out = []
    for f in ctx.filings:
        if f.form != "8-K" or f.filed_at <= since:
            continue
        items = [f"{i} {ITEM_LABELS[i]}" if i in ITEM_LABELS else i for i in f.items if i != "9.01"]
        out.append({
            "key": f"8k:{f.accession}",
            "title": f"{ctx.ticker} filed an 8-K",
            "detail": ("Items: " + "; ".join(items) + ".") if items else "No item details in the filing index.",
            "occurred_on": f.filed_at, "url": f.url,
        })  # fmt: skip
    return out


def evaluate(tickers: list[str] | None = None) -> dict:
    """Evaluate every enabled rule for the watched stocks and store new events. Idempotent within a day."""
    today = clock.today()
    rs = {r["kind"]: r["enabled"] for r in rules()}
    tickers = tickers or watchlist()
    created = 0
    for t in tickers:
        try:
            ctx = contexts.get(t, None, False)
            _ = ctx.symbol
        except TickerNotFound:
            continue
        with session_scope() as s:
            rows = {
                r.kind: (r.id, dict(r.params_json or {}))
                for r in s.scalars(select(m.Alert).where(m.Alert.ticker == t))
            }
        for kind, (aid, params) in rows.items():
            if not rs.get(kind, False):
                continue
            since = date.fromisoformat(params.get("since", today.isoformat()))
            try:
                if kind == "band":
                    events, params = _band(ctx, params)
                elif kind == "trigger":
                    events, params = _triggers(ctx, params)
                elif kind == "insider_cluster":
                    events = _insider(ctx, since)
                elif kind == "analyst_change":
                    events = _analysts(ctx, since)
                elif kind == "filing_8k":
                    events = _filings(ctx, since)
                else:
                    events = []
            except Exception:
                log.exception("alert %s for %s failed", kind, t)
                continue
            created += _store(aid, t, kind, events)
            with session_scope() as s:
                row = s.get(m.Alert, aid)
                row.params_json = {**params, "since": today.isoformat()}
                if events:
                    row.last_fired_at = clock.now().replace(tzinfo=None)
    log.info("alerts evaluated for %d stocks: %d new events", len(tickers), created)
    return {"tickers": len(tickers), "new_events": created, "evaluated_at": clock.now().isoformat()}


def _store(alert_id: int, ticker: str, kind: str, events: list[dict]) -> int:
    n = 0
    with session_scope() as s:
        for e in events:
            key = f"{ticker}:{e['key']}"
            if s.scalar(select(m.AlertEvent.id).where(m.AlertEvent.key == key)):
                continue
            s.add(m.AlertEvent(alert_id=alert_id, ticker=ticker, kind=kind, title=e["title"], message=e["detail"],
                               url=e.get("url"), occurred_on=e.get("occurred_on"), key=key))  # fmt: skip
            n += 1
    return n


def inbox(limit: int = 200) -> dict:
    with session_scope() as s:
        rows = s.scalars(
            select(m.AlertEvent)
            .order_by(m.AlertEvent.occurred_on.desc(), m.AlertEvent.id.desc())
            .limit(limit)
        ).all()
        unread = (
            s.scalar(select(func.count()).select_from(m.AlertEvent).where(m.AlertEvent.seen.is_(False))) or 0
        )
        events = [
            {"id": r.id, "ticker": r.ticker, "kind": r.kind, "title": r.title, "detail": r.message, "url": r.url,
             "occurred_on": r.occurred_on.isoformat() if r.occurred_on else None,
             "created_at": r.fired_at.isoformat(), "read": r.seen}
            for r in rows
        ]  # fmt: skip
    return {"events": events, "unread": int(unread), "watchlist": watchlist(), "rules": rules()}


def mark_read(ids: list[int] | None = None) -> int:
    with session_scope() as s:
        q = select(m.AlertEvent).where(m.AlertEvent.seen.is_(False))
        if ids:
            q = q.where(m.AlertEvent.id.in_(ids))
        rows = s.scalars(q).all()
        for r in rows:
            r.seen = True
        return len(rows)


def unread_count() -> int:
    with session_scope() as s:
        return int(
            s.scalar(select(func.count()).select_from(m.AlertEvent).where(m.AlertEvent.seen.is_(False))) or 0
        )
