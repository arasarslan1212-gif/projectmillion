"""Walk-forward, point-in-time backtest.

For each date (every few months from the configured start until one horizon before today), the engine builds
point-in-time reports that see only data public on that date: filings by filing date, prices to that close, analyst
calls made by then, short interest after its publication lag. It runs the raw model (no track-record feedback),
stores each result as a backtest snapshot, then scores every snapshot whose horizon has passed.

Caveats, shown wherever results appear: the universe is today's listed companies (survivorship bias), provider
history may have been restated since, and these are simulations, not live forecasts.

Usage: python -m engine.track.backtest [--tickers A,B] [--start 2019-03-29] [--every-months 3] [--limit N]
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import date, timedelta

import pandas as pd

from engine import clock
from engine.config import get_config
from engine.data.service import get_data
from engine.report.builder import contexts
from engine.track import calibration, scoring, snapshots

log = logging.getLogger("engine.track")

CAVEATS = [
    "Backtest, not a live track record: these estimates were produced now by replaying the engine on past data.",
    "Survivorship bias: the universe is companies listed today, so failures and delistings are under-represented.",
    "Point-in-time data: filings are used from their filing dates and analyst calls from their dates, but "
    "providers may have restated history since.",
    "The backtest grades the raw model; live reports may apply a recalibration fitted on these results.",
]
SYNTHETIC_CAVEAT = (
    "Synthetic data: these results grade the engine against a simulated market, not real stocks."
)


def walk_dates(start: date, end: date, every_months: int) -> list[date]:
    """Month-end business days from `start`, every `every_months` months, up to `end`."""
    out = []
    for ts in pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq=f"{every_months}BME"):
        out.append(ts.date())
    return out


def default_universe() -> list[str]:
    """The six headline tickers plus a few peers per profile (synthetic), or configured tickers (real data)."""
    cfg = get_config()["track"]["backtest"]
    if clock.is_synthetic():
        from engine.synthetic.world import PEER_PREFIX

        head = ["ZZTEC", "ZZBNK", "ZZREI", "ZZGRO", "ZZUTL", "ZZSML"]
        k = int(cfg["per_profile"])
        peers = [f"{p}{i:02d}" for p in PEER_PREFIX.values() for i in range(1, k + 1)]
        listed = {s.ticker for s in (get_data().symbols().value or [])}
        return [t for t in head + peers if t in listed]
    return [t.upper() for t in cfg.get("tickers") or []]


def run(
    tickers: list[str] | None = None,
    start: date | None = None,
    every_months: int | None = None,
    end: date | None = None,
    progress: bool = False,
) -> dict:
    cfg = get_config()
    t = cfg["track"]
    tickers = tickers or default_universe()
    if not tickers:
        raise SystemExit("no backtest tickers: pass --tickers or set track.backtest.tickers")
    horizon = int(t["horizon_days"])
    end = end or clock.today() - timedelta(days=horizon)
    dates = walk_dates(
        start or date.fromisoformat(t["backtest"]["start"]),
        end,
        every_months or int(t["backtest"]["every_months"]),
    )
    stored, failed, t0 = 0, 0, time.time()
    for i, d in enumerate(dates):
        rows = []
        with calibration.raw_model():
            for tk in tickers:
                try:
                    ctx = contexts.get(tk, d, True)
                    row = snapshots.snapshot_row(ctx, is_backtest=True)
                    if row:
                        rows.append(row)
                except Exception as exc:  # one company failing must not stop the run
                    failed += 1
                    log.warning("backtest %s at %s failed: %s", tk, d, exc)
        stored += snapshots.insert(rows)
        contexts.d.clear()  # point-in-time contexts are large; keep memory flat
        if progress:
            print(f"[{i + 1}/{len(dates)}] {d}: {len(rows)} snapshots ({time.time() - t0:.0f}s)", flush=True)
    scored = scoring.score_due(tickers=tickers)
    return {"dates": len(dates), "tickers": len(tickers), "stored": stored, "failed": failed, **scored}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tickers", help="comma-separated tickers (default: the configured universe)")
    ap.add_argument("--start", type=date.fromisoformat)
    ap.add_argument("--every-months", type=int)
    ap.add_argument("--limit", type=int, help="use only the first N tickers")
    ap.add_argument("--recalibrate", action="store_true", help="fit and log a recalibration afterwards")
    a = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    from engine.db.session import init_db

    init_db()
    tickers = [x.strip().upper() for x in a.tickers.split(",")] if a.tickers else default_universe()
    if a.limit:
        tickers = tickers[: a.limit]
    res = run(tickers, a.start, a.every_months, progress=True)
    print(res)
    if a.recalibrate:
        r = calibration.recalibrate(clock.today(), clock.is_synthetic())
        print(r["reason"])


if __name__ == "__main__":
    main()
