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
            return None
        return float(self.prices["close"].iloc[-1])

    @cached_property
    def last_price_date(self) -> date | None:
        return None if self.prices.empty else self.prices.index[-1].date()

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

    def recent(self, days: int) -> date:
        return self.as_of - timedelta(days=days)
