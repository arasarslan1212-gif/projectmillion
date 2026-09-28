"""Tiingo EOD prices. Free tier: 1,000 req/day, 500 unique symbols/month, personal use only.

GET https://api.tiingo.com/tiingo/daily/{ticker}/prices?startDate=&endDate=&token=
Rows carry raw and adjusted OHLCV plus divCash and splitFactor.
"""

from __future__ import annotations

from datetime import date, datetime

from engine.http.client import HttpClient, ProviderError, get_http
from engine.providers.models import CorporateAction, PriceBar, PriceHistory, Quote
from engine.settings import get_settings

BASE = "https://api.tiingo.com/tiingo/daily"


class Tiingo:
    name = "Tiingo"
    provider_key = "tiingo"

    def __init__(self, http: HttpClient | None = None) -> None:
        self.http = http or get_http()

    def _token(self) -> str:
        s = get_settings()
        if not s.tiingo_api_key and s.data_mode != "mock":
            raise ProviderError("tiingo", "not_configured", "TIINGO_API_KEY not set")
        return s.tiingo_api_key or ""

    def history(self, ticker: str, start: date, end: date) -> PriceHistory:
        rows = self.http.get(
            "tiingo",
            f"{BASE}/{ticker.lower()}/prices",
            params={"startDate": start.isoformat(), "endDate": end.isoformat(), "token": self._token()},
        ).body
        if not isinstance(rows, list):
            raise ProviderError("tiingo", "bad_response", str(rows)[:200])
        rows = sorted(rows, key=lambda r: str(r["date"]))
        # Normalize to the model's convention: OHLC and dividends in *current* share units
        # (split-adjusted, not dividend-adjusted); adj_close is total-return adjusted.
        # cum = product of split factors strictly after each row's date.
        cum = 1.0
        factors: list[float] = [1.0] * len(rows)
        for i in range(len(rows) - 1, -1, -1):
            factors[i] = cum
            split = float(rows[i].get("splitFactor") or 1.0)
            if split and split != 1.0:
                cum *= split
        bars, actions = [], []
        for r, f in zip(rows, factors, strict=True):
            d = date.fromisoformat(str(r["date"])[:10])
            split = float(r.get("splitFactor") or 1.0)

            # The split happens at the open of its date, so that row is already post-split.
            def adj(x, f=f):
                return float(x) / f if x is not None else None

            bars.append(
                PriceBar(
                    date=d,
                    open=adj(r.get("open")),
                    high=adj(r.get("high")),
                    low=adj(r.get("low")),
                    close=float(r["close"]) / f,
                    adj_close=float(r.get("adjClose") or r["close"]),
                    volume=float(r["volume"]) * f if r.get("volume") is not None else None,
                )
            )
            div = float(r.get("divCash") or 0)
            if div:
                actions.append(CorporateAction(date=d, kind="dividend", value=div / f))
            if split and split != 1.0:
                actions.append(CorporateAction(date=d, kind="split", value=split))
        return PriceHistory(ticker=ticker.upper(), bars=bars, actions=actions, source="Tiingo", as_of=end)

    def quote(self, ticker: str) -> Quote | None:
        # Free tier is end-of-day only; the report uses the last daily close and labels it.
        return None


def parse_ts(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
