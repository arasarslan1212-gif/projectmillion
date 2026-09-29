"""Check the engine's data sources against the live APIs, through the engine's own adapters.

Runs in CI (.github/workflows/data-probe.yml) with keys from repository secrets. It prints, per dataset, whether
the source answered and what came back (counts and date ranges), never the data itself or any key.

Usage (from services/engine, DATA_MODE=live):
    python -m engine.tools.probe_providers AAPL JPM
"""

from __future__ import annotations

import sys
import time
from datetime import date

from engine.data.service import get_data
from engine.db.session import init_db
from engine.providers.models import PriceHistory
from engine.providers.registry import get_providers
from engine.settings import get_settings


def summary(v) -> str:
    if v is None:
        return "nothing"
    if isinstance(v, PriceHistory):
        if not v.bars:
            return "0 bars"
        return f"{len(v.bars)} bars {v.bars[0].date}..{v.bars[-1].date} from {v.source}"
    if isinstance(v, list):
        return f"{len(v)} items"
    if isinstance(v, dict):
        return f"{len(v)} keys"
    return type(v).__name__


def main() -> int:
    tickers = [t.upper() for t in sys.argv[1:]] or ["AAPL"]
    s = get_settings()
    init_db()
    print(f"data_mode={s.data_mode} tier={s.data_tier} price_source={s.price_source}")
    print(
        "keys set:",
        {
            k: bool(getattr(s, k))
            for k in ("finnhub_api_key", "fred_api_key", "tiingo_api_key", "fmp_api_key")
        },
    )
    print("providers:", get_providers().describe())
    d = get_data()
    failures = 0

    def check(name: str, fn) -> object:
        nonlocal failures
        t0 = time.time()
        try:
            f = fn()
        except Exception as e:  # report every failure; the probe's job is to find them all
            failures += 1
            print(f"  ERROR   {name}: {type(e).__name__}: {str(e)[:300]}")
            return None
        status = getattr(f, "status", "ok")
        reason = getattr(f, "reason", None)
        value = getattr(f, "value", f)
        mark = "ok     " if status == "ok" and value not in (None, [], {}) else status.upper().ljust(7)
        print(
            f"  {mark} {name}: {summary(value)}{f' ({reason})' if reason else ''} [{time.time() - t0:.1f}s]"
        )
        return value

    syms = check("symbols (SEC ticker list)", d.symbols)
    print(f"  ... {len(syms or [])} US-listed symbols")
    for t in tickers:
        print(f"{t}:")
        info = d.resolve(t)
        if info is None:
            print("  not found in the SEC ticker list")
            failures += 1
            continue
        subs = check("submissions (SEC)", lambda i=info: d.submissions(i.cik))
        check("company facts (SEC XBRL)", lambda i=info: d.facts(i.cik))
        check("prices 10y", lambda t=t: d.prices(t, 3650))
        check("prices 1y", lambda t=t: d.prices(t, 365))
        check("quote", lambda t=t: d.quote(t))
        check("profile", lambda t=t: d.profile(t))
        check("estimates", lambda t=t: d.estimates(t))
        check("earnings", lambda t=t: d.earnings(t))
        check("earnings calendar", lambda t=t: d.earnings_calendar(t))
        check("analyst actions", lambda t=t: d.analyst_actions(t))
        check("recommendation trends", lambda t=t: d.recommendation_trends(t))
        check("news", lambda t=t: d.news(t))
        check("insiders (SEC Form 4)", lambda t=t, i=info: d.insiders(t, i.cik))
        check("institutional holders", lambda t=t: d.institutions(t))
        check("short interest (FINRA)", lambda t=t: d.short_interest(t))
        if subs:
            print(f"  ... submissions keys: {sorted(subs)[:8]}")
    print("macro:")
    for sid in ("DGS10", "BAA10Y", "CPIAUCSL"):
        check(f"FRED {sid}", lambda sid=sid: d.macro(sid))
    print(f"probe finished {date.today()}: {failures} errors")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
