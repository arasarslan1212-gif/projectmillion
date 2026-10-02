from datetime import date

import httpx
import pytest

from engine.http.client import FixtureStore, HttpClient, ProviderError, fixture_key
from engine.settings import Settings


def _client(handler, tmp_path, mode="live"):
    s = Settings(data_mode=mode, fixtures_dir=tmp_path, fixture_set="recorded", record_set="recorded")
    return HttpClient(settings=s, transport=httpx.MockTransport(handler))


def test_fixture_key_ignores_secrets_and_param_order():
    a = fixture_key("fmp", "GET", "https://x.test/a", {"symbol": "AAPL", "apikey": "SECRET1"})
    b = fixture_key("fmp", "GET", "https://x.test/a", {"apikey": "OTHER", "symbol": "AAPL"})
    assert a == b
    assert a != fixture_key("fmp", "GET", "https://x.test/a", {"symbol": "MSFT"})


def test_retries_transient_errors_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.http.client.time.sleep", lambda s: None)
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, json={"error": "busy"})
        return httpx.Response(200, json={"ok": True})

    c = _client(handler, tmp_path)
    assert c.get("sec", "https://x.test/r").body == {"ok": True}
    assert calls["n"] == 3


def test_circuit_breaker_opens_after_repeated_failures(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.http.client.time.sleep", lambda s: None)

    def handler(req):
        return httpx.Response(500, text="down")

    c = _client(handler, tmp_path)
    for _ in range(5):
        with pytest.raises(ProviderError) as e:
            c.get("finra", "https://x.test/r")
        assert e.value.kind == "unavailable"
    assert c.breaker("finra").state == "open"
    with pytest.raises(ProviderError, match="circuit breaker"):
        c.get("finra", "https://x.test/r")


def test_status_mapping(tmp_path):
    def handler(req):
        if req.url.path == "/missing":
            return httpx.Response(404, json={})
        return httpx.Response(403, text="Your subscription plan does not include this endpoint")

    c = _client(handler, tmp_path)
    with pytest.raises(ProviderError) as e:
        c.get("fmp", "https://x.test/missing")
    assert e.value.kind == "not_found"
    with pytest.raises(ProviderError) as e:
        c.get("fmp", "https://x.test/premium")
    assert e.value.kind == "plan_restricted"


def test_finnhub_premium_endpoint_is_a_plan_limit_not_a_bad_key(tmp_path, monkeypatch):
    from engine.providers.finnhub import Finnhub

    monkeypatch.setenv("FINNHUB_API_KEY", "k")

    def handler(req):
        return httpx.Response(403, json={"error": "You don't have access to this resource."})

    c = _client(handler, tmp_path)
    with pytest.raises(ProviderError) as e:
        c.get("finnhub", "https://x.test/stock/candle")
    assert e.value.kind == "plan_restricted"
    from engine.settings import reset_settings_cache

    reset_settings_cache()
    try:
        with pytest.raises(ProviderError) as e:
            Finnhub(c).history("AAPL", date(2025, 1, 1), date(2025, 6, 30))
    finally:
        reset_settings_cache()
    assert "higher subscription plan" in e.value.user_reason() and "TIINGO_API_KEY" in e.value.user_reason()


def test_pasted_secrets_are_cleaned(monkeypatch):
    # a trailing newline or space makes an HTTP header invalid, failing every request before it is sent
    monkeypatch.setenv("SEC_USER_AGENT", "Jane  Doe\tjane@example.com \n")
    monkeypatch.setenv("FINNHUB_API_KEY", " abc123\n")
    monkeypatch.setenv("TIINGO_API_KEY", "  ")
    s = Settings()
    assert s.sec_user_agent == "Jane Doe jane@example.com"
    assert s.finnhub_api_key == "abc123" and s.tiingo_api_key is None


def test_record_then_replay_without_secrets(tmp_path):
    def handler(req):
        return httpx.Response(200, json={"price": 1.5, "echo": req.url.params.get("symbol")})

    rec = _client(handler, tmp_path, mode="record")
    rec.get("fmp", "https://x.test/quote", params={"symbol": "AAPL", "apikey": "TOPSECRET"})
    raw = b"".join(p.read_bytes() for p in (tmp_path / "recorded").rglob("*.gz"))
    index = (tmp_path / "recorded" / "index.jsonl").read_text()
    assert b"TOPSECRET" not in raw and "TOPSECRET" not in index

    def boom(req):
        raise AssertionError("mock mode must not touch the network")

    rep = _client(boom, tmp_path, mode="mock")
    assert (
        rep.get("fmp", "https://x.test/quote", params={"symbol": "AAPL", "apikey": "different"}).body["price"]
        == 1.5
    )
    with pytest.raises(ProviderError) as e:
        rep.get("fmp", "https://x.test/quote", params={"symbol": "MSFT"})
    assert e.value.kind == "fixture_missing"


def test_fixture_store_is_deterministic(tmp_path):
    from engine.http.client import HttpResponse

    st = FixtureStore(tmp_path, "recorded")
    st.save("sec", "k1", "GET", "https://x.test", None, None, HttpResponse(200, {"a": 1}, "application/json"))
    b1 = st.path("sec", "k1").read_bytes()
    st.save("sec", "k1", "GET", "https://x.test", None, None, HttpResponse(200, {"a": 1}, "application/json"))
    assert st.path("sec", "k1").read_bytes() == b1
