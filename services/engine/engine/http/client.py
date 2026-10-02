"""Shared HTTP layer for every provider adapter.

Responsibilities:
- per-provider rate limiting (token bucket)
- retries with exponential backoff and jitter on transient errors (honours Retry-After)
- a circuit breaker per provider
- record/replay of responses as fixtures (DATA_MODE=record / DATA_MODE=mock)

Secrets (API keys) are stripped before a request is keyed or written to disk.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import random
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from engine.settings import Settings, get_settings

SECRET_PARAMS = {"apikey", "api_key", "apiKey", "token", "api_token", "access_key"}
SECRET_HEADERS = {"authorization", "x-api-key"}


class ProviderError(Exception):
    """Raised by the HTTP layer and adapters. `kind` drives the UI's "missing because" text."""

    KINDS = {
        "not_configured",  # no API key / provider disabled on this tier
        "plan_restricted",  # provider says the endpoint needs a higher plan
        "not_found",
        "auth",
        "rate_limited",
        "unavailable",  # network error, 5xx, circuit open
        "fixture_missing",  # mock mode and nothing recorded for this request
        "bad_response",
    }

    def __init__(self, provider: str, kind: str, message: str, hint: str | None = None) -> None:
        assert kind in self.KINDS, kind
        super().__init__(f"[{provider}] {kind}: {message}")
        self.provider = provider
        self.kind = kind
        self.message = message
        self.hint = hint  # what the operator can do about it, appended to the user-facing reason

    def user_reason(self) -> str:
        reason = self._reason()
        return f"{reason}. {self.hint}" if self.hint else reason

    def _reason(self) -> str:
        if self.provider == "sec" and self.kind == "auth":  # the SEC has no keys; a 403 means the User-Agent
            return (
                "SEC EDGAR refused the request: its fair-access policy requires a User-Agent naming the app "
                "and a contact email (SEC_USER_AGENT)"
            )
        return {
            "not_configured": f"{self.provider} is not configured on this data tier",
            "plan_restricted": f"{self.provider} requires a higher subscription plan for this data",
            "not_found": f"{self.provider} has no data for this request",
            "auth": f"{self.provider} rejected the API key",
            "rate_limited": f"{self.provider} rate limit reached; try again later",
            "unavailable": f"{self.provider} is temporarily unavailable",
            "fixture_missing": f"no recorded {self.provider} data for this request (mock mode)",
            "bad_response": f"{self.provider} returned data in an unexpected format",
        }[self.kind]


@dataclass
class ProviderPolicy:
    rate_per_sec: float
    burst: int = 1
    max_retries: int = 4
    timeout_s: float = 30.0
    breaker_threshold: int = 5
    breaker_cooldown_s: float = 60.0


DEFAULT_POLICIES: dict[str, ProviderPolicy] = {
    "sec": ProviderPolicy(rate_per_sec=5.0, burst=2),  # SEC fair access allows 10/s; stay well below
    "fred": ProviderPolicy(rate_per_sec=1.5, burst=2),  # ~120/min documented
    "finra": ProviderPolicy(rate_per_sec=2.0, burst=2),
    # free tier: 50/hour and 1000/day; pacing can't raise that, so it only keeps bursts polite
    "tiingo": ProviderPolicy(rate_per_sec=1.0, burst=5),
    "fmp": ProviderPolicy(rate_per_sec=4.0, burst=4),  # starter: 300/min
    "finnhub": ProviderPolicy(rate_per_sec=0.9, burst=2),  # free: 60/min
    "massive": ProviderPolicy(rate_per_sec=1.5, burst=2),
}


class _TokenBucket:
    def __init__(self, rate: float, burst: int) -> None:
        self.rate = rate
        self.capacity = max(1, burst)
        self.tokens = float(self.capacity)
        self.updated = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self.lock:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.updated) * self.rate)
                self.updated = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                wait = (1 - self.tokens) / self.rate
            time.sleep(wait)


@dataclass
class _Breaker:
    threshold: int
    cooldown: float
    failures: int = 0
    opened_at: float | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def allow(self) -> bool:
        with self.lock:
            if self.opened_at is None:
                return True
            if time.monotonic() - self.opened_at >= self.cooldown:
                return True  # half-open: let one request through
            return False

    def record(self, ok: bool) -> None:
        with self.lock:
            if ok:
                self.failures = 0
                self.opened_at = None
            else:
                self.failures += 1
                if self.failures >= self.threshold:
                    self.opened_at = time.monotonic()

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "closed"
        return "open" if time.monotonic() - self.opened_at < self.cooldown else "half-open"


