"""Chooses concrete adapters for each data type based on DATA_TIER.

Swapping a vendor means changing this file only; analysis code sees the interfaces in base.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from engine.http.client import HttpClient, get_http
from engine.providers.finnhub import Finnhub
from engine.providers.finra import Finra
from engine.providers.fmp import Fmp
from engine.providers.fred import Fred
from engine.providers.massive import MassiveBenzinga
from engine.providers.sec_edgar import SecEdgar
from engine.providers.tiingo import Tiingo
from engine.settings import get_settings


@dataclass
class Providers:
    tier: str
    symbols: SecEdgar
    filings: SecEdgar
    fundamentals: SecEdgar
    universe: SecEdgar
    screener: Fmp | None
    prices: Tiingo | Fmp | Finnhub
    quote: Fmp | Finnhub | None
    profile: Fmp | None
    estimates: Fmp | None
    earnings: list  # ordered fallbacks
    analysts: Fmp | MassiveBenzinga | None
    analyst_grades: Fmp | None  # firm-level grades joined to per-analyst targets
    consensus: Finnhub | None
    target_consensus: Fmp | None
    news: list
    insiders: SecEdgar
    institutions: Fmp | None
    short_interest: Finra
    macro: Fred
    options: None = None
    social: None = None
    notes: dict[str, str] = field(default_factory=dict)

    @property
    def analyst_granularity(self) -> str:
        if self.analysts is not None:
            return "analyst"
        if self.consensus is not None:
            return "consensus"
        return "none"

    def describe(self) -> dict[str, str]:
        def nm(p) -> str:
            if p is None:
                return "not available on this tier"
            if isinstance(p, list):
                return ", ".join(x.name for x in p) if p else "not available on this tier"
            return p.name

        return {
            "symbols": nm(self.symbols),
            "prices": nm(self.prices),
            "quote": nm(self.quote) if self.quote else "end-of-day close (no intraday quote on this tier)",
            "fundamentals": nm(self.fundamentals),
            "filings": nm(self.filings),
            "profile": nm(self.profile),
            "estimates": nm(self.estimates),
            "earnings": nm(self.earnings),
            "analysts": nm(self.analysts) if self.analysts else f"consensus only ({nm(self.consensus)})",
            "news": nm(self.news),
            "insiders": nm(self.insiders),
            "institutional holders": nm(self.institutions),
            "short interest": nm(self.short_interest),
            "macro": nm(self.macro),
            "options": "not configured",
            "social": "not configured",
        }


def free_prices(finnhub: Finnhub, http: HttpClient) -> Tiingo | Finnhub:
    """The free tier's price source. Tiingo's free plan is personal use only, so the public site uses Finnhub."""
    s = get_settings()
    src = s.price_source.lower()
    if src == "auto":
        src = "finnhub" if s.finnhub_api_key and not s.tiingo_api_key else "tiingo"
    if src not in ("tiingo", "finnhub"):
        raise ValueError(f"PRICE_SOURCE must be tiingo, finnhub or auto, not {s.price_source!r}")
    return finnhub if src == "finnhub" else Tiingo(http)


def build_providers(tier: str | None = None, http: HttpClient | None = None) -> Providers:
    tier = tier or get_settings().data_tier
    http = http or get_http()
    sec, fred, finra = SecEdgar(http), Fred(http), Finra(http)
    finnhub = Finnhub(http)
    fmp = Fmp(http) if tier in ("starter", "pro") else None
    massive = MassiveBenzinga(http) if tier == "pro" else None
    prices = fmp or free_prices(finnhub, http)
    # Finnhub's quote is free, so it serves the latest price whenever its key is set, whatever the daily bars' source
    quote = fmp or (finnhub if prices is finnhub or get_settings().finnhub_api_key else None)
    analysts = massive or fmp
    return Providers(
        tier=tier,
        symbols=sec,
        filings=sec,
        fundamentals=sec,
        universe=sec,
        screener=fmp,
        prices=prices,
        quote=quote,
        profile=fmp,
        estimates=fmp,
        earnings=[p for p in (fmp, finnhub) if p is not None],
        analysts=analysts,
        analyst_grades=fmp,
        consensus=finnhub,
        target_consensus=fmp,
        news=[p for p in (fmp, finnhub) if p is not None],
        insiders=sec,
        institutions=fmp,
        short_interest=finra,
        macro=fred,
    )


@lru_cache(maxsize=4)
def get_providers(tier: str | None = None) -> Providers:
    return build_providers(tier)
