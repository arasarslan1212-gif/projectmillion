"""Job bodies. Each is idempotent and safe to re-run."""

from __future__ import annotations

import logging

from engine.data.service import get_data

log = logging.getLogger("engine.jobs")


def refresh_symbols() -> None:
    get_data().invalidate("symbols")
    get_data().symbols()


JOBS: list[tuple[str, dict, object]] = [
    ("refresh_symbols", {"hour": 5, "minute": 7}, refresh_symbols),
]
