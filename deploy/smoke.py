"""Smoke test a running app container through its web server, as a visitor's browser would use it: health,
search, the stock page and every report section for the given tickers.

Usage: python3 deploy/smoke.py http://127.0.0.1:7860 AAPL JPM [--synthetic]
Prints each section's status and reason (no data values). Fails on a crash (HTTP 5xx) or a section in "error";
sections that are "missing" or "partial" because a source lacks data are reported, not failed.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request


def get(
    base: str, path: str, timeout: float = 930, body: dict | None = None
) -> tuple[int, object, float]:
    """GET, or POST a JSON body. Returns (status, parsed body, seconds)."""
    t0 = time.time()
    req = urllib.request.Request(base + path)
    if body is not None:
        req = urllib.request.Request(
            base + path,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            status = r.status
    except urllib.error.HTTPError as e:
        raw, status = e.read(), e.code
    try:
        parsed: object = json.loads(raw)
    except ValueError:
        parsed = raw[:200].decode("utf-8", "replace")
    return status, parsed, time.time() - t0


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    base, tickers = args[0].rstrip("/"), [t.upper() for t in args[1:]] or ["AAPL"]
    synthetic = "--synthetic" in sys.argv
    for _ in range(90):  # the engine and web server start together; give both time
        try:
            if get(base, "/api/engine/health", timeout=5)[0] == 200:
                break
        except OSError:
            pass
        time.sleep(2)
    status, health, _ = get(base, "/api/engine/health")
    if status != 200 or not isinstance(health, dict):
        print(f"FAIL health: HTTP {status} {health}")
        return 1
    print(
        f"health: mode={health['data_mode']} tier={health['data_tier']} synthetic={health['synthetic']}"
    )
    print(f"providers: {json.dumps(health['providers'])}")
    if health["synthetic"] != synthetic:
        print(f"FAIL expected {'synthetic' if synthetic else 'live'} data")
        return 1

    failures = 0
    status, found, secs = get(base, f"/api/engine/search?q={tickers[0].lower()}")
    results = found.get("results", []) if isinstance(found, dict) else []
    print(f"search {tickers[0]!r}: HTTP {status}, {len(results)} results ({secs:.1f}s)")
    failures += status != 200 or not results
    status, _, _ = get(base, "/")
    print(f"home page: HTTP {status}")
    failures += status != 200

    for t in tickers:
        status, _, _ = get(base, f"/stock/{t}")
        print(f"{t} page: HTTP {status}")
        failures += status != 200
        status, names, _ = get(base, f"/api/engine/report/{t}/sections")
        for name in names.get("sections", []) if isinstance(names, dict) else []:
            status, sec, secs = get(base, f"/api/engine/report/{t}/section/{name}")
            state = sec.get("status") if isinstance(sec, dict) else None
            reason = (sec.get("reason") or "") if isinstance(sec, dict) else str(sec)
            bad = status >= 500 or state == "error"
            failures += bad
            print(
                f"  {'FAIL' if bad else 'ok  '} {t} {name}: HTTP {status} {state} ({secs:.1f}s) {reason[:160]}"
            )
        status, dcf, secs = get(
            base, f"/api/engine/valuation/{t}/dcf", body={"wacc": 0.1}
        )
        ok = (
            status == 200 and isinstance(dcf, dict) and dcf.get("per_share") is not None
        )
        detail = "" if ok else (dcf.get("detail") if isinstance(dcf, dict) else dcf)
        print(
            f"  {'ok  ' if ok or status < 500 else 'FAIL'} {t} what-if DCF: HTTP {status} ({secs:.1f}s) {detail or ''}"
        )
        failures += status >= 500
    print(f"{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
