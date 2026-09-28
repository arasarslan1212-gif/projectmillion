"""FRED adapter. Requires a free API key. Attribution is required:
"This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis."
Only public-domain series are used (DGS10, CPIAUCSL, GDP, BAA10Y, DTWEXBGS, DCOILWTICO).
"""

from __future__ import annotations

from datetime import date

from engine.http.client import HttpClient, ProviderError, get_http
from engine.providers.models import MacroPoint, MacroSeries
from engine.settings import get_settings

BASE = "https://api.stlouisfed.org/fred"

SERIES_META = {
    "DGS10": ("10-Year Treasury Constant Maturity Rate", "percent"),
    "DGS3MO": ("3-Month Treasury Constant Maturity Rate", "percent"),
    "CPIAUCSL": ("Consumer Price Index for All Urban Consumers", "index"),
    "GDP": ("Gross Domestic Product", "billions USD"),
    "BAA10Y": ("Moody's Baa Corporate Bond Yield Relative to 10-Year Treasury", "percent"),
    "DTWEXBGS": ("Nominal Broad U.S. Dollar Index", "index"),
    "DCOILWTICO": ("Crude Oil Prices: West Texas Intermediate", "USD per barrel"),
}


class Fred:
    name = "FRED"
    provider_key = "fred"
    attribution = "This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis."

    def __init__(self, http: HttpClient | None = None) -> None:
        self.http = http or get_http()

    def series(self, series_id: str, start: date) -> MacroSeries:
        s = get_settings()
        if not s.fred_api_key and s.data_mode != "mock":
            raise ProviderError("fred", "not_configured", "FRED_API_KEY not set")
        body = self.http.get(
            "fred",
            f"{BASE}/series/observations",
            params={
                "series_id": series_id,
                "api_key": s.fred_api_key or "",
                "file_type": "json",
                "observation_start": start.isoformat(),
            },
        ).body
        pts = []
        for o in body.get("observations", []):
            v = o.get("value")
            if v in (None, ".", ""):
                continue
            try:
                pts.append(MacroPoint(date=date.fromisoformat(o["date"]), value=float(v)))
            except (ValueError, KeyError):
                continue
        title, units = SERIES_META.get(series_id, (series_id, ""))
        return MacroSeries(series_id=series_id, title=title, units=units, points=pts, source="FRED")
