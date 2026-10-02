"""The free tier with Finnhub alone: no daily price history (premium on Finnhub), but a live quote."""

from engine.data.service import Fetched, get_data
from engine.report.builder import get_section, section_names


def test_reports_price_off_the_quote_when_there_is_no_history(reset_env, monkeypatch):
    monkeypatch.setenv("DATA_TIER", "free")
    monkeypatch.setenv("PRICE_SOURCE", "finnhub")
    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    reset_env()
    data = get_data()
    asked: list[str] = []

    def no_history(ticker, days=None):
        asked.append(ticker.upper())
        return Fetched(None, "Finnhub", None, "missing", "finnhub requires a higher subscription plan")

    monkeypatch.setattr(data, "prices", no_history)
    quote = data.quote("ZZTEC").value
    assert quote is not None

    out = {n: get_section("ZZTEC", n) for n in section_names()}
    assert not [n for n, s in out.items() if s["status"] == "error"]
    assert out["company"]["price"]["price"]["value"] == quote.price
    assert out["valuation"]["status"] == "ok", out["valuation"].get("reason")
    assert out["chart"]["status"] == "missing"
    # dividend events come with the price history: unknown, not "never paid"
    assert out["dividends"]["status"] == "missing"
    # peers are priced off their quotes, sparing a rate-limited history source
    peers = [r for r in out["peers"]["rows"] if not r["is_subject"]]
    assert peers and all(r["metrics"]["market_cap"] for r in peers)
    assert not {r["ticker"] for r in peers} & set(asked)
