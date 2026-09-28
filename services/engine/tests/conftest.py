"""Test configuration: every test runs in mock mode against the synthetic world, with a fresh SQLite DB."""

from __future__ import annotations

import os
import tempfile

import pytest

_TMP = tempfile.mkdtemp(prefix="engine-tests-")
os.environ.update(
    {
        "DATA_MODE": "mock",
        "FIXTURE_SET": "synthetic",
        "DATA_TIER": "starter",
        "DATABASE_URL": f"sqlite:///{_TMP}/test.db",
        "ANTHROPIC_API_KEY": "",
        "AS_OF_OVERRIDE": "",
    }
)


def _reset() -> None:
    from engine.config import load_config
    from engine.data import service
    from engine.db.session import init_db, reset_db_caches
    from engine.http import client
    from engine.providers import registry
    from engine.report import builder
    from engine.settings import reset_settings_cache

    reset_settings_cache()
    reset_db_caches()
    load_config.cache_clear()
    registry.get_providers.cache_clear()
    client.reset_http(None)
    service.reset_data(None)
    builder.contexts.d.clear()
    init_db()


@pytest.fixture(scope="session", autouse=True)
def _session_env():
    _reset()
    yield


@pytest.fixture
def reset_env():
    """For tests that change settings through environment variables."""
    yield _reset
    _reset()
