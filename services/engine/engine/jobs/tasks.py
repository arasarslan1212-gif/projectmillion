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


def score_outcomes() -> None:
    """Grade every snapshot whose 12-month horizon has passed."""
    from engine.track.scoring import score_due

    log.info("snapshot outcomes: %s", score_due())


def recalibrate() -> None:
    """Refit the prob-up map and range scale on all known outcomes; every change is logged."""
    from engine import clock
    from engine.track.calibration import recalibrate as fit

    res = fit(clock.today(), clock.is_synthetic())
    log.info("recalibration: %s", res["reason"])


def evaluate_alerts() -> None:
    """Check the watchlist's alert rules and add new events to the inbox."""
    from engine.alerts.service import evaluate

    log.info("alerts: %s", evaluate())


JOBS: list[tuple[str, dict, object]] = [
    ("refresh_symbols", {"hour": 5, "minute": 7}, refresh_symbols),
    ("score_analysts", {"hour": 6, "minute": 13}, score_analysts),
    ("score_outcomes", {"hour": 6, "minute": 41}, score_outcomes),
    ("recalibrate", {"day_of_week": "sun", "hour": 7, "minute": 3}, recalibrate),
    ("evaluate_alerts", {"hour": 7, "minute": 29}, evaluate_alerts),
]
