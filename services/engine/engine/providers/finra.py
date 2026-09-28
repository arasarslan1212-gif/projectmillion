"""FINRA equity short interest via the FINRA Query API (public dataset).

Dataset: group `otcMarket`, name `consolidatedShortInterest` (exchange-listed and OTC).
Field names follow FINRA's published metadata; they are parsed defensively because the
adapter could not be exercised against the live API from the build environment.
"""

from __future__ import annotations

from datetime import date

from engine.http.client import HttpClient, get_http
from engine.providers.models import ShortInterestPoint

URL = "https://api.finra.org/data/group/otcMarket/name/consolidatedShortInterest"


def _first(d: dict, *keys):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


class Finra:
    name = "FINRA"
    provider_key = "finra"

    def __init__(self, http: HttpClient | None = None) -> None:
        self.http = http or get_http()

    def short_interest(self, ticker: str) -> list[ShortInterestPoint]:
        body = self.http.post(
            "finra",
            URL,
            json_body={
                "compareFilters": [
                    {"compareType": "EQUAL", "fieldName": "symbolCode", "fieldValue": ticker.upper()}
                ],
                "sortFields": ["-settlementDate"],
                "limit": 60,
            },
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        ).body
        rows = body if isinstance(body, list) else body.get("data", []) if isinstance(body, dict) else []
        out = []
        for r in rows:
            sd = _first(r, "settlementDate", "settlement_date")
            si = _first(r, "currentShortPositionQuantity", "currentShortShareNumber", "shortInterest")
            if sd is None or si is None:
                continue
            try:
                d = date.fromisoformat(str(sd)[:10])
                adv = _first(r, "averageDailyVolumeQuantity", "averageShortShareNumber")
                dtc = _first(r, "daysToCoverQuantity", "daysToCover")
                out.append(
                    ShortInterestPoint(
                        settlement_date=d,
                        short_interest=float(si),
                        avg_daily_volume=float(adv) if adv is not None else None,
                        days_to_cover=float(dtc) if dtc is not None else None,
                        source="FINRA",
                    )
                )
            except (TypeError, ValueError):
                continue
        out.sort(key=lambda p: p.settlement_date)
        return out
