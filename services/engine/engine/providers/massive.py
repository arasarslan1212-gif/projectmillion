"""Benzinga data via Massive (formerly Polygon.io), the `pro` analyst source.

Endpoint: GET https://api.massive.com/benzinga/v1/ratings?ticker=...&limit=...&apiKey=...
Benzinga records carry the analyst name, firm, current/prior rating and current/prior target.
Field names differ slightly between Benzinga's native API and Massive's wrapper, so both
spellings are accepted.
"""

from __future__ import annotations

from datetime import date

from engine.http.client import HttpClient, ProviderError, get_http
from engine.providers.models import AnalystAction, RecommendationTrend, TargetConsensus
from engine.settings import get_settings

BASE = "https://api.massive.com"


def _g(r: dict, *keys):
    for k in keys:
        v = r.get(k)
        if v not in (None, ""):
            return v
    return None


def _f(x):
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


ACTION_MAP = {
    "upgrades": "upgrade",
    "upgrade": "upgrade",
    "downgrades": "downgrade",
    "downgrade": "downgrade",
    "initiates": "initiate",
    "initiates_coverage_on": "initiate",
    "initiated": "initiate",
    "maintains": "reiterate",
    "reiterates": "reiterate",
    "reiterated": "reiterate",
    "raises": "target_raise",
    "lowers": "target_cut",
    "terminates": "terminate",
    "terminates_coverage_on": "terminate",
}


class MassiveBenzinga:
    name = "Benzinga (via Massive)"
    provider_key = "massive"
    granularity = "analyst"

    def __init__(self, http: HttpClient | None = None) -> None:
        self.http = http or get_http()

    def _get(self, path: str, **params):
        s = get_settings()
        if not s.massive_api_key and s.data_mode != "mock":
            raise ProviderError("massive", "not_configured", "MASSIVE_API_KEY not set")
        params["apiKey"] = s.massive_api_key or ""
        return self.http.get("massive", f"{BASE}/{path}", params=params).body

    def actions(self, ticker: str) -> list[AnalystAction]:
        body = self._get("benzinga/v1/ratings", ticker=ticker.upper(), limit="1000", sort="date.desc")
        rows = body.get("results", []) if isinstance(body, dict) else body or []
        out = []
        for r in rows:
            try:
                d = date.fromisoformat(str(_g(r, "date"))[:10])
            except ValueError:
                continue
            firm = _g(r, "firm", "action_company_name", "analyst")
            if not firm:
                continue
            raw_action = str(_g(r, "rating_action", "action_company") or "").lower()
            pt_action = str(_g(r, "price_target_action", "action_pt") or "").lower()
            action = ACTION_MAP.get(raw_action) or ACTION_MAP.get(pt_action) or (raw_action or None)
            uid = str(
                _g(r, "benzinga_id", "id") or f"{ticker}-{d}-{firm}-{_g(r, 'price_target', 'pt_current')}"
            )
            out.append(
                AnalystAction(
                    ticker=ticker.upper(),
                    date=d,
                    analyst_name=_g(r, "analyst", "analyst_name"),
                    analyst_id=str(_g(r, "benzinga_analyst_id", "analyst_id") or "") or None,
                    firm=str(firm),
                    action=action,
                    rating=_g(r, "rating", "rating_current"),
                    rating_prior=_g(r, "previous_rating", "rating_prior"),
                    target=_f(_g(r, "price_target", "pt_current")),
                    target_prior=_f(_g(r, "previous_price_target", "pt_prior")),
                    url=_g(r, "benzinga_news_url", "url_news", "url"),
                    source="Benzinga via Massive",
                    source_uid=f"bz-{uid}",
                )
            )
        return out

    def recommendation_trends(self, ticker: str) -> list[RecommendationTrend]:
        return []

    def target_consensus(self, ticker: str) -> TargetConsensus | None:
        return None
