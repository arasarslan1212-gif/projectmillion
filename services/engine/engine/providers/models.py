"""Normalized domain models returned by provider adapters.

Adapters translate each provider's response shape into these models, so the analysis code
never depends on a specific vendor.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field


class SymbolInfo(BaseModel):
    ticker: str
    cik: int | None = None
    name: str
    exchange: str | None = None


class CompanyMeta(BaseModel):
    """From SEC submissions (plus optional profile enrichment)."""

    cik: int
    name: str
    tickers: list[str] = Field(default_factory=list)
    exchanges: list[str] = Field(default_factory=list)
    sic: int | None = None
    sic_description: str | None = None
    fiscal_year_end: str | None = None  # "MMDD"
    state_of_incorporation: str | None = None
    hq_city: str | None = None
    hq_state: str | None = None
    entity_type: str | None = None
    is_synthetic: bool = False
    source: str = "SEC EDGAR submissions"


class Filing(BaseModel):
    accession: str
    cik: int
    form: str
    filed_at: date
    report_date: date | None = None
    accepted_at: datetime | None = None
    items: list[str] = Field(default_factory=list)  # 8-K item numbers, e.g. ["2.02", "9.01"]
    primary_doc: str | None = None
    description: str | None = None
    url: str | None = None


class Fact(BaseModel):
    """One XBRL fact as reported in one filing. Point-in-time via `filed`."""

    taxonomy: str
    concept: str
    unit: str
    start: date | None = None
    end: date
    value: float
    fy: int | None = None
    fp: str | None = None
    form: str | None = None
    accn: str | None = None
    filed: date
    frame: str | None = None


class FramePoint(BaseModel):
    cik: int
    entity_name: str
    value: float
    start: date | None = None
    end: date
    accn: str | None = None


class PriceBar(BaseModel):
    date: date
    open: float | None
    high: float | None
    low: float | None
    close: float
    adj_close: float
    volume: float | None = None


class CorporateAction(BaseModel):
    date: date
    kind: str  # "split" | "dividend"
    value: float  # split ratio (e.g. 4.0) or cash dividend per share
    pay_date: date | None = None
    record_date: date | None = None
    declared_date: date | None = None


class PriceHistory(BaseModel):
    ticker: str
    bars: list[PriceBar]
    actions: list[CorporateAction] = Field(default_factory=list)
    source: str
    as_of: date | None = None


class Quote(BaseModel):
    ticker: str
    price: float
    change: float | None = None
    change_pct: float | None = None
    volume: float | None = None
    prev_close: float | None = None
    after_hours_price: float | None = None
    timestamp: datetime | None = None
    source: str
    delayed_note: str | None = None


class CompanyProfile(BaseModel):
    ticker: str
    description: str | None = None
    ceo: str | None = None
    employees: int | None = None
    ipo_date: date | None = None
    website: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    sector: str | None = None
    industry: str | None = None
    beta: float | None = None
    source: str


class Executive(BaseModel):
    name: str
    title: str
    since: int | None = None  # year, when the provider exposes it


class EmployeeCount(BaseModel):
    period: date
    count: int
    filed: date | None = None
    source: str


class Segment(BaseModel):
    fiscal_year: int
    period_end: date | None = None
    kind: str  # "product" | "geography"
    values: dict[str, float]
    source: str


class Estimate(BaseModel):
    period_end: date
    period_type: str  # "annual" | "quarter"
    metric: str  # "eps" | "revenue" | "ebitda" | "net_income"
    mean: float | None
    low: float | None = None
    high: float | None = None
    n_analysts: int | None = None
    source: str


class EarningsEvent(BaseModel):
    date: date
    period_end: date | None = None
    eps_actual: float | None = None
    eps_estimate: float | None = None
    revenue_actual: float | None = None
    revenue_estimate: float | None = None
    time_of_day: str | None = None  # "bmo" | "amc" | None
    source: str


class AnalystAction(BaseModel):
    ticker: str
    date: date
    analyst_name: str | None  # None when the provider is firm-level only
    analyst_id: str | None = None
    firm: str
    action: str | None = None  # upgrade | downgrade | initiate | reiterate | target_raise | target_cut | ...
    rating: str | None = None
    rating_prior: str | None = None
    target: float | None = None
    target_prior: float | None = None
    price_when_posted: float | None = None
    url: str | None = None
    headline: str | None = None
    source: str
    source_uid: str


class RecommendationTrend(BaseModel):
    period: date
    strong_buy: int
    buy: int
    hold: int
    sell: int
    strong_sell: int
    source: str


class TargetConsensus(BaseModel):
    high: float | None
    low: float | None
    mean: float | None
    median: float | None
    source: str


class NewsItem(BaseModel):
    ticker: str
    published_at: datetime
    headline: str
    source_name: str | None = None
    url: str
    provider: str
    provider_summary: str | None = None  # short provider-supplied teaser; never full article text


class InsiderTransaction(BaseModel):
    ticker: str
    filer_name: str
    filer_cik: str | None = None
    role: str | None = None
    is_director: bool = False
    is_officer: bool = False
    is_ten_pct_owner: bool = False
    tx_date: date
    filed_at: date
    code: str  # SEC transaction code: P, S, M, A, F, G, ...
    acquired: bool
    shares: float
    price: float | None
    owned_after: float | None = None
    plan_10b5_1: bool | None = None  # None = not disclosed (filings before April 2023)
    accession: str
    url: str | None = None
    derivative: bool = False


class InstitutionalHolding(BaseModel):
    holder: str
    holder_cik: str | None = None
    period: date
    shares: float
    value: float | None = None
    change_shares: float | None = None
    pct_of_shares: float | None = None
    source: str


class ShortInterestPoint(BaseModel):
    settlement_date: date
    short_interest: float
    avg_daily_volume: float | None = None
    days_to_cover: float | None = None
    source: str


class MacroPoint(BaseModel):
    date: date
    value: float


class MacroSeries(BaseModel):
    series_id: str
    title: str
    units: str
    points: list[MacroPoint]
    source: str
