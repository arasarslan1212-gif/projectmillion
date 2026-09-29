"""Finnhub adapter (https://finnhub.io/api/v1). Free tier: 60 calls/min.

Used for: company news (free), recommendation trends (free, consensus distribution only),
earnings surprises (free: recent quarters) and the earnings calendar; with PRICE_SOURCE=finnhub, also daily
candles and the latest quote (the public site's price source; see DECISIONS D-064).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from engine.http.client import HttpClient, ProviderError, get_http
from engine.providers.models import (
    AnalystAction,
    EarningsEvent,
    Estimate,
    NewsItem,
    PriceBar,
    PriceHistory,
    Quote,
    RecommendationTrend,
    TargetConsensus,
)
from engine.settings import get_settings

BASE = "https://finnhub.io/api/v1"


class Finnhub:
    name = "Finnhub"
    provider_key = "finnhub"
    granularity = "consensus"

    def __init__(self, http: HttpClient | None = None) -> None:
        self.http = http or get_http()

    def _get(self, path: str, **params):
        s = get_settings()
        if not s.finnhub_api_key and s.data_mode != "mock":
            raise ProviderError("finnhub", "not_configured", "FINNHUB_API_KEY not set")
        params["token"] = s.finnhub_api_key or ""
        body = self.http.get("finnhub", f"{BASE}/{path}", params=params).body
        if isinstance(body, dict) and body.get("error"):
            msg = str(body["error"])
            kind = (
                "plan_restricted" if "access" in msg.lower() or "premium" in msg.lower() else "bad_response"
            )
            raise ProviderError("finnhub", kind, msg[:200])
        return body

    def news(self, ticker: str, start: date, end: date) -> list[NewsItem]:
        rows = (
            self._get(
                "company-news", symbol=ticker.upper(), **{"from": start.isoformat(), "to": end.isoformat()}
            )
            or []
        )
        out = []
        for r in rows:
            ts, url, head = r.get("datetime"), r.get("url"), r.get("headline")
            if not ts or not url or not head:
                continue
            out.append(
                NewsItem(
                    ticker=ticker.upper(),
                    published_at=datetime.fromtimestamp(int(ts), tz=UTC),
                    headline=head,
                    source_name=r.get("source"),
                    url=url,
                    provider="Finnhub",
                    provider_summary=(r.get("summary") or "")[:400] or None,
                )
            )
        return out

    def recommendation_trends(self, ticker: str) -> list[RecommendationTrend]:
        out = []
        for r in self._get("stock/recommendation", symbol=ticker.upper()) or []:
            try:
                out.append(
                    RecommendationTrend(
                        period=date.fromisoformat(r["period"][:10]),
                        strong_buy=int(r.get("strongBuy", 0)),
                        buy=int(r.get("buy", 0)),
                        hold=int(r.get("hold", 0)),
                        sell=int(r.get("sell", 0)),
                        strong_sell=int(r.get("strongSell", 0)),
                        source="Finnhub",
                    )
                )
            except (KeyError, ValueError):
                continue
        return sorted(out, key=lambda t: t.period)

    def actions(self, ticker: str) -> list[AnalystAction]:
        return []  # per-analyst and firm actions are premium on Finnhub; not used

    def target_consensus(self, ticker: str) -> TargetConsensus | None:
        return None

    def earnings(self, ticker: str) -> list[EarningsEvent]:
        out = []
        for r in self._get("stock/earnings", symbol=ticker.upper()) or []:
            try:
                pe = date.fromisoformat(r["period"][:10])
            except (KeyError, ValueError):
                continue
            out.append(
                EarningsEvent(
                    date=pe,  # Finnhub reports the fiscal period; the release date comes from the calendar
                    period_end=pe,
                    eps_actual=r.get("actual"),
                    eps_estimate=r.get("estimate"),
                    source="Finnhub",
                )
            )
        return out

    def earnings_calendar(self, ticker: str, start: date, end: date) -> list[EarningsEvent]:
        body = self._get(
            "calendar/earnings", symbol=ticker.upper(), **{"from": start.isoformat(), "to": end.isoformat()}
        )
        out = []
        for r in (body or {}).get("earningsCalendar", []) or []:
            try:
                d = date.fromisoformat(r["date"][:10])
            except (KeyError, ValueError):
                continue
            out.append(
                EarningsEvent(
                    date=d,
                    eps_actual=r.get("epsActual"),
                    eps_estimate=r.get("epsEstimate"),
                    revenue_actual=r.get("revenueActual"),
                    revenue_estimate=r.get("revenueEstimate"),
                    time_of_day=r.get("hour") or None,
                    source="Finnhub",
                )
            )
        return out

    def estimates(self, ticker: str) -> list[Estimate]:
        return []  # premium on Finnhub

    # ---- prices (PRICE_SOURCE=finnhub) ------------------------------------------------
    def history(self, ticker: str, start: date, end: date) -> PriceHistory:
        """Daily candles. Finnhub adjusts them for splits; dividends aren't part of the free data, so adj_close is
        the split-adjusted close (price return, not total return)."""
        t0 = int(datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp())
        t1 = int(datetime(end.year, end.month, end.day, 23, 59, tzinfo=UTC).timestamp())
        b = self._get("stock/candle", symbol=ticker.upper(), resolution="D", **{"from": t0, "to": t1})
        if not isinstance(b, dict) or b.get("s") not in ("ok", "no_data"):
            raise ProviderError("finnhub", "bad_response", str(b)[:200])
        bars = []
        if b.get("s") == "ok":
            for t, o, h, lo, c, v in zip(b["t"], b["o"], b["h"], b["l"], b["c"], b["v"], strict=False):
                bars.append(
                    PriceBar(
                        date=datetime.fromtimestamp(int(t), tz=UTC).date(),
                        open=o,
                        high=h,
                        low=lo,
                        close=float(c),
                        adj_close=float(c),
                        volume=v,
                    )
                )
        return PriceHistory(ticker=ticker.upper(), bars=bars, source="Finnhub", as_of=end)

    def quote(self, ticker: str) -> Quote | None:
        r = self._get("quote", symbol=ticker.upper())
        if not isinstance(r, dict) or not r.get("c"):  # unknown symbols come back as zeros
            return None
        ts = r.get("t")
        return Quote(
            ticker=ticker.upper(),
            price=float(r["c"]),
            change=r.get("d"),
            change_pct=r["dp"] / 100 if r.get("dp") is not None else None,
            prev_close=r.get("pc"),
            timestamp=datetime.fromtimestamp(int(ts), tz=UTC) if ts else None,
            source="Finnhub",
        )
