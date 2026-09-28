"""Provider interfaces. The analysis code depends only on these, never on a concrete vendor."""

from __future__ import annotations

from datetime import date
from typing import Protocol, runtime_checkable

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
    FramePoint,
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


@runtime_checkable
class SymbolProvider(Protocol):
    name: str

    def all_symbols(self) -> list[SymbolInfo]: ...


@runtime_checkable
class PriceProvider(Protocol):
    name: str

    def history(self, ticker: str, start: date, end: date) -> PriceHistory: ...

    def quote(self, ticker: str) -> Quote | None: ...


@runtime_checkable
class FundamentalsProvider(Protocol):
    name: str

    def company_facts(self, cik: int) -> list[Fact]: ...


@runtime_checkable
class UniverseProvider(Protocol):
    """Cross-sectional data used for sector percentiles."""

    name: str

    def ciks_for_sic(self, sic: int) -> list[int]: ...

    def frame(self, concept: str, unit: str, period: str, taxonomy: str = "us-gaap") -> list[FramePoint]: ...


@runtime_checkable
class FilingsProvider(Protocol):
    name: str

    def company_meta(self, cik: int) -> CompanyMeta: ...

    def filings(self, cik: int) -> list[Filing]: ...

    def document_text(self, filing: Filing) -> str: ...


@runtime_checkable
class ProfileProvider(Protocol):
    name: str

    def profile(self, ticker: str) -> CompanyProfile | None: ...

    def executives(self, ticker: str) -> list[Executive]: ...

    def employee_history(self, ticker: str) -> list[EmployeeCount]: ...

    def segments(self, ticker: str) -> list[Segment]: ...

    def peers(self, ticker: str) -> list[str]: ...


@runtime_checkable
class EstimatesProvider(Protocol):
    name: str

    def estimates(self, ticker: str) -> list[Estimate]: ...

    def earnings(self, ticker: str) -> list[EarningsEvent]: ...


@runtime_checkable
class AnalystProvider(Protocol):
    name: str
    granularity: str  # "analyst" | "firm" | "consensus"

    def actions(self, ticker: str) -> list[AnalystAction]: ...

    def recommendation_trends(self, ticker: str) -> list[RecommendationTrend]: ...

    def target_consensus(self, ticker: str) -> TargetConsensus | None: ...


@runtime_checkable
class NewsProvider(Protocol):
    name: str

    def news(self, ticker: str, start: date, end: date) -> list[NewsItem]: ...


@runtime_checkable
class OwnershipProvider(Protocol):
    name: str

    def insider_transactions(self, ticker: str, cik: int, since: date) -> list[InsiderTransaction]: ...

    def institutional_holders(self, ticker: str) -> list[InstitutionalHolding]: ...


@runtime_checkable
class ShortInterestProvider(Protocol):
    name: str

    def short_interest(self, ticker: str) -> list[ShortInterestPoint]: ...


@runtime_checkable
class MacroProvider(Protocol):
    name: str

    def series(self, series_id: str, start: date) -> MacroSeries: ...


@runtime_checkable
class OptionsProvider(Protocol):
    """Optional. No adapter is configured by default (see PLAN.md §7)."""

    name: str

    def implied_vol(self, ticker: str) -> float | None: ...

    def implied_earnings_move(self, ticker: str) -> float | None: ...


@runtime_checkable
class SocialProvider(Protocol):
    """Optional; only official APIs within their terms. Not configured by default."""

    name: str

    def mentions(self, ticker: str, start: date, end: date) -> list[NewsItem]: ...
