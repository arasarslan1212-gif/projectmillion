"""The in-browser engine bridge (engine.browser), exercised under CPython with thread creation forbidden, as in
WebAssembly. It runs in a subprocess because the bridge patches thread pools process-wide."""

import json
import os
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


RECORD = textwrap.dedent(
    """
    import sys
    from pathlib import Path
    from engine.db.session import init_db
    from engine.http import client
    from engine.synthetic.server import synthetic_transport
    from engine.tools.export_static import export

    init_db()
    # "live" requests answered by the synthetic market, so the recording needs no network or keys
    client.reset_http(client.HttpClient(transport=synthetic_transport()))
    export(Path(sys.argv[1]), ["ZZTEC"], backtest=False)
    """
)

REPLAY = textwrap.dedent(
    """
    import asyncio, json, sys, threading
    from pathlib import Path

    threading.Thread.start = lambda self, *a, **k: (_ for _ in ()).throw(RuntimeError("no threads"))
    from engine import browser

    site = Path(sys.argv[2])
    fetched = []

    def fetch(path):  # stands in for the worker's download from the site
        fetched.append(path)
        p = site / path
        return p.read_bytes() if p.exists() else None

    browser.start(db_path=sys.argv[1], env={"FIXTURE_SET": "recorded", "DATA_TIER": "starter"}, fetch_fixture=fetch)

    async def main():
        out = {}
        for s in ["headline", "valuation", "trust", "chart"]:
            status, text = await browser.request("GET", f"/report/ZZTEC/section/{s}")
            out[s] = [status, json.loads(text)]
        status, text = await browser.request("POST", "/valuation/ZZTEC/dcf", json.dumps({"wacc": 0.1}))
        out["dcf"] = [status, json.loads(text)]
        status, _ = await browser.request("GET", "/report/ZZBNK/section/headline")  # never recorded
        out["unrecorded"] = [status, None]
        return out

    print(json.dumps({"calls": asyncio.run(main()), "fetched": len(fetched)}))
    """
)


def _strip(d):
    volatile = {"fetched_at", "timing_ms", "generated_at", "created_at", "computed_at", "report_id"}
    if isinstance(d, dict):
        return {k: _strip(v) for k, v in d.items() if k not in volatile}
    if isinstance(d, list):
        return [_strip(v) for v in d]
    return d


def test_recorded_data_replays_in_the_browser_engine(tmp_path):
    """Record provider responses, then replay them in the browser bridge, downloading each file on first use."""
    recorded, empty = tmp_path / "fixtures", tmp_path / "replay-fixtures"
    env = {
        **os.environ,
        "DATA_MODE": "record",
        "DATA_TIER": "starter",
        "FIXTURES_DIR": str(recorded),
        "RECORD_SET": "recorded",
        "AS_OF_OVERRIDE": "2026-09-25",
        "DATABASE_URL": f"sqlite:///{tmp_path / 'record.db'}",
        # the synthetic market ignores keys, but adapters refuse to run without them outside mock mode;
        # recordings never contain keys
        **{k: "test-key" for k in ("FMP_API_KEY", "FINNHUB_API_KEY", "FRED_API_KEY", "TIINGO_API_KEY")},
    }
    out = tmp_path / "data"
    rec = subprocess.run(
        [sys.executable, "-c", RECORD, str(out)], env=env, capture_output=True, text=True, timeout=600
    )
    assert rec.returncode == 0, rec.stderr[-3000:]
    meta = json.loads((recorded / "recorded" / "meta.json").read_text())
    assert meta["as_of"] == "2026-09-25" and meta["tickers"] == ["ZZTEC"]
    assert len(list((recorded / "recorded").rglob("*.json.gz"))) > 10

    # the replaying engine starts with only meta.json, as in the browser bundle
    (empty / "recorded").mkdir(parents=True)
    (empty / "recorded" / "meta.json").write_text(json.dumps(meta))
    env = {k: v for k, v in os.environ.items() if k not in ("AS_OF_OVERRIDE", "DATA_MODE")}
    env["FIXTURES_DIR"] = str(empty)
    res = subprocess.run(
        [sys.executable, "-c", REPLAY, str(tmp_path / "replay.db"), str(recorded)],
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert res.returncode == 0, res.stderr[-3000:]
    r = json.loads(res.stdout.strip().splitlines()[-1])
    assert r["fetched"] > 10  # downloaded on demand
    for s in ["headline", "valuation", "trust", "chart"]:
        status, live = r["calls"][s]
        assert status == 200, (s, live)
        saved = json.loads((out / "report" / "ZZTEC" / f"{s}.json").read_text())
        assert _strip(live) == _strip(saved), s
    assert r["calls"]["dcf"][0] == 200 and r["calls"]["dcf"][1]["per_share"] > 0
    assert r["calls"]["unrecorded"][0] in (200, 404)  # answered from what was recorded, never a crash
