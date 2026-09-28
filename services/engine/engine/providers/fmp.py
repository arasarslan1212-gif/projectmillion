"""Financial Modeling Prep adapter ("stable" API, https://financialmodelingprep.com/stable/).

Used on the starter/pro tiers for: prices, quote, profile, executives, employee counts, segments,
peers, estimates, earnings, per-analyst price targets (`price-target-news`), firm grades,
target consensus, news and institutional holders.

Standard FMP plans are licensed for personal use; public display needs FMP's data display
license (see DATA_SOURCES.md). Parsing is defensive: fields are read with fallbacks because
the adapter could not be exercised against the live API from the build environment.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime

from engine.http.client import HttpClient, ProviderError, get_http
from engine.providers.models import (
    AnalystAction,
    CompanyProfile,
    CorporateAction,
    EarningsEvent,
    EmployeeCount,
    Estimate,
    Executive,
    InstitutionalHolding,
    NewsItem,
    PriceBar,
    PriceHistory,
    Quote,
    RecommendationTrend,
    Segment,
    TargetConsensus,
)
from engine.settings import get_settings

BASE = "https://financialmodelingprep.com/stable"


def _d(s) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(str(s)[:10])
    except ValueError:
        return None


def _dt(s) -> datetime | None:
    if not s:
        return None
    s = str(s).replace("Z", "+00:00")
    for fmt in (None, "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.fromisoformat(s) if fmt is None else datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _f(x) -> float | None:
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _uid(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:20]


class Fmp:
    name = "Financial Modeling Prep"
    provider_key = "fmp"
    granularity = "analyst"

    def __init__(self, http: HttpClient | None = None) -> None:
        self.http = http or get_http()

    def _get(self, path: str, **params):
        s = get_settings()
        if not s.fmp_api_key and s.data_mode != "mock":
            raise ProviderError("fmp", "not_configured", "FMP_API_KEY not set")
        params["apikey"] = s.fmp_api_key or ""
        body = self.http.get("fmp", f"{BASE}/{path}", params=params).body
        if isinstance(body, dict) and ("Error Message" in body or "error" in body):
            msg = str(body.get("Error Message") or body.get("error"))
            kind = (
                "plan_restricted"
                if "plan" in msg.lower() or "subscription" in msg.lower()
                else "bad_response"
            )
            raise ProviderError("fmp", kind, msg[:200])
        return body

    # -- prices ----------------------------------------------------------------------
    def history(self, ticker: str, start: date, end: date) -> PriceHistory:
        rows = self._get(
            "historical-price-eod/full",
            symbol=ticker.upper(),
            **{"from": start.isoformat(), "to": end.isoformat()},
        )
        adj_rows = self._get(
            "historical-price-eod/dividend-adjusted",
            symbol=ticker.upper(),
            **{"from": start.isoformat(), "to": end.isoformat()},
        )
        rows = rows.get("historical", rows) if isinstance(rows, dict) else rows
        adj_rows = adj_rows.get("historical", adj_rows) if isinstance(adj_rows, dict) else adj_rows
        adj_by_date = {str(r.get("date"))[:10]: _f(r.get("adjClose")) for r in adj_rows or []}
        bars = []
        for r in sorted(rows or [], key=lambda r: str(r.get("date"))):
            ds = str(r.get("date"))[:10]
            close = _f(r.get("close"))
            if close is None:
                continue
            bars.append(
                PriceBar(
                    date=date.fromisoformat(ds),
                    open=_f(r.get("open")),
                    high=_f(r.get("high")),
                    low=_f(r.get("low")),
                    close=close,  # FMP EOD "full" is split-adjusted, not dividend-adjusted
                    adj_close=adj_by_date.get(ds) or close,
                    volume=_f(r.get("volume")),
                )
            )
        actions: list[CorporateAction] = []
        try:
            for r in self._get("dividends", symbol=ticker.upper()) or []:
                d = _d(r.get("date"))
                v = _f(r.get("adjDividend")) or _f(r.get("dividend"))
                if d and v:
                    actions.append(
                        CorporateAction(
                            date=d,
                            kind="dividend",
                            value=v,
                            pay_date=_d(r.get("paymentDate")),
                            record_date=_d(r.get("recordDate")),
                            declared_date=_d(r.get("declarationDate")),
                        )
                    )
            for r in self._get("splits", symbol=ticker.upper()) or []:
                d = _d(r.get("date"))
                num, den = _f(r.get("numerator")), _f(r.get("denominator"))
                if d and num and den:
                    actions.append(CorporateAction(date=d, kind="split", value=num / den))
        except ProviderError:
            pass
        return PriceHistory(ticker=ticker.upper(), bars=bars, actions=actions, source="FMP", as_of=end)

    def quote(self, ticker: str) -> Quote | None:
        rows = self._get("quote", symbol=ticker.upper())
        if not rows:
            return None
        r = rows[0]
        ts = r.get("timestamp")
        return Quote(
            ticker=ticker.upper(),
            price=float(r["price"]),
            change=_f(r.get("change")),
            change_pct=(_f(r.get("changePercentage")) or 0) / 100
            if r.get("changePercentage") is not None
            else None,
            volume=_f(r.get("volume")),
            prev_close=_f(r.get("previousClose")),
            timestamp=datetime.fromtimestamp(ts) if isinstance(ts, (int, float)) else None,
            source="FMP",
        )

    # -- profile ---------------------------------------------------------------------
    def profile(self, ticker: str) -> CompanyProfile | None:
        rows = self._get("profile", symbol=ticker.upper())
        if not rows:
            return None
        r = rows[0]
        emp = r.get("fullTimeEmployees")
        try:
            emp_i = int(str(emp).replace(",", "")) if emp not in (None, "") else None
        except ValueError:
            emp_i = None
        return CompanyProfile(
            ticker=ticker.upper(),
            description=r.get("description"),
            ceo=r.get("ceo"),
            employees=emp_i,
            ipo_date=_d(r.get("ipoDate")),
            website=r.get("website"),
            city=r.get("city"),
            state=r.get("state"),
            country=r.get("country"),
            sector=r.get("sector"),
            industry=r.get("industry"),
            beta=_f(r.get("beta")),
            source="FMP",
        )

    def executives(self, ticker: str) -> list[Executive]:
        out = []
        for r in self._get("key-executives", symbol=ticker.upper()) or []:
            if r.get("active") is False:
                continue
            out.append(
                Executive(name=r.get("name") or "", title=r.get("title") or "", since=r.get("titleSince"))
            )
        return out

    def employee_history(self, ticker: str) -> list[EmployeeCount]:
        out = []
        for r in self._get("employee-count", symbol=ticker.upper()) or []:
            p = _d(r.get("periodOfReport"))
            c = r.get("employeeCount")
            if p and c is not None:
                out.append(EmployeeCount(period=p, count=int(c), filed=_d(r.get("filingDate")), source="FMP"))
        return sorted(out, key=lambda e: e.period)

    def segments(self, ticker: str) -> list[Segment]:
        out = []
        for kind, path in (
            ("product", "revenue-product-segmentation"),
            ("geography", "revenue-geographic-segmentation"),
        ):
            try:
                rows = self._get(path, symbol=ticker.upper(), period="annual")
            except ProviderError:
                continue
            for r in rows or []:
                data = r.get("data") or {}
                vals = {k: float(v) for k, v in data.items() if _f(v) is not None}
                if vals:
                    out.append(
                        Segment(
                            fiscal_year=int(r.get("fiscalYear") or (_d(r.get("date")) or date.today()).year),
                            period_end=_d(r.get("date")),
                            kind=kind,
                            values=vals,
                            source="FMP",
                        )
                    )
        return out

    def peers(self, ticker: str) -> list[str]:
        rows = self._get("stock-peers", symbol=ticker.upper()) or []
        return [r["symbol"] for r in rows if r.get("symbol")]

    def screener(
        self, sector: str | None = None, industry: str | None = None, limit: int = 300
    ) -> list[dict]:
        params = {"isActivelyTrading": "true", "limit": str(limit), "isEtf": "false", "isFund": "false"}
        if sector:
            params["sector"] = sector
        if industry:
            params["industry"] = industry
        return self._get("company-screener", **params) or []

    def shares_float(self, ticker: str) -> dict | None:
        rows = self._get("shares-float", symbol=ticker.upper())
        return rows[0] if rows else None

    def index_membership(self) -> set[str]:
        rows = self._get("sp500-constituent") or []
        return {r["symbol"] for r in rows if r.get("symbol")}

    # -- estimates & earnings ----------------------------------------------------------
    def estimates(self, ticker: str) -> list[Estimate]:
        out = []
        for period in ("annual", "quarter"):
            try:
                rows = self._get(
                    "analyst-estimates", symbol=ticker.upper(), period=period, page="0", limit="20"
                )
            except ProviderError:
                continue
            for r in rows or []:
                pe = _d(r.get("date"))
                if not pe:
                    continue
                for metric, prefix, n_key in (
                    ("eps", "eps", "numAnalystsEps"),
                    ("revenue", "revenue", "numAnalystsRevenue"),
                    ("ebitda", "ebitda", "numAnalystsRevenue"),
                ):
                    mean = _f(r.get(f"{prefix}Avg"))
                    if mean is None:
                        continue
                    out.append(
                        Estimate(
                            period_end=pe,
                            period_type=period,
                            metric=metric,
                            mean=mean,
                            low=_f(r.get(f"{prefix}Low")),
                            high=_f(r.get(f"{prefix}High")),
                            n_analysts=r.get(n_key),
                            source="FMP",
                        )
                    )
        return out

    def earnings(self, ticker: str) -> list[EarningsEvent]:
        out = []
        for r in self._get("earnings", symbol=ticker.upper(), limit="40") or []:
            d = _d(r.get("date"))
            if not d:
                continue
            out.append(
                EarningsEvent(
                    date=d,
                    eps_actual=_f(r.get("epsActual")),
                    eps_estimate=_f(r.get("epsEstimated")),
                    revenue_actual=_f(r.get("revenueActual")),
                    revenue_estimate=_f(r.get("revenueEstimated")),
                    source="FMP",
                )
            )
        return sorted(out, key=lambda e: e.date)

    # -- analysts ----------------------------------------------------------------------
    def actions(self, ticker: str) -> list[AnalystAction]:
        out: list[AnalystAction] = []
        rows = self._get("price-target-news", symbol=ticker.upper(), page="0", limit="1000") or []
        for r in rows:
            d = _d(r.get("publishedDate"))
            firm = (r.get("analystCompany") or "").strip()
            target = _f(r.get("priceTarget"))
            if not d or not firm or target is None:
                continue
            name = (r.get("analystName") or "").strip() or None
            out.append(
                AnalystAction(
                    ticker=ticker.upper(),
                    date=d,
                    analyst_name=name,
                    firm=firm,
                    action="target",
                    target=target,
                    price_when_posted=_f(r.get("priceWhenPosted")),
                    url=r.get("newsURL"),
                    headline=r.get("newsTitle"),
                    source="FMP price-target-news",
                    source_uid=_uid("fmp-pt", ticker, d, firm, name, target),
                )
            )
        try:
            grades = self._get("grades", symbol=ticker.upper(), limit="1000") or []
        except ProviderError:
            grades = []
        for r in grades:
            d = _d(r.get("date"))
            firm = (r.get("gradingCompany") or "").strip()
            if not d or not firm:
                continue
            out.append(
                AnalystAction(
                    ticker=ticker.upper(),
                    date=d,
                    analyst_name=None,
                    firm=firm,
                    action=(r.get("action") or "").lower() or None,
                    rating=r.get("newGrade"),
                    rating_prior=r.get("previousGrade"),
                    source="FMP grades",
                    source_uid=_uid("fmp-grade", ticker, d, firm, r.get("newGrade")),
                )
            )
        return out

    def recommendation_trends(self, ticker: str) -> list[RecommendationTrend]:
        return []

    def target_consensus(self, ticker: str) -> TargetConsensus | None:
        rows = self._get("price-target-consensus", symbol=ticker.upper())
        if not rows:
            return None
        r = rows[0]
        return TargetConsensus(
            high=_f(r.get("targetHigh")),
            low=_f(r.get("targetLow")),
            mean=_f(r.get("targetConsensus")),
            median=_f(r.get("targetMedian")),
            source="FMP",
        )

    # -- news & ownership --------------------------------------------------------------
    def news(self, ticker: str, start: date, end: date) -> list[NewsItem]:
        rows = (
            self._get(
                "news/stock",
                symbols=ticker.upper(),
                page="0",
                limit="100",
                **{"from": start.isoformat(), "to": end.isoformat()},
            )
            or []
        )
        out = []
        for r in rows:
            ts = _dt(r.get("publishedDate"))
            url = r.get("url")
            if not ts or not url or not r.get("title"):
                continue
            teaser = (r.get("text") or "")[:400] or None
            out.append(
                NewsItem(
                    ticker=ticker.upper(),
                    published_at=ts,
                    headline=r["title"],
                    source_name=r.get("publisher") or r.get("site"),
                    url=url,
                    provider="FMP",
                    provider_summary=teaser,
                )
            )
        return out

    def institutional_holders(self, ticker: str) -> list[InstitutionalHolding]:
        today = date.today()
        # 13F filings arrive ~45 days after quarter end; ask for the latest quarter likely complete.
        q_end_month = ((today.month - 1) // 3) * 3
        year, quarter = (today.year, q_end_month // 3) if q_end_month else (today.year - 1, 4)
        if quarter >= 1 and (today - date(year, quarter * 3, 28)).days < 50:
            quarter -= 1
            if quarter == 0:
                year, quarter = year - 1, 4
        rows = (
            self._get(
                "institutional-ownership/extract-analytics/holder",
                symbol=ticker.upper(),
                year=str(year),
                quarter=str(quarter),
                page="0",
                limit="25",
            )
            or []
        )
        out = []
        for r in rows:
            shares = _f(r.get("sharesNumber"))
            if shares is None:
                continue
            out.append(
                InstitutionalHolding(
                    holder=r.get("investorName") or "Unknown",
                    holder_cik=r.get("cik"),
                    period=_d(r.get("date")) or date(year, quarter * 3, 28),
                    shares=shares,
                    value=_f(r.get("marketValue")),
                    change_shares=_f(r.get("changeInSharesNumber")),
                    pct_of_shares=(_f(r.get("ownership")) or 0) / 100
                    if r.get("ownership") is not None
                    else None,
                    source="FMP (13F)",
                )
            )
        return out
