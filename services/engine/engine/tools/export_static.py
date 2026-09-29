"""Export the engine's API responses as static JSON for the read-only web demo (GitHub Pages).

Every file is the exact response of the live API endpoint (called in-process through the FastAPI app), so the static
demo shows precisely what the running app shows for the synthetic market. The web app's static mode maps each API
request to one of these files (apps/web/lib/static.ts holds the same mapping).

Usage (from services/engine, synthetic mock mode):
    DATA_MODE=mock FIXTURE_SET=synthetic DATABASE_URL=sqlite:///demo.db \\
        python -m engine.tools.export_static --out ../../apps/web/public/data
"""

from __future__ import annotations

import argparse
import itertools
import json
import logging
import time
from pathlib import Path

from fastapi.testclient import TestClient

from engine import clock
from engine.data.service import get_data
from engine.synthetic.world import BENCHMARKS, FACTOR_FUNDS

DEMO_TICKERS = ["ZZTEC", "ZZBNK", "ZZREI", "ZZGRO", "ZZUTL", "ZZSML"]
RANGES = ["6m", "1y", "3y", "5y"]
KINDS = ["backtest", "live", "all"]

log = logging.getLogger("engine.export")


def key(tickers: list[str] | tuple[str, ...]) -> str:
    """File-name key for a set of tickers (order-independent), mirrored in apps/web/lib/static.ts."""
    return "_".join(sorted(t.upper() for t in tickers))


class Exporter:
    def __init__(self, client: TestClient, out: Path) -> None:
        self.c, self.out, self.n, self.bytes = client, out, 0, 0

    def get(self, api: str, file: str, method: str = "GET", body: dict | None = None) -> dict:
        r = self.c.request(method, f"/api{api}", json=body)
        if r.status_code != 200:
            raise RuntimeError(f"{method} {api} -> {r.status_code}: {r.text[:200]}")
        data = r.json()
        if file:
            self.write(file, data)
        return data

    def write(self, file: str, data) -> None:
        p = self.out / file
        p.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(data, separators=(",", ":"), allow_nan=False, default=str)
        p.write_text(raw)
        self.n += 1
        self.bytes += len(raw)


def export(out: Path, tickers: list[str], backtest: bool) -> dict:
    from engine.api.main import app
    from engine.report.builder import section_names

    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    if backtest:
        from engine.track import backtest as bt
        from engine.track.calibration import recalibrate

        log.warning("running the walk-forward backtest (a few minutes)")
        print(bt.run(progress=True))
        print(recalibrate(clock.today(), clock.is_synthetic())["reason"])

    with TestClient(app) as client:
        ex = Exporter(client, out)
        health = ex.get("/health", "health.json")
        ex.get("/meta/definitions", "meta/definitions.json")
        ex.get("/meta/methodology", "meta/methodology.json")

        for t in tickers:
            for name in section_names():
                ex.get(f"/report/{t}/section/{name}", f"report/{t}/{name}.json")
            print(f"{t}: report exported ({time.time() - t0:.0f}s)", flush=True)

        # a shared snapshot, so the /s/{token} page has something to show
        share = ex.get(f"/report/{tickers[0]}/share", "", method="POST")
        ex.get(f"/snapshot/{share['token']}", f"snapshot/{share['token']}.json")

        for n in range(2, min(4, len(tickers)) + 1):
            for combo in itertools.combinations(tickers, n):
                for rng in RANGES:
                    ex.get(
                        f"/compare?tickers={','.join(combo)}&range={rng}", f"compare/{key(combo)}_{rng}.json"
                    )
        print(f"compare exported ({time.time() - t0:.0f}s)", flush=True)
        for n in range(1, len(tickers) + 1):
            for combo in itertools.combinations(tickers, n):
                ex.get(f"/watchlist/summary?tickers={','.join(combo)}", f"watchlist/{key(combo)}.json")
        ex.write("watchlist/_empty.json", {"holdings": [], "aggregate": None, "errors": []})

        # alerts for a watchlist of every demo stock, evaluated once
        ex.get("/watchlist", "", method="PUT", body={"tickers": tickers})
        ex.get("/alerts/run", "", method="POST")
        ex.get("/alerts", "alerts/inbox.json")
        ex.get("/alerts/unread", "alerts/unread.json")

        for kind in KINDS:
            base = ex.get(f"/track-record?kind={kind}", f"track-record/{kind}/_all.json")
            for prof in base.get("profiles") or []:
                ex.get(f"/track-record?kind={kind}&profile={prof}", f"track-record/{kind}/{prof}.json")
        for t in tickers:
            ex.get(f"/track-record/{t}", f"track-record/ticker/{t}.json")

        # Every synthetic company (not the index and factor funds): the in-browser engine can analyze all of them,
        # so the site lists and pre-renders them; only `tickers` have saved responses.
        funds = set(BENCHMARKS) | set(FACTOR_FUNDS)
        companies = [s for s in get_data().symbols().value or [] if s.ticker not in funds]
        ex.write(
            "symbols.json",
            [{"ticker": s.ticker, "name": s.name, "exchange": s.exchange, "exported": s.ticker in tickers}
             for s in companies],
        )  # fmt: skip
        manifest = {
            "generated_at": clock.now().isoformat(),
            "as_of": health["today"],
            "engine_version": health["engine_version"],
            "config_hash": health["config_hash"],
            "synthetic": health["synthetic"],
            "tickers": tickers,
            "companies": [s.ticker for s in companies],
            "snapshot_tokens": [share["token"]],
        }
        ex.write("manifest.json", manifest)
    print(f"exported {ex.n} files, {ex.bytes / 1e6:.1f} MB, in {time.time() - t0:.0f}s")
    return manifest


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--tickers", help="comma-separated (default: the six synthetic headline tickers)")
    ap.add_argument(
        "--no-backtest", action="store_true", help="skip the backtest (the track record will be empty)"
    )
    a = ap.parse_args()
    logging.basicConfig(level=logging.WARNING)
    from engine.db.session import init_db

    init_db()
    tickers = [t.strip().upper() for t in a.tickers.split(",")] if a.tickers else DEMO_TICKERS
    export(a.out, tickers, backtest=not a.no_backtest)


if __name__ == "__main__":
    main()
