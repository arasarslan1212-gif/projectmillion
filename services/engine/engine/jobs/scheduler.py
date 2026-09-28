"""Scheduled jobs (APScheduler). Enabled with ENABLE_SCHEDULER=true (the `worker` service in compose)."""

from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler

log = logging.getLogger("engine.jobs")
_scheduler: BackgroundScheduler | None = None


def _safe(name: str, fn) -> None:
    try:
        log.info("job %s starting", name)
        fn()
        log.info("job %s finished", name)
    except Exception:  # a failed job must never kill the scheduler
        log.exception("job %s failed", name)


def registered_jobs() -> list[tuple[str, dict, object]]:
    """(name, cron kwargs, callable). Later milestones append refresh, scoring and alert jobs."""
    from engine.jobs import tasks

    return tasks.JOBS


def start_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is not None:
        return _scheduler
    sched = BackgroundScheduler(timezone="UTC")
    for name, cron, fn in registered_jobs():
        sched.add_job(lambda n=name, f=fn: _safe(n, f), "cron", id=name, replace_existing=True, **cron)
    sched.start()
    _scheduler = sched
    log.info("scheduler started with %d jobs", len(sched.get_jobs()))
    return sched


def run_forever() -> None:
    import time

    from engine.db.session import init_db

    init_db()
    start_scheduler()
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_forever()
