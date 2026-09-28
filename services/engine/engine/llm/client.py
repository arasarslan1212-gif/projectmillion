"""The one place the engine talks to Claude.

Every call goes through `structured_call`, which:
- returns a pydantic-validated object (structured outputs via `messages.parse`) or None, never raw text;
- caches by a hash of (purpose, prompt version, model, input) so identical requests are never paid for twice;
- enforces the per-report token budget;
- logs tokens and cost for every call, cached or not;
- retries once on invalid output, and treats refusals, truncation and API errors as "no result",
  so callers always have a deterministic fallback.

Without ANTHROPIC_API_KEY the client is None and every call returns (None, info) immediately.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from dataclasses import dataclass, field

import anthropic
from pydantic import BaseModel, ValidationError

from engine.config import get_config
from engine.db import models as m
from engine.db.session import session_scope
from engine.settings import get_settings

log = logging.getLogger("engine.llm")

_client: object | None = None
_client_override: object | None = None
_lock = threading.Lock()


def set_client_for_tests(client: object | None) -> None:
    """Tests inject a fake with a `.messages.parse(**kwargs)` method; None restores the real client."""
    global _client_override, _client
    _client_override = client
    _client = None


def get_client():
    """The Anthropic client, or None when no API key is configured."""
    global _client
    if _client_override is not None:
        return _client_override
    s = get_settings()
    if not s.llm_enabled:
        return None
    with _lock:
        if _client is None:
            _client = anthropic.Anthropic(api_key=s.anthropic_api_key, max_retries=2, timeout=90.0)
        return _client


def llm_available() -> bool:
    return get_client() is not None


@dataclass
class Budget:
    """Token budget for one report. Calls that would exceed it are skipped (callers fall back)."""

    total: int
    used: int = 0
    skipped: int = 0
    lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def reserve(self, tokens: int) -> bool:
        with self.lock:
            if self.used + tokens > self.total:
                self.skipped += 1
                return False
            self.used += tokens
            return True

    def settle(self, reserved: int, actual: int) -> None:
        with self.lock:
            self.used += actual - reserved


@dataclass
class CallInfo:
    model: str
    purpose: str
    cached: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    attempts: int = 0
    error: str | None = None  # why no result was returned, if none was


def price_per_token(model: str) -> tuple[float, float]:
    table = get_config()["llm"]["pricing_per_mtok"]
    inp, out = table.get(model) or table.get(model.rsplit("-", 1)[0]) or table["default"]
    return inp / 1e6, out / 1e6


def cache_key(purpose: str, model: str, payload: object) -> str:
    version = get_config()["llm"]["prompt_versions"].get(purpose, "v1")
    blob = json.dumps(
        {"p": purpose, "v": version, "m": model, "x": payload}, sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(blob.encode()).hexdigest()


def cache_get(key: str) -> dict | list | None:
    with session_scope() as s:
        row = s.get(m.LlmCache, key)
        return row.output_json if row else None


def cache_put(key: str, model: str, purpose: str, info: CallInfo, output: dict | list) -> None:
    with session_scope() as s:
        s.merge(
            m.LlmCache(
                key=key,
                model=model,
                purpose=purpose,
                input_tokens=info.input_tokens,
                output_tokens=info.output_tokens,
                cost_usd=info.cost_usd,
                output_json=output,
            )
        )


def log_cost(ticker: str, report_id: str | None, info: CallInfo, validator_failures: int = 0) -> None:
    with session_scope() as s:
        s.add(
            m.LlmCostLog(
                ticker=ticker.upper(),
                report_id=report_id,
                model=info.model,
                purpose=info.purpose,
                input_tokens=info.input_tokens,
                output_tokens=info.output_tokens,
                cost_usd=info.cost_usd,
                cached=info.cached,
                validator_failures=validator_failures,
            )
        )


def structured_call[T: BaseModel](
    *,
    model: str,
    system: str,
    user: str,
    output: type[T],
    max_tokens: int,
    purpose: str,
    cache_payload: object,
    ticker: str,
    report_id: str | None,
    budget: Budget | None,
    check=None,
    extra: dict | None = None,
) -> tuple[T | None, CallInfo]:
    """One validated structured call. `check(parsed) -> list[str]` adds semantic validation (retried once)."""
    info = CallInfo(model=model, purpose=purpose)
    key = cache_key(purpose, model, cache_payload)
    hit = cache_get(key)
    if hit is not None:
        info.cached = True
        log_cost(ticker, report_id, info)
        return output.model_validate(hit), info
    client = get_client()
    if client is None:
        info.error = "LLM not configured (no ANTHROPIC_API_KEY)"
        return None, info
    reserve = len(system) // 4 + len(user) // 4 + max_tokens
    if budget is not None and not budget.reserve(reserve):
        info.error = "report token budget exhausted"
        return None, info
    problems: list[str] = []
    result: T | None = None
    try:
        for attempt in range(2):
            info.attempts = attempt + 1
            prompt = (
                user
                if not problems
                else (
                    user
                    + "\n\nYour previous answer was rejected for these reasons; fix them:\n- "
                    + "\n- ".join(problems[:10])
                )
            )
            try:
                resp = client.messages.parse(
                    model=model,
                    max_tokens=max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                    output_format=output,
                    **(extra or {}),
                )
            except ValidationError as e:  # the SDK validates the JSON against the schema
                problems = [f"output did not match the schema: {e.errors()[0]['msg']}"]
                continue
            u = getattr(resp, "usage", None)
            if u is not None:
                info.input_tokens += int(getattr(u, "input_tokens", 0) or 0)
                info.output_tokens += int(getattr(u, "output_tokens", 0) or 0)
            if resp.stop_reason == "refusal":
                info.error = "the model declined the request"
                break
            if resp.stop_reason == "max_tokens":
                problems = ["the answer was cut off; keep it shorter"]
                continue
            parsed = resp.parsed_output
            if parsed is None:
                problems = ["no structured output was returned"]
                continue
            problems = check(parsed) if check else []
            if not problems:
                result = parsed
                break
        else:
            info.error = "invalid output after retry: " + "; ".join(problems[:3])
    except anthropic.RateLimitError:
        info.error = "rate limited by the Claude API"
    except anthropic.APIStatusError as e:
        info.error = f"Claude API error {e.status_code}"
    except anthropic.APIConnectionError:
        info.error = "could not reach the Claude API"
    pin, pout = price_per_token(model)
    info.cost_usd = info.input_tokens * pin + info.output_tokens * pout
    if budget is not None:
        budget.settle(reserve, info.input_tokens + info.output_tokens)
    if info.input_tokens or info.output_tokens:
        log_cost(
            ticker, report_id, info, validator_failures=len(problems) if result is None else info.attempts - 1
        )
    if result is not None:
        cache_put(key, model, purpose, info, result.model_dump(mode="json"))
    elif info.error:
        log.warning("LLM %s call for %s returned no result: %s", purpose, ticker, info.error)
    return result, info


def log_validation(ticker: str, report_id: str | None, model: str, purpose: str, failures: int) -> None:
    """A zero-cost row recording narrative validation failures (for the per-report cost/quality log)."""
    log_cost(
        ticker, report_id, CallInfo(model=model, purpose=purpose, cached=True), validator_failures=failures
    )


def report_budget(ctx) -> Budget:
    return ctx.section("_llm_budget", lambda c: Budget(get_settings().llm_report_token_budget))


def report_id(ctx) -> str:
    return f"{ctx.ticker}:{ctx.as_of.isoformat()}"
