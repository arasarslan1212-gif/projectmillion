"""Runtime settings, read from environment variables (see .env.example at repo root)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(REPO_ROOT / ".env"), extra="ignore")

    # live = real HTTP; mock = replay fixtures only (no network, no keys);
    # record = real HTTP and save every response as a fixture.
    data_mode: Literal["live", "mock", "record"] = "mock"
    data_tier: Literal["free", "starter", "pro"] = "starter"
    fixtures_dir: Path = REPO_ROOT / "fixtures"
    # Fixture set used in mock mode: "recorded" (real, captured with `make record-fixtures`),
    # "synthetic" (generated, fake tickers, always labeled) or "auto" (recorded if present).
    # Sets are never mixed, so synthetic companies can never be compared against real ones.
    fixture_set: str = "auto"
    record_set: str = "recorded"

    database_url: str = f"sqlite:///{REPO_ROOT / 'services' / 'engine' / 'dev.db'}"
    # WAL lets the API read while jobs write. The in-browser engine turns it off (no shared memory there).
    sqlite_wal: bool = True
    config_path: Path = REPO_ROOT / "config" / "engine.yaml"
    metrics_path: Path = REPO_ROOT / "config" / "metrics.yaml"

    sec_user_agent: str = Field(default="StockAnalysisApp contact@example.com")
    fred_api_key: str | None = None
    fmp_api_key: str | None = None
    finnhub_api_key: str | None = None
    tiingo_api_key: str | None = None
    massive_api_key: str | None = None

    anthropic_api_key: str | None = None
    fast_model: str = "claude-haiku-4-5-20251001"
    reasoning_model: str = "claude-sonnet-5"
    llm_report_token_budget: int = 60_000

    # Wall-clock "today". Overridable for deterministic tests and fixture replay.
    as_of_override: str | None = None
    enable_scheduler: bool = False
    cors_origins: str = "http://localhost:3000"

    @property
    def active_fixture_set(self) -> str:
        if self.fixture_set != "auto":
            return self.fixture_set
        recorded = self.fixtures_dir / "recorded" / "index.jsonl"
        return "recorded" if recorded.exists() and recorded.stat().st_size > 0 else "synthetic"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
