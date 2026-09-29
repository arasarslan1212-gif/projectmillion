"""The in-browser engine bridge (engine.browser), exercised under CPython with thread creation forbidden, as in
WebAssembly. It runs in a subprocess because the bridge patches thread pools process-wide."""

import json
import subprocess
import sys
import textwrap
from concurrent.futures import Future

from engine.browser import InlineExecutor

SCRIPT = textwrap.dedent(
    """
    import asyncio, json, sys, threading

    def no_threads(self, *a, **k):
        raise RuntimeError("can't start new thread")

    threading.Thread.start = no_threads  # WebAssembly Python cannot start threads

    from engine import browser

    info = browser.start(db_path=sys.argv[1])
    calls = [
        ("GET", "/health", None),
        ("GET", "/report/ZZTEC/section/headline", None),
        ("GET", "/report/ZZTEC/section/peers?peers=ZQT01,ZQT02", None),
        ("GET", "/compare?tickers=ZZTEC,ZQT01&range=1y", None),
        ("POST", "/valuation/ZZTEC/dcf", json.dumps({"wacc": 0.1})),
        ("POST", "/report/ZZTEC/refresh", None),
        ("PUT", "/watchlist", json.dumps({"tickers": ["ZZTEC"]})),
        ("POST", "/alerts/run", None),
        ("GET", "/alerts/unread", None),
        ("GET", "/report/NOPE/section/company", None),
        ("POST", "/valuation/ZZTEC/dcf", json.dumps({"wacc": 9})),
    ]

    async def main():
        out = []
        for method, path, body in calls:
            status, text = await browser.request(method, path, body)
            out.append([method, path, status, json.loads(text)])
        return out

    print(json.dumps({"info": info, "calls": asyncio.run(main())}))
    """
)


def test_inline_executor_behaves_like_a_pool():
    with InlineExecutor(max_workers=4) as ex:
        assert list(ex.map(lambda a, b: a + b, [1, 2], [10, 20])) == [11, 22]
        ok: Future = ex.submit(lambda: 42)
        bad: Future = ex.submit(lambda: 1 / 0)
    assert ok.result() == 42
    assert isinstance(bad.exception(), ZeroDivisionError)


def test_engine_runs_without_threads(tmp_path):
    proc = subprocess.run(
        [sys.executable, "-c", SCRIPT, str(tmp_path / "browser.db")],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    res = json.loads(proc.stdout.strip().splitlines()[-1])
    assert res["info"]["synthetic"] is True
    statuses = [s for _, _, s, _ in res["calls"]]
    assert statuses == [200] * 9 + [404, 422], res["calls"]  # errors map to the same statuses as over HTTP
    body = {f"{m} {p}": b for m, p, _, b in res["calls"][:9]}
    assert body["GET /report/ZZTEC/section/headline"]["target"]["p50"] > 0
    assert body["GET /compare?tickers=ZZTEC,ZQT01&range=1y"]["tickers"] == ["ZZTEC", "ZQT01"]
    assert body["POST /valuation/ZZTEC/dcf"]["per_share"] > 0
    assert body["GET /alerts/unread"]["unread"] >= 0
