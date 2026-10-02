from fastapi.testclient import TestClient

from engine.api.main import app
from engine.data.service import Fetched, get_data


def test_health_search_sections_and_404():
    with TestClient(app) as c:
        h = c.get("/api/health").json()
        assert h["synthetic"] is True and h["fixture_set"] == "synthetic"
        res = c.get("/api/search", params={"q": "ZZT"}).json()["results"]
        assert res[0]["ticker"] == "ZZTEC"
        comp = c.get("/api/report/ZZTEC/section/company").json()
        assert comp["identity"]["name"].endswith("(Synthetic)")
        assert comp["stats"]["market_cap"]["value"] > 0
        assert comp["stats"]["pe"]["unit"] == "x"
        chart = c.get("/api/report/zztec/section/chart").json()
        assert len(chart["dates"]) == len(chart["ohlc"]["close"]) == len(chart["indicators"]["sma50"])
        assert chart["markers"]["splits"] == [{"date": "2020-08-31", "ratio": 4.0}]
        r = c.get("/api/report/NOPE/section/company")
        assert r.status_code == 404 and "not a US-listed ticker" in r.json()["detail"]


def test_unprofitable_company_pe_is_explained_not_invented():
    with TestClient(app) as c:
        comp = c.get("/api/report/ZZGRO/section/company").json()
        pe = comp["stats"]["pe"]
        assert pe["value"] is None and pe["status"] == "insufficient_data" and "negative" in pe["reason"]
        assert comp["identity"]["profile"] == "growth_unprofitable"


def test_unloadable_ticker_list_is_a_503_with_the_reason_not_an_unknown_ticker(monkeypatch):
    reason = "sec is temporarily unavailable"
    monkeypatch.setattr(get_data(), "symbols", lambda: Fetched(None, "SEC EDGAR", None, "missing", reason))
    with TestClient(app) as c:
        for path in ("/api/report/AAPL/section/company", "/api/search?q=aapl"):
            r = c.get(path)
            assert r.status_code == 503 and reason in r.json()["detail"], path