def _clean_params(params: dict[str, Any] | None) -> dict[str, str]:
    if not params:
        return {}
    return {k: str(v) for k, v in sorted(params.items()) if k not in SECRET_PARAMS and v is not None}


def fixture_key(provider: str, method: str, url: str, params: dict[str, Any] | None, body: Any = None) -> str:
    parts = urlsplit(url)
    canonical = json.dumps(
        {
            "p": provider,
            "m": method.upper(),
            "u": f"{parts.netloc}{parts.path}",
            "q": _clean_params(params),
            "b": body,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha1(canonical.encode()).hexdigest()


@dataclass
class HttpResponse:
    status: int
    body: Any  # parsed JSON, or str for text responses
    content_type: str
    from_fixture: bool = False


class FixtureStore:
    """Fixtures live at fixtures/<set>/<provider>/<key>.json.gz with an index.jsonl per set."""

    # Where a missing fixture file can be fetched from: called with "<set>/<provider>/<key>.json.gz", returns the
    # bytes or None. The in-browser engine sets it to download recordings from the site on first use.
    fetcher: Callable[[str], bytes | None] | None = None

    def __init__(self, root: Path, set_name: str) -> None:
        self.dir = root / set_name
        self.set_name = set_name
        self._lock = threading.Lock()

    def path(self, provider: str, key: str) -> Path:
        return self.dir / provider / f"{key}.json.gz"

    def load(self, provider: str, key: str) -> HttpResponse | None:
        p = self.path(provider, key)
        if not p.exists() and FixtureStore.fetcher is not None:
            data = FixtureStore.fetcher(f"{self.set_name}/{provider}/{key}.json.gz")
            if data:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
        if not p.exists():
            return None
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            rec = json.load(fh)
        return HttpResponse(rec["status"], rec["body"], rec.get("content_type", "application/json"), True)

    def save(
        self,
        provider: str,
        key: str,
        method: str,
        url: str,
        params: dict[str, Any] | None,
        body: Any,
        resp: HttpResponse,
    ) -> None:
        p = self.path(provider, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        rec = {
            "request": {"method": method, "url": url, "params": _clean_params(params), "body": body},
            "status": resp.status,
            "content_type": resp.content_type,
            "body": resp.body,
        }
        # mtime=0 keeps the gzip bytes deterministic, so re-recording unchanged data is a no-op diff.
        with open(p, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
            gz.write(json.dumps(rec, separators=(",", ":"), sort_keys=True).encode("utf-8"))
        with self._lock, open(self.dir / "index.jsonl", "a", encoding="utf-8") as idx:
            idx.write(
                json.dumps({"provider": provider, "key": key, "url": url, "params": _clean_params(params)})
                + "\n"
            )


class HttpClient:
    def __init__(
        self, settings: Settings | None = None, transport: httpx.BaseTransport | None = None
    ) -> None:
        self.settings = settings or get_settings()
        mode = self.settings.data_mode
        # The synthetic fixture set is generated on the fly by an in-process transport (D-013);
        # the recorded set is replayed from files.
        self.synthetic = mode == "mock" and self.settings.active_fixture_set == "synthetic"
        if self.synthetic and transport is None:
            from engine.synthetic.server import synthetic_transport

            transport = synthetic_transport()
        self._client = httpx.Client(transport=transport, follow_redirects=True)
        self._buckets: dict[str, _TokenBucket] = {}
        self._breakers: dict[str, _Breaker] = {}
        self._lock = threading.Lock()
        self.replay_store = (
            FixtureStore(self.settings.fixtures_dir, self.settings.active_fixture_set)
            if mode == "mock" and not self.synthetic
            else None
        )
        self.record_store = (
            FixtureStore(self.settings.fixtures_dir, self.settings.record_set) if mode == "record" else None
        )
        self.stats: dict[str, dict[str, int]] = {}

    # -- internals -----------------------------------------------------------------
    def _policy(self, provider: str) -> ProviderPolicy:
        return DEFAULT_POLICIES.get(provider, ProviderPolicy(rate_per_sec=1.0))

    def _bucket(self, provider: str) -> _TokenBucket:
        with self._lock:
            if provider not in self._buckets:
                pol = self._policy(provider)
                self._buckets[provider] = _TokenBucket(pol.rate_per_sec, pol.burst)
            return self._buckets[provider]

    def breaker(self, provider: str) -> _Breaker:
        with self._lock:
            if provider not in self._breakers:
                pol = self._policy(provider)
                self._breakers[provider] = _Breaker(pol.breaker_threshold, pol.breaker_cooldown_s)
            return self._breakers[provider]

    def _count(self, provider: str, what: str) -> None:
        s = self.stats.setdefault(provider, {})
        s[what] = s.get(what, 0) + 1

    # -- public --------------------------------------------------------------------
    def request(
        self,
        provider: str,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        headers: dict[str, str] | None = None,
        expect: str = "json",
    ) -> HttpResponse:
        key = fixture_key(provider, method, url, params, json_body)

        if self.replay_store is not None:
            resp = self.replay_store.load(provider, key)
            self._count(provider, "replay")
            if resp is None:
                raise ProviderError(provider, "fixture_missing", f"{method} {url} {_clean_params(params)}")
            return self._check_status(provider, resp)

        breaker = self.breaker(provider)
        if not breaker.allow():
            raise ProviderError(provider, "unavailable", "circuit breaker open after repeated failures")

        pol = self._policy(provider)
        attempt = 0
        while True:
            attempt += 1
            if not self.synthetic:
                self._bucket(provider).acquire()
            try:
                r = self._client.request(
                    method, url, params=params, json=json_body, headers=headers, timeout=pol.timeout_s
                )
            except httpx.TransportError as exc:
                self._count(provider, "transport_error")
                if attempt > pol.max_retries:
                    breaker.record(False)
                    raise ProviderError(provider, "unavailable", repr(exc)) from exc
                self._sleep_backoff(attempt, None)
                continue

            if r.status_code == 429 or r.status_code >= 500:
                self._count(provider, f"http_{r.status_code}")
                if attempt > pol.max_retries:
                    breaker.record(False)
                    kind = "rate_limited" if r.status_code == 429 else "unavailable"
                    raise ProviderError(provider, kind, f"HTTP {r.status_code} after {attempt} attempts")
                self._sleep_backoff(attempt, r.headers.get("retry-after"))
                continue

            breaker.record(True)
            ctype = r.headers.get("content-type", "")
            body: Any
            if expect == "json" or "json" in ctype:
                try:
                    body = r.json()
                except ValueError:
                    body = r.text
            else:
                body = r.text
            resp = HttpResponse(r.status_code, body, ctype, from_fixture=self.synthetic)
            self._count(provider, "synthetic" if self.synthetic else "live")
            if self.record_store is not None and r.status_code < 500:
                self.record_store.save(provider, key, method, url, params, json_body, resp)
            return self._check_status(provider, resp)

    def get(self, provider: str, url: str, **kw: Any) -> HttpResponse:
        return self.request(provider, "GET", url, **kw)

    def post(self, provider: str, url: str, **kw: Any) -> HttpResponse:
        return self.request(provider, "POST", url, **kw)

    @staticmethod
    def _sleep_backoff(attempt: int, retry_after: str | None) -> None:
        if retry_after:
            try:
                time.sleep(min(float(retry_after), 30.0))
                return
            except ValueError:
                pass
        base = 0.5 * (2 ** (attempt - 1))
        time.sleep(min(base, 16.0) + random.uniform(0, base / 2))

    @staticmethod
    def _check_status(provider: str, resp: HttpResponse) -> HttpResponse:
        if resp.status in (401, 403):
            body = str(resp.body)[:300].lower()
            kind = (
                "plan_restricted"
                # Finnhub answers premium endpoints with "You don't have access to this resource."
                if any(w in body for w in ("plan", "subscription", "premium", "access to this resource"))
                else "auth"
            )
            raise ProviderError(provider, kind, f"HTTP {resp.status}: {str(resp.body)[:200]}")
        if resp.status == 402:
            raise ProviderError(provider, "plan_restricted", "HTTP 402")
        if resp.status == 404:
            raise ProviderError(provider, "not_found", "HTTP 404")
        if resp.status >= 400:
            raise ProviderError(provider, "bad_response", f"HTTP {resp.status}: {str(resp.body)[:200]}")
        return resp


_shared: HttpClient | None = None
_shared_lock = threading.Lock()


def get_http() -> HttpClient:
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = HttpClient()
        return _shared


def reset_http(client: HttpClient | None = None) -> None:
    global _shared
    with _shared_lock:
        _shared = client
