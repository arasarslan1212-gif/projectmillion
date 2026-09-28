"""Job bodies. Each is idempotent and safe to re-run."""

from __future__ import annotations

import logging

from engine.data.service import get_data

log = logging.getLogger("engine.jobs")


def refresh_symbols() -> None:
    get_data().invalidate("symbols")
    get_data().symbols()


def score_analysts() -> None:
    from engine import clock
    from engine.analysts.service import score_and_store
    from engine.config import get_config

    res = score_and_store(get_data(), get_config(), clock.today(), clock.is_synthetic())
    log.info("analyst scores stored: %s", res)


JOBS: list[tuple[str, dict, object]] = [
    ("refresh_symbols", {"hour": 5, "minute": 7}, refresh_symbols),
    ("score_analysts", {"hour": 6, "minute": 13}, score_analysts),
]
