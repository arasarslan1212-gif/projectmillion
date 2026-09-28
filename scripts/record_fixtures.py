"""Record real provider responses for the mock-mode fixture set.

Usage (needs network access to the providers and API keys for the chosen tier):
    DATA_MODE=record DATA_TIER=starter python scripts/record_fixtures.py AAPL JPM O RIVN NEE <small-cap>

Every HTTP response the report makes is saved (secrets stripped) under fixtures/recorded/, and
fixtures/recorded/meta.json pins "today" so mock mode replays exactly the same requests.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "engine"))

# mega-cap tech, bank, REIT, unprofitable growth, high-dividend utility, sparse small cap (pick one that is still listed)
DEFAULT = ["AAPL", "JPM", "O", "RIVN", "DUK", "ASTC"]


def main(tickers: list[str]) -> None:
    from engine import clock
    from engine.db.session import init_db
    from engine.report import builder
    from engine.settings import get_settings

    s = get_settings()
    if s.data_mode != "record":
        sys.exit("Set DATA_MODE=record to record fixtures.")
    init_db()
    out = s.fixtures_dir / s.record_set
    out.mkdir(parents=True, exist_ok=True)
    today = clock.today()
    for t in tickers:
        print(f"recording {t} ...", flush=True)
        report = builder.build_report(t)
        bad = {k: v.get("reason") for k, v in report["sections"].items() if v.get("status") != "ok"}
        if bad:
            print(f"  sections with gaps: {json.dumps(bad)[:500]}")
    (out / "meta.json").write_text(json.dumps({"as_of": today.isoformat(), "tickers": tickers, "tier": s.data_tier}, indent=2))
    print(f"done: fixtures in {out} (as_of {today})")


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULT)
