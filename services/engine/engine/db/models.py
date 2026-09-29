"""Database schema (SQLAlchemy 2). Migrations live in services/engine/alembic."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def _utcnow() -> datetime:
    """Naive UTC timestamp (columns are timezone-naive and always hold UTC)."""
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"
    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    cik: Mapped[int | None] = mapped_column(Integer, index=True)
    name: Mapped[str] = mapped_column(String(300))
    exchange: Mapped[str | None] = mapped_column(String(40))
    sic: Mapped[int | None] = mapped_column(Integer)
    sic_desc: Mapped[str | None] = mapped_column(String(200))
    sector: Mapped[str | None] = mapped_column(String(60))
    industry: Mapped[str | None] = mapped_column(String(200))
    profile_json: Mapped[dict | None] = mapped_column(JSON)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Price(Base):
    __tablename__ = "prices"
    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    adj_close: Mapped[float] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(40))


class CorporateActionRow(Base):
    __tablename__ = "corporate_actions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(16))
    value: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(40))
    __table_args__ = (UniqueConstraint("ticker", "date", "kind", name="uq_action"),)


class FundamentalFact(Base):
    __tablename__ = "fundamentals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cik: Mapped[int] = mapped_column(Integer)
    taxonomy: Mapped[str] = mapped_column(String(20))
    concept: Mapped[str] = mapped_column(String(200))
    unit: Mapped[str] = mapped_column(String(40))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    fy: Mapped[int | None] = mapped_column(Integer)
    fp: Mapped[str | None] = mapped_column(String(4))
    form: Mapped[str | None] = mapped_column(String(20))
    accn: Mapped[str | None] = mapped_column(String(30))
    filed_at: Mapped[date] = mapped_column(Date)
    value: Mapped[float] = mapped_column(Float)
    frame: Mapped[str | None] = mapped_column(String(20))
    __table_args__ = (Index("ix_fund_pit", "cik", "concept", "period_end", "filed_at"),)


class EstimateRow(Base):
    __tablename__ = "estimates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    period_end: Mapped[date] = mapped_column(Date)
    period_type: Mapped[str] = mapped_column(String(10))
    metric: Mapped[str] = mapped_column(String(20))
    mean: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    n: Mapped[int | None] = mapped_column(Integer)
    as_of: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(40))


class EstimateRevision(Base):
    """Daily snapshot of consensus, so 7/30/60/90-day revisions can be computed over time."""

    __tablename__ = "estimate_revisions"
    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    period_end: Mapped[date] = mapped_column(Date, primary_key=True)
    metric: Mapped[str] = mapped_column(String(20), primary_key=True)
    as_of: Mapped[date] = mapped_column(Date, primary_key=True)
    mean: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(40))


class AnalystActionRow(Base):
    __tablename__ = "analyst_actions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    analyst_key: Mapped[str | None] = mapped_column(String(200), index=True)
    analyst_name: Mapped[str | None] = mapped_column(String(200))
    firm: Mapped[str] = mapped_column(String(200), index=True)
    date: Mapped[date] = mapped_column(Date)
    action: Mapped[str | None] = mapped_column(String(40))
    rating: Mapped[str | None] = mapped_column(String(60))
    rating_prior: Mapped[str | None] = mapped_column(String(60))
    rating_norm: Mapped[int | None] = mapped_column(Integer)  # +1 buy, 0 hold, -1 sell
    target: Mapped[float | None] = mapped_column(Float)
    target_prior: Mapped[float | None] = mapped_column(Float)
    price_when_posted: Mapped[float | None] = mapped_column(Float)
    url: Mapped[str | None] = mapped_column(Text)
    headline: Mapped[str | None] = mapped_column(Text)  # provider headline, shown only as a link title
    source: Mapped[str] = mapped_column(String(60))
    source_uid: Mapped[str] = mapped_column(String(80), unique=True)


class _ScoreCols:
    scope: Mapped[str] = mapped_column(String(80), primary_key=True)  # "all" | "sector:X" | "ticker:Y"
    n_calls: Mapped[int] = mapped_column(Integer)
    hit_rate: Mapped[float | None] = mapped_column(Float)
    mape: Mapped[float | None] = mapped_column(Float)
    excess_3m: Mapped[float | None] = mapped_column(Float)
    excess_6m: Mapped[float | None] = mapped_column(Float)
    excess_12m: Mapped[float | None] = mapped_column(Float)
    bullish_bias: Mapped[float | None] = mapped_column(Float)
    herding: Mapped[float | None] = mapped_column(Float)
    raw_score: Mapped[float | None] = mapped_column(Float)
    trust_score: Mapped[float | None] = mapped_column(Float)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    config_hash: Mapped[str] = mapped_column(String(16))


class AnalystScore(_ScoreCols, Base):
    __tablename__ = "analyst_scores"
    analyst_key: Mapped[str] = mapped_column(String(200), primary_key=True)


class FirmScore(_ScoreCols, Base):
    __tablename__ = "firm_scores"
    firm: Mapped[str] = mapped_column(String(200), primary_key=True)


class NewsRow(Base):
    __tablename__ = "news"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    published_at: Mapped[datetime] = mapped_column(DateTime)
    headline: Mapped[str] = mapped_column(Text)
    source_name: Mapped[str | None] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(40))
    cluster_id: Mapped[str | None] = mapped_column(String(40))
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    __table_args__ = (UniqueConstraint("ticker", "url", name="uq_news_url"),)


class NewsAnalysis(Base):
    __tablename__ = "news_analysis"
    news_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    model: Mapped[str] = mapped_column(String(80))
    summary: Mapped[str | None] = mapped_column(Text)
    sentiment: Mapped[float | None] = mapped_column(Float)
    relevance: Mapped[float | None] = mapped_column(Float)
    materiality: Mapped[str | None] = mapped_column(String(10))
    event_type: Mapped[str | None] = mapped_column(String(40))
    input_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class InsiderTx(Base):
    __tablename__ = "insider_tx"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    filer: Mapped[str] = mapped_column(String(200))
    role: Mapped[str | None] = mapped_column(String(200))
    tx_date: Mapped[date] = mapped_column(Date)
    filed_at: Mapped[date] = mapped_column(Date)
    code: Mapped[str] = mapped_column(String(4))
    open_market: Mapped[bool] = mapped_column(Boolean)
    plan_10b5_1: Mapped[bool | None] = mapped_column(Boolean)
    shares: Mapped[float] = mapped_column(Float)
    price: Mapped[float | None] = mapped_column(Float)
    value: Mapped[float | None] = mapped_column(Float)
    owned_after: Mapped[float | None] = mapped_column(Float)
    accn: Mapped[str] = mapped_column(String(30))
    url: Mapped[str | None] = mapped_column(Text)


class InstitutionalHoldingRow(Base):
    __tablename__ = "institutional_holdings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    holder: Mapped[str] = mapped_column(String(300))
    holder_cik: Mapped[str | None] = mapped_column(String(20))
    period: Mapped[date] = mapped_column(Date)
    filed_at: Mapped[date | None] = mapped_column(Date)
    shares: Mapped[float] = mapped_column(Float)
    value: Mapped[float | None] = mapped_column(Float)
    change_shares: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(40))


class ShortInterestRow(Base):
    __tablename__ = "short_interest"
    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    settlement_date: Mapped[date] = mapped_column(Date, primary_key=True)
    short_interest: Mapped[float] = mapped_column(Float)
    avg_volume: Mapped[float | None] = mapped_column(Float)
    days_to_cover: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(40))


class MacroRow(Base):
    __tablename__ = "macro"
    series_id: Mapped[str] = mapped_column(String(30), primary_key=True)
    date: Mapped[date] = mapped_column(Date, primary_key=True)
    value: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(40))


class FilingRow(Base):
    __tablename__ = "filings"
    accn: Mapped[str] = mapped_column(String(30), primary_key=True)
    cik: Mapped[int] = mapped_column(Integer, index=True)
    form: Mapped[str] = mapped_column(String(20))
    filed_at: Mapped[date] = mapped_column(Date)
    report_date: Mapped[date | None] = mapped_column(Date)
    items: Mapped[str | None] = mapped_column(String(200))
    primary_doc: Mapped[str | None] = mapped_column(String(300))
    url: Mapped[str | None] = mapped_column(Text)


class ProviderCache(Base):
    """Normalized provider payloads with TTLs. Raw HTTP is never cached here."""

    __tablename__ = "provider_cache"
    key: Mapped[str] = mapped_column(String(300), primary_key=True)
    provider: Mapped[str] = mapped_column(String(40))
    dataset: Mapped[str] = mapped_column(String(60))
    fetched_at: Mapped[datetime] = mapped_column(DateTime)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    payload_json: Mapped[dict | list] = mapped_column(JSON)
    error: Mapped[str | None] = mapped_column(Text)


class AppSnapshot(Base):
    __tablename__ = "app_snapshots"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    share_token: Mapped[str] = mapped_column(String(24), unique=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    as_of: Mapped[date] = mapped_column(Date)
    price: Mapped[float] = mapped_column(Float)
    p10: Mapped[float | None] = mapped_column(Float)
    p50: Mapped[float | None] = mapped_column(Float)
    p90: Mapped[float | None] = mapped_column(Float)
    prob_up: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[float | None] = mapped_column(Float)
    trust_rating: Mapped[float | None] = mapped_column(Float)
    sector: Mapped[str | None] = mapped_column(String(60))
    size_bucket: Mapped[str | None] = mapped_column(String(10))
    vol_bucket: Mapped[str | None] = mapped_column(String(10))
    pillars_json: Mapped[dict | None] = mapped_column(JSON)
    engine_version: Mapped[str] = mapped_column(String(20))
    config_hash: Mapped[str] = mapped_column(String(16))
    is_backtest: Mapped[bool] = mapped_column(Boolean, default=False)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    horizon_days: Mapped[int] = mapped_column(Integer, default=365)
    report_json: Mapped[dict | None] = mapped_column(JSON)
    __table_args__ = (Index("ix_snap_ticker_asof", "ticker", "as_of", "is_backtest"),)


class SnapshotOutcome(Base):
    __tablename__ = "snapshot_outcomes"
    snapshot_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    horizon_date: Mapped[date] = mapped_column(Date)
    realized_price: Mapped[float] = mapped_column(Float)
    realized_return: Mapped[float] = mapped_column(Float)
    in_band: Mapped[bool] = mapped_column(Boolean)
    abs_pct_err: Mapped[float] = mapped_column(Float)
    realized_up: Mapped[bool] = mapped_column(Boolean)
    brier: Mapped[float | None] = mapped_column(Float)
    scored_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class CalibrationChange(Base):
    """One fitted recalibration: an isotonic map for prob-up and a scale for the range width.

    Every fit is stored, applied or not, with the evidence for the decision, so the track record page can show
    each change. Live reports use the latest applied fit dated on or before their as-of date."""

    __tablename__ = "calibration_changes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fitted_on: Mapped[date] = mapped_column(Date, index=True)
    data_cutoff: Mapped[date] = mapped_column(Date)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    n: Mapped[int] = mapped_column(Integer)
    sigma_scale: Mapped[float] = mapped_column(Float, default=1.0)
    prob_map_json: Mapped[dict | None] = mapped_column(JSON)
    metrics_json: Mapped[dict] = mapped_column(JSON)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(Text)
    engine_version: Mapped[str] = mapped_column(String(20))
    config_hash: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class LlmCache(Base):
    __tablename__ = "llm_cache"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    model: Mapped[str] = mapped_column(String(80))
    purpose: Mapped[str] = mapped_column(String(40))
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    output_json: Mapped[dict | list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class LlmCostLog(Base):
    __tablename__ = "llm_cost_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    report_id: Mapped[str | None] = mapped_column(String(36))
    model: Mapped[str] = mapped_column(String(80))
    purpose: Mapped[str] = mapped_column(String(40))
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    cost_usd: Mapped[float] = mapped_column(Float)
    cached: Mapped[bool] = mapped_column(Boolean)
    validator_failures: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class WatchlistItem(Base):
    __tablename__ = "watchlist"
    ticker: Mapped[str] = mapped_column(String(16), primary_key=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticker: Mapped[str] = mapped_column(String(16), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    params_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    last_fired_at: Mapped[datetime | None] = mapped_column(DateTime)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class AlertEvent(Base):
    __tablename__ = "alert_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    alert_id: Mapped[int] = mapped_column(Integer, index=True)
    ticker: Mapped[str] = mapped_column(String(16))
    fired_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    message: Mapped[str] = mapped_column(Text)
    seen: Mapped[bool] = mapped_column(Boolean, default=False)
    kind: Mapped[str | None] = mapped_column(String(40))
    title: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    occurred_on: Mapped[date | None] = mapped_column(Date)
    key: Mapped[str | None] = mapped_column(String(200), index=True)  # dedupe: one event per underlying fact
