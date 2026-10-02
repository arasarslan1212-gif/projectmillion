"""ReportContext: everything the report sections need for one ticker at one as-of date.

All data access is lazy and memoized. In point-in-time mode (backtests), only information that was
public at `as_of` is visible: facts and filings by filing date, prices by date, analyst actions and
news by publication date. Sources with no history (current estimates, profiles) are excluded.
"""

from __future__ import annotations

import threading
from datetime import date, timedelta
from functools import cached_property
from typing import Any

import pandas as pd

from engine import clock
from engine.config import get_config
from engine.data.prices import dividends_of, splits_of, to_frame
from engine.data.service import DataService, Fetched, get_data
from engine.fundamentals.sector import SectorInfo, detect
from engine.fundamentals.statements import Financials, build_financials
from engine.providers.models import CompanyMeta, Filing, SymbolInfo


class TickerNotFound(Exception):
    pass


class ReportContext:
    def __init__(
        self, ticker: str, as_of: date | None = None, data: DataService | None = None, pit: bool = False
    ) -> None:
        self.data = data or get_data()
        self.cfg = get_config()
        self.as_of = as_of or clock.today()
        self.pit = pit
        self.ticker = ticker.upper().strip()
        self.sources: dict[str, dict] = {}
        self.missing: dict[str, str] = {}
        self._sections: dict[str, Any] = {}
        self._lock = threading.RLock()
        self.synthetic = clock.is_synthetic()

    # ---- bookkeeping -----------------------------------------------------------------
    def _note(self, name: str, fx: Fetched) -> Any:
        self.sources[name] = fx.meta()
        if fx.value is None and fx.reason:
            self.missing[name] = fx.reason
        return fx.value

    def section(self, name: str, fn) -> Any:
        with self._lock:
            if name not in self._sections:
                self._sections[name] = fn(self)
            return self._sections[name]

    # ---- identity ----------------------------------------------------------------------
    @cached_property
    def symbol(self) -> SymbolInfo:
        s = self.data.resolve(self.ticker)
        if s is None:
            raise TickerNotFound(self.ticker)
        return s

    @cached_property
    def cik(self) -> int | None:
        return self.symbol.cik

    @cached_property
    def _submissions(self) -> dict | None:
        if self.cik is None:
            return None
        return self._note("filings", self.data.submissions(self.cik))

    @cached_property
    def meta(self) -> CompanyMeta | None:
        return self._submissions["meta"] if self._submissions else None

    @cached_property
    def all_filings(self) -> list[Filing]:
        return self._submissions["filings"] if self._submissions else []

    @cached_property
    def filings(self) -> list[Filing]:
        return sorted((f for f in self.all_filings if f.filed_at <= self.as_of), key=lambda f: f.filed_at)

    @cached_property
    def facts(self):
        if self.cik is None:
            return []
        return self._note("fundamentals", self.data.facts(self.cik, self.all_filings)) or []

    # ---- prices ------------------------------------------------------------------------
    @cached_property
    def price_history(self):
        return self._note("prices", self.data.prices(self.ticker))

    @cached_property
    def prices(self) -> pd.DataFrame:
        return to_frame(self.price_history, self.as_of)

    @cached_property
    def splits(self) -> list[tuple[date, float]]:
        return splits_of(self.price_history)

    @cached_property
    def dividends(self) -> list[tuple[date, float]]:
        return dividends_of(self.price_history, self.as_of)

    @cached_property
    def last_price(self) -> float | None:
        if self.prices.empty:
            # no daily history (e.g. Finnhub's free plan): today's report can still price off the live quote
            q = self._live_quote
            return float(q.price) if q is not None else None
        return float(self.prices["close"].iloc[-1])

    @cached_property
    def last_price_date(self) -> date | None:
        if self.prices.empty:
            q = self._live_quote
            return (q.timestamp.date() if q.timestamp else self.as_of) if q is not None else None
        return self.prices.index[-1].date()

    @property
    def _live_quote(self):
        return self.quote if self.as_of >= clock.today() else None

    def peer_price(self, ticker: str, days: int) -> tuple[float | None, pd.DataFrame]:
        """A peer's latest price and its daily history, for multiples and the 1-year return. On the free tier, with a
        quote source, the quote alone: history for every peer would spend a rate-limited plan (Tiingo's free
        plan allows 50 requests an hour) on a column the comparison can do without."""
        if self.data.p.tier == "free" and self.data.p.quote is not None and self.as_of >= clock.today():
            q = self.data.quote(ticker).value
            return (float(q.price) if q is not None else None), pd.DataFrame()
        px = self.other_prices(ticker, days)
        return (float(px["close"].iloc[-1]) if not px.empty else None), px

    @cached_property
    def quote(self):
        if self.pit:
            return None
        return self._note("quote", self.data.quote(self.ticker))

    def benchmark_tickers(self) -> tuple[str, str | None, str]:
        b = self.cfg["benchmarks"]
        if self.synthetic:
            b = b["synthetic"]
        return b["market"], b["sector_etfs"].get(self.sector.sector), b["market_label"]

    def other_prices(self, ticker: str, days: int | None = None) -> pd.DataFrame:
        if self.as_of < clock.today():
            # a past report needs prices up to its own date: use the full (shared, cached) history
            days = None
        fx = self.data.prices(ticker, days)
        if fx.value is None:
            self.missing[f"prices:{ticker}"] = fx.reason or "unavailable"
        return to_frame(fx.value, self.as_of)

    @cached_property
    def market_prices(self) -> pd.DataFrame:
        return self.other_prices(self.benchmark_tickers()[0])

    @cached_property
    def sector_prices(self) -> pd.DataFrame:
        etf = self.benchmark_tickers()[1]
        return self.other_prices(etf) if etf else pd.DataFrame()

    # ---- fundamentals --------------------------------------------------------------------
    @cached_property
    def fin(self) -> Financials:
        return build_financials(self.facts, self.as_of, self.splits)

    @cached_property
    def sector(self) -> SectorInfo:
        f = self.fin
        rev = f.ttm.get("revenue")
        oi = f.ttm.get("operating_income")
        margin = (oi / rev) if (rev and oi is not None and rev > 0) else None
        growth = None
        a = f.annual
        if len(a) >= 2 and a[-1].get("revenue") and a[-2].get("revenue") and a[-2].get("revenue") > 0:
            growth = a[-1].get("revenue") / a[-2].get("revenue") - 1
        rnd = f.ttm.get("rnd")
        rnd_ratio = (rnd / rev) if (rnd and rev) else None
        m = self.meta
        return detect(
            m.sic if m else None, m.sic_description if m else None, rev, margin, growth, rnd_ratio, self.cfg
        )

    @cached_property
    def shares_outstanding(self) -> tuple[float | None, str]:
        """Best current share count, in current share units."""
        cov = self.fin.cover.get("shares_outstanding_cover")
        if cov:
            val, d = cov
            f = 1.0
            for sd, ratio in self.splits:
                if d < sd <= self.as_of:
                    f *= ratio
            return val * f, f"cover page of the latest filing (as of {d.isoformat()})"
        so = self.fin.latest("shares_outstanding")
        if so:
            return so, "balance sheet"
        sd_ = self.fin.ttm.get("shares_diluted")
        if sd_:
            return sd_, "weighted-average diluted shares (latest quarter)"
        return None, "unavailable"

    @cached_property
    def market_cap(self) -> float | None:
        sh, _ = self.shares_outstanding
        if sh is None or self.last_price is None:
            return None
        return sh * self.last_price

    # ---- optional enrichments (not point-in-time) -----------------------------------------
    def optional(self, name: str, fx_fn) -> Any:
        if self.pit:
            self.missing[name] = "excluded in point-in-time mode (no history available)"
            return None
        return self._note(name, fx_fn())

    @cached_property
    def profile(self):
        return self.optional("profile", lambda: self.data.profile(self.ticker))

    # ---- cross-sectional ---------------------------------------------------------------
    peer_override: list[str] | None = None

    @cached_property
    def universe(self):
        from engine.fundamentals.universe import build_universe

        u = build_universe(self, int(self.cfg.get("peers.min_peers_for_percentiles", 8)))
        if u is not None:
            self.sources["universe"] = {
                "source": self._label_src("SEC EDGAR frames"),
                "fetched_at": None,
                "status": "ok",
                "reason": None,
            }
        return u

    def _label_src(self, s: str) -> str:
        return f"{s} (SYNTHETIC)" if self.synthetic else s

    # ---- ownership ---------------------------------------------------------------------
    @cached_property
    def insiders(self):
        if self.cik is None:
            return None
        txs = self._note("insiders", self.data.insiders(self.ticker, self.cik))
        if txs is None:
            return None
        return [t for t in txs if t.filed_at <= self.as_of]

    @cached_property
    def institutions(self):
        return self.optional("institutions", lambda: self.data.institutions(self.ticker))

    def recent(self, days: int) -> date:
        return self.as_of - timedelta(days=days)
