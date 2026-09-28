"""Cached access to provider data.

Every fetch goes through `_cached`, which:
- serves a fresh cached payload (provider_cache table + in-process LRU) when within its TTL,
- otherwise calls the provider, stores the normalized payload and persists rows into the domain tables,
- on provider failure serves the stale payload (flagged) if one exists, or returns a `Fetched` with
  `status="missing"` and a user-facing reason. Failures never propagate into report rendering.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, TypeAdapter
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from engine import clock
from engine.config import get_config
from engine.db import models as m
from engine.db.session import session_scope
from engine.fundamentals.concepts import LINE_ITEMS
from engine.http.client import ProviderError
from engine.providers.models import (
    AnalystAction,
    CompanyMeta,
    CompanyProfile,
    EarningsEvent,
    EmployeeCount,
    Estimate,
    Executive,
    Fact,
    Filing,
    InsiderTransaction,
    InstitutionalHolding,
    MacroSeries,
    NewsItem,
    PriceHistory,
    Quote,
    RecommendationTrend,
    Segment,
    ShortInterestPoint,
    SymbolInfo,
    TargetConsensus,
)
from engine.providers.registry import Providers, get_providers

T = TypeVar("T")


@dataclass
class Fetched(Generic[T]):
    value: T | None
    source: str
    fetched_at: datetime | None
    status: str = "ok"  # ok | stale | missing
    reason: str | None = None

    @property
    def ok(self) -> bool:
        return self.value is not None

    def meta(self) -> dict:
        return {
            "source": self.source,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "status": self.status,
            "reason": self.reason,
        }


class _Lru:
    def __init__(self, cap: int = 512) -> None:
        self.cap = cap
        self.d: OrderedDict[str, tuple[datetime, datetime, Any]] = OrderedDict()
        self.lock = threading.Lock()

    def get(self, key: str) -> tuple[datetime, Any] | None:
        with self.lock:
            v = self.d.get(key)
            if v is None:
                return None
            expires, fetched, val = v
            if expires < datetime.now(UTC):
                del self.d[key]
                return None
            self.d.move_to_end(key)
            return fetched, val

    def put(self, key: str, expires: datetime, fetched: datetime, val: Any) -> None:
        with self.lock:
            self.d[key] = (expires, fetched, val)
            self.d.move_to_end(key)
            while len(self.d) > self.cap:
                self.d.popitem(last=False)

    def clear(self) -> None:
        with self.lock:
            self.d.clear()


def _dump(v: Any) -> Any:
    if isinstance(v, BaseModel):
        return v.model_dump(mode="json")
    if isinstance(v, list):
        return [_dump(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _dump(x) for k, x in v.items()}
    if isinstance(v, (date, datetime)):
        return v.isoformat()
    return v


class DataService:
    def __init__(self, providers: Providers | None = None) -> None:
        self.p = providers or get_providers()
        self.cfg = get_config()
        self.mem = _Lru()
        self._locks: dict[str, threading.Lock] = {}
        self._locks_lock = threading.Lock()

    # ---------------------------------------------------------------------------------
    def _ttl(self, name: str) -> timedelta:
        return timedelta(seconds=int(self.cfg.get(f"data.ttl_seconds.{name}", 3600)))

    def _label(self, source: str) -> str:
        return f"{source} (SYNTHETIC)" if clock.is_synthetic() else source

    def _key_lock(self, key: str) -> threading.Lock:
        with self._locks_lock:
            if key not in self._locks:
                self._locks[key] = threading.Lock()
            return self._locks[key]

    def _cached(
        self,
        key: str,
        dataset: str,
        source: str,
        ttl: str,
        loader: Callable[[], Any],
        adapter: TypeAdapter | None = None,
        persist: Callable[[Any], None] | None = None,
    ) -> Fetched:
        label = self._label(source)
        hit = self.mem.get(key)
        if hit is not None:
            fetched, val = hit
            return Fetched(val, label, fetched)
        with self._key_lock(key):
            hit = self.mem.get(key)
            if hit is not None:
                return Fetched(hit[1], label, hit[0])
            now = datetime.now(UTC).replace(tzinfo=None)
            with session_scope() as s:
                row = s.get(m.ProviderCache, key)
                if row is not None and row.expires_at > now and row.error is None:
                    val = adapter.validate_python(row.payload_json) if adapter else row.payload_json
                    self.mem.put(
                        key, row.expires_at.replace(tzinfo=UTC), row.fetched_at.replace(tzinfo=UTC), val
                    )
                    return Fetched(val, label, row.fetched_at.replace(tzinfo=UTC))
                if row is not None and row.error is not None and row.expires_at > now:
                    stale = None
                    return Fetched(stale, label, None, "missing", row.error)
                stale_row = row
            try:
                val = loader()
            except ProviderError as exc:
                reason = exc.user_reason()
                if stale_row is not None and stale_row.error is None:
                    val = (
                        adapter.validate_python(stale_row.payload_json) if adapter else stale_row.payload_json
                    )
                    return Fetched(
                        val,
                        label,
                        stale_row.fetched_at.replace(tzinfo=UTC),
                        "stale",
                        f"showing cached data; refresh failed: {reason}",
                    )
                with session_scope() as s:
                    s.merge(
                        m.ProviderCache(
                            key=key,
                            provider=source,
                            dataset=dataset,
                            fetched_at=now,
                            expires_at=now + self._ttl("error"),
                            payload_json={},
                            error=reason,
                        )
                    )
                return Fetched(None, label, None, "missing", reason)
            expires = now + self._ttl(ttl)
            payload = _dump(val)
            with session_scope() as s:
                s.merge(
                    m.ProviderCache(
                        key=key,
                        provider=source,
                        dataset=dataset,
                        fetched_at=now,
                        expires_at=expires,
                        payload_json=payload,
                        error=None,
                    )
                )
            if persist is not None:
                try:
                    persist(val)
                except Exception:  # persistence is best-effort; the report still renders
                    pass
            self.mem.put(key, expires.replace(tzinfo=UTC), now.replace(tzinfo=UTC), val)
            return Fetched(val, label, now.replace(tzinfo=UTC))

    def invalidate(self, prefix: str) -> None:
        self.mem.clear()
        with session_scope() as s:
            s.execute(delete(m.ProviderCache).where(m.ProviderCache.key.like(f"{prefix}%")))

    # ---- symbols & filings ------------------------------------------------------------
    def symbols(self) -> Fetched[list[SymbolInfo]]:
        return self._cached(
            "symbols",
            "symbols",
            self.p.symbols.name,
            "symbols",
            self.p.symbols.all_symbols,
            TypeAdapter(list[SymbolInfo]),
        )

    def resolve(self, ticker: str) -> SymbolInfo | None:
        syms = self.symbols().value or []
        t = ticker.upper().strip()
        for s in syms:
            if s.ticker == t:
                return s
        alt = t.replace(".", "-")
        for s in syms:
            if s.ticker == alt:
                return s
        return None

    def search(self, q: str, limit: int = 10) -> list[SymbolInfo]:
        syms = self.symbols().value or []
        qu = q.upper().strip()
        if not qu:
            return []
        exact = [s for s in syms if s.ticker == qu]
        prefix = [s for s in syms if s.ticker.startswith(qu) and s.ticker != qu]
        words = qu.split()
        by_name = [
            s for s in syms if all(w in s.name.upper() for w in words) and s not in exact and s not in prefix
        ]
        prefix.sort(key=lambda s: (len(s.ticker), s.ticker))
        by_name.sort(key=lambda s: (not s.name.upper().startswith(qu), len(s.name)))
        return (exact + prefix + by_name)[:limit]

    def submissions(self, cik: int) -> Fetched[dict]:
        def load():
            meta = self.p.filings.company_meta(cik)
            filings = self.p.filings.filings(cik)
            return {"meta": meta, "filings": filings}

        def persist(v):
            with session_scope() as s:
                for f in v["filings"]:
                    s.merge(
                        m.FilingRow(
                            accn=f.accession,
                            cik=f.cik,
                            form=f.form,
                            filed_at=f.filed_at,
                            report_date=f.report_date,
                            items=",".join(f.items),
                            primary_doc=f.primary_doc,
                            url=f.url,
                        )
                    )

        fx = self._cached(
            f"submissions:{cik}",
            "submissions",
            self.p.filings.name,
            "submissions",
            load,
            TypeAdapter(dict[str, Any]),
            persist,
        )
        if fx.value is not None and isinstance(fx.value.get("meta"), dict):
            fx.value = {
                "meta": CompanyMeta.model_validate(fx.value["meta"]),
                "filings": TypeAdapter(list[Filing]).validate_python(fx.value["filings"]),
            }
        return fx

    def facts(self, cik: int, filings: list[Filing] | None = None) -> Fetched[list[Fact]]:
        """Company facts, re-fetched whenever a new 10-K/10-Q/amendment appears in the filings list."""
        latest = ""
        if filings:
            periodic = [f for f in filings if f.form in ("10-K", "10-Q", "10-K/A", "10-Q/A", "20-F", "40-F")]
            if periodic:
                latest = max(periodic, key=lambda f: (f.filed_at, f.accession)).accession

        def persist(facts: list[Fact]) -> None:
            wanted = {c for li in LINE_ITEMS.values() for c in li.concepts}
            rows = [
                {
                    "cik": cik,
                    "taxonomy": f.taxonomy,
                    "concept": f.concept,
                    "unit": f.unit,
                    "period_start": f.start,
                    "period_end": f.end,
                    "fy": f.fy,
                    "fp": f.fp,
                    "form": f.form,
                    "accn": f.accn,
                    "filed_at": f.filed,
                    "value": f.value,
                    "frame": f.frame,
                }
                for f in facts
                if f.concept in wanted
            ]
            with session_scope() as s:
                s.execute(delete(m.FundamentalFact).where(m.FundamentalFact.cik == cik))
                if rows:
                    s.execute(m.FundamentalFact.__table__.insert(), rows)

        return self._cached(
            f"facts:{cik}:{latest}",
            "fundamentals",
            self.p.fundamentals.name,
            "fundamentals",
            lambda: self.p.fundamentals.company_facts(cik),
            TypeAdapter(list[Fact]),
            persist,
        )

    def document_text(self, filing: Filing) -> Fetched[str]:
        return self._cached(
            f"doc:{filing.accession}",
            "documents",
            self.p.filings.name,
            "documents",
            lambda: self.p.filings.document_text(filing),
            TypeAdapter(str),
        )

    # ---- prices ---------------------------------------------------------------------
    def prices(self, ticker: str, days: int | None = None) -> Fetched[PriceHistory]:
        end = clock.today()
        years = int(self.cfg.get("data.price_history_years", 12))
        start = end - timedelta(days=days) if days else date(end.year - years, 1, 1)
        t = ticker.upper()

        def persist(h: PriceHistory) -> None:
            with session_scope() as s:
                dialect = s.bind.dialect.name if s.bind else "sqlite"
                rows = [
                    {
                        "ticker": t,
                        "date": b.date,
                        "open": b.open,
                        "high": b.high,
                        "low": b.low,
                        "close": b.close,
                        "adj_close": b.adj_close,
                        "volume": b.volume,
                        "source": h.source,
                    }
                    for b in h.bars
                ]
                if not rows:
                    return
                if dialect == "sqlite":
                    stmt = sqlite_insert(m.Price).values(rows)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["ticker", "date"],
                        set_={"close": stmt.excluded.close, "adj_close": stmt.excluded.adj_close},
                    )
                    s.execute(stmt)
                else:
                    from sqlalchemy.dialects.postgresql import insert as pg_insert

                    stmt = pg_insert(m.Price).values(rows)
                    stmt = stmt.on_conflict_do_update(
                        index_elements=["ticker", "date"],
                        set_={"close": stmt.excluded.close, "adj_close": stmt.excluded.adj_close},
                    )
                    s.execute(stmt)

        return self._cached(
            f"prices:{t}:{start.isoformat()}:{end.isoformat()}",
            "daily_bars",
            self.p.prices.name,
            "daily_bars",
            lambda: self.p.prices.history(t, start, end),
            TypeAdapter(PriceHistory),
            persist,
        )

    def quote(self, ticker: str) -> Fetched[Quote]:
        if self.p.quote is None:
            return Fetched(
                None, "end-of-day", None, "missing", "no intraday quote on this data tier; using last close"
            )
        return self._cached(
            f"quote:{ticker.upper()}",
            "quote",
            self.p.quote.name,
            "quote",
            lambda: self.p.quote.quote(ticker),
            TypeAdapter(Quote | None),
        )

    # ---- profile ----------------------------------------------------------------------
    def _optional(self, provider, key: str, dataset: str, ttl: str, fn: Callable, ta: TypeAdapter) -> Fetched:
        if provider is None:
            return Fetched(
                None, "—", None, "missing", f"{dataset} is not available on the {self.p.tier} data tier"
            )
        return self._cached(key, dataset, provider.name, ttl, fn, ta)

    def profile(self, ticker: str) -> Fetched[CompanyProfile]:
        return self._optional(
            self.p.profile,
            f"profile:{ticker}",
            "company profile",
            "profile",
            lambda: self.p.profile.profile(ticker),
            TypeAdapter(CompanyProfile | None),
        )

    def executives(self, ticker: str) -> Fetched[list[Executive]]:
        return self._optional(
            self.p.profile,
            f"execs:{ticker}",
            "executives",
            "profile",
            lambda: self.p.profile.executives(ticker),
            TypeAdapter(list[Executive]),
        )

    def employees(self, ticker: str) -> Fetched[list[EmployeeCount]]:
        return self._optional(
            self.p.profile,
            f"employees:{ticker}",
            "employee history",
            "profile",
            lambda: self.p.profile.employee_history(ticker),
            TypeAdapter(list[EmployeeCount]),
        )

    def segments(self, ticker: str) -> Fetched[list[Segment]]:
        return self._optional(
            self.p.profile,
            f"segments:{ticker}",
            "revenue segments",
            "profile",
            lambda: self.p.profile.segments(ticker),
            TypeAdapter(list[Segment]),
        )

    def provider_peers(self, ticker: str) -> Fetched[list[str]]:
        return self._optional(
            self.p.profile,
            f"peers:{ticker}",
            "peer list",
            "profile",
            lambda: self.p.profile.peers(ticker),
            TypeAdapter(list[str]),
        )

    def shares_float(self, ticker: str) -> Fetched[dict]:
        return self._optional(
            self.p.profile,
            f"float:{ticker}",
            "share float",
            "profile",
            lambda: self.p.profile.shares_float(ticker),
            TypeAdapter(dict | None),
        )

    def index_members(self) -> Fetched[list[str]]:
        return self._optional(
            self.p.profile,
            "index:sp500",
            "index membership",
            "universe",
            lambda: sorted(self.p.profile.index_membership()),
            TypeAdapter(list[str]),
        )

    def screener(self, sector: str | None, industry: str | None) -> Fetched[list[dict]]:
        return self._optional(
            self.p.screener,
            f"screener:{sector}:{industry}",
            "screener",
            "universe",
            lambda: self.p.screener.screener(sector, industry),
            TypeAdapter(list[dict]),
        )

    # ---- estimates & earnings -----------------------------------------------------------
    def estimates(self, ticker: str) -> Fetched[list[Estimate]]:
        def persist(ests: list[Estimate]) -> None:
            today = clock.today()
            with session_scope() as s:
                for e in ests:
                    s.merge(
                        m.EstimateRevision(
                            ticker=ticker.upper(),
                            period_end=e.period_end,
                            metric=f"{e.period_type}:{e.metric}",
                            as_of=today,
                            mean=e.mean,
                            source=e.source,
                        )
                    )

        if self.p.estimates is None:
            return Fetched(
                None,
                "—",
                None,
                "missing",
                f"consensus estimates are not available on the {self.p.tier} data tier",
            )
        return self._cached(
            f"estimates:{ticker}",
            "estimates",
            self.p.estimates.name,
            "estimates",
            lambda: self.p.estimates.estimates(ticker),
            TypeAdapter(list[Estimate]),
            persist,
        )

    def estimate_history(self, ticker: str) -> list[dict]:
        with session_scope() as s:
            rows = (
                s.execute(select(m.EstimateRevision).where(m.EstimateRevision.ticker == ticker.upper()))
                .scalars()
                .all()
            )
            return [
                {"period_end": r.period_end, "metric": r.metric, "as_of": r.as_of, "mean": r.mean}
                for r in rows
            ]

    def earnings(self, ticker: str) -> Fetched[list[EarningsEvent]]:
        last: Fetched = Fetched(None, "—", None, "missing", "no earnings provider on this tier")
        for prov in self.p.earnings:
            fx = self._cached(
                f"earnings:{prov.provider_key}:{ticker}",
                "earnings",
                prov.name,
                "earnings",
                lambda prov=prov: prov.earnings(ticker),
                TypeAdapter(list[EarningsEvent]),
            )
            if fx.ok and fx.value:
                return fx
            last = fx
        return last

    def earnings_calendar(self, ticker: str) -> Fetched[list[EarningsEvent]]:
        fh = self.p.consensus
        if fh is None:
            return Fetched(None, "—", None, "missing", "no earnings calendar provider")
        today = clock.today()
        return self._cached(
            f"ecal:{ticker}:{today}",
            "earnings",
            fh.name,
            "earnings",
            lambda: fh.earnings_calendar(ticker, today - timedelta(days=400), today + timedelta(days=120)),
            TypeAdapter(list[EarningsEvent]),
        )

    # ---- analysts ---------------------------------------------------------------------
    def analyst_actions(self, ticker: str) -> Fetched[list[AnalystAction]]:
        prov = self.p.analysts
        if prov is None:
            return Fetched(
                None,
                "—",
                None,
                "missing",
                f"analyst-level history is not available on the {self.p.tier} data tier",
            )

        def persist(actions: list[AnalystAction]) -> None:
            from engine.analysts.ratings import normalize_rating

            with session_scope() as s:
                existing = set(
                    s.execute(
                        select(m.AnalystActionRow.source_uid).where(
                            m.AnalystActionRow.ticker == ticker.upper()
                        )
                    )
                    .scalars()
                    .all()
                )
                for a in actions:
                    if a.source_uid in existing:
                        continue
                    s.add(
                        m.AnalystActionRow(
                            ticker=a.ticker,
                            analyst_key=analyst_key(a),
                            analyst_name=a.analyst_name,
                            firm=a.firm,
                            date=a.date,
                            action=a.action,
                            rating=a.rating,
                            rating_prior=a.rating_prior,
                            rating_norm=normalize_rating(a.rating),
                            target=a.target,
                            target_prior=a.target_prior,
                            price_when_posted=a.price_when_posted,
                            url=a.url,
                            source=a.source,
                            source_uid=a.source_uid,
                        )
                    )
                    existing.add(a.source_uid)

        return self._cached(
            f"analysts:{prov.provider_key}:{ticker}",
            "analyst_actions",
            prov.name,
            "analyst_actions",
            lambda: prov.actions(ticker),
            TypeAdapter(list[AnalystAction]),
            persist,
        )

    def recommendation_trends(self, ticker: str) -> Fetched[list[RecommendationTrend]]:
        prov = self.p.consensus
        if prov is None:
            return Fetched(None, "—", None, "missing", "no consensus provider configured")
        return self._cached(
            f"rectrend:{ticker}",
            "analyst_actions",
            prov.name,
            "analyst_actions",
            lambda: prov.recommendation_trends(ticker),
            TypeAdapter(list[RecommendationTrend]),
        )

    def target_consensus(self, ticker: str) -> Fetched[TargetConsensus]:
        prov = self.p.target_consensus
        if prov is None:
            return Fetched(None, "—", None, "missing", "no target consensus provider on this tier")
        return self._cached(
            f"tcons:{ticker}",
            "analyst_actions",
            prov.name,
            "analyst_actions",
            lambda: prov.target_consensus(ticker),
            TypeAdapter(TargetConsensus | None),
        )

    # ---- news -------------------------------------------------------------------------
    def news(self, ticker: str) -> Fetched[list[NewsItem]]:
        today = clock.today()
        start = today - timedelta(days=int(self.cfg.get("data.news_lookback_days", 365)))
        items: list[NewsItem] = []
        sources, reasons, fetched_at = [], [], None
        for prov in self.p.news:
            fx = self._cached(
                f"news:{prov.provider_key}:{ticker}:{today}",
                "news",
                prov.name,
                "news",
                lambda prov=prov: prov.news(ticker, start, today),
                TypeAdapter(list[NewsItem]),
            )
            if fx.value:
                items.extend(fx.value)
                sources.append(fx.source)
                fetched_at = fx.fetched_at
            elif fx.reason:
                reasons.append(f"{prov.name}: {fx.reason}")
        for it in items:
            if it.published_at.tzinfo is None:
                it.published_at = it.published_at.replace(tzinfo=UTC)
        if not sources:
            return Fetched(
                None,
                ", ".join(p.name for p in self.p.news) or "—",
                None,
                "missing",
                "; ".join(reasons) or "no news provider configured",
            )
        return Fetched(items, ", ".join(sources), fetched_at, "ok", "; ".join(reasons) or None)

    # ---- ownership ----------------------------------------------------------------------
    def insiders(self, ticker: str, cik: int) -> Fetched[list[InsiderTransaction]]:
        since = clock.today() - timedelta(days=int(self.cfg.get("data.insider_lookback_days", 730)))
        return self._cached(
            f"insiders:{ticker}:{since}",
            "insiders",
            self.p.insiders.name,
            "insiders",
            lambda: self.p.insiders.insider_transactions(ticker, cik, since),
            TypeAdapter(list[InsiderTransaction]),
        )

    def institutions(self, ticker: str) -> Fetched[list[InstitutionalHolding]]:
        return self._optional(
            self.p.institutions,
            f"inst:{ticker}",
            "institutional holders",
            "institutions",
            lambda: self.p.institutions.institutional_holders(ticker),
            TypeAdapter(list[InstitutionalHolding]),
        )

    def short_interest(self, ticker: str) -> Fetched[list[ShortInterestPoint]]:
        return self._cached(
            f"si:{ticker}",
            "short_interest",
            self.p.short_interest.name,
            "short_interest",
            lambda: self.p.short_interest.short_interest(ticker),
            TypeAdapter(list[ShortInterestPoint]),
        )

    # ---- macro & universe ---------------------------------------------------------------
    def macro(self, series_id: str, years: int = 15) -> Fetched[MacroSeries]:
        today = clock.today()
        start = date(today.year - years, 1, 1)
        return self._cached(
            f"macro:{series_id}:{start}:{today}",
            "macro",
            self.p.macro.name,
            "macro",
            lambda: self.p.macro.series(series_id, start),
            TypeAdapter(MacroSeries),
        )

    def universe_ciks(self, sic: int) -> Fetched[list[int]]:
        return self._cached(
            f"sic:{sic}",
            "universe",
            self.p.universe.name,
            "universe",
            lambda: self.p.universe.ciks_for_sic(sic),
            TypeAdapter(list[int]),
        )

    def frame_item(self, item: str, period: str) -> Fetched[dict[int, float]]:
        """Coalesce a line item across its alternative concepts for one SEC frame period."""
        li = LINE_ITEMS[item]

        def load() -> dict[int, float]:
            out: dict[int, float] = {}
            errors = []
            for concept in li.concepts:
                try:
                    pts = self.p.universe.frame(concept, li.unit, period, li.taxonomy)
                except ProviderError as exc:
                    if exc.kind in ("not_found", "fixture_missing"):
                        continue
                    errors.append(exc)
                    continue
                for pt in pts:
                    out.setdefault(pt.cik, pt.value)
            if not out and errors:
                raise errors[0]
            return out

        fx = self._cached(
            f"frame:{item}:{period}",
            "frames",
            self.p.universe.name,
            "frames",
            load,
            TypeAdapter(dict[int, float]),
        )
        return fx


def analyst_key(a: AnalystAction) -> str | None:
    if a.analyst_id:
        return f"id:{a.analyst_id}"
    if a.analyst_name:
        return f"name:{a.analyst_name.strip().lower()}|{a.firm.strip().lower()}"
    return None


_service: DataService | None = None
_service_lock = threading.Lock()


def get_data() -> DataService:
    global _service
    with _service_lock:
        if _service is None:
            _service = DataService()
        return _service


def reset_data(svc: DataService | None = None) -> None:
    global _service
    with _service_lock:
        _service = svc
