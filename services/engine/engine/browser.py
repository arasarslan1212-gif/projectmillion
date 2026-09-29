"""Run the engine inside a web browser: Pyodide, which is CPython compiled to WebAssembly.

The GitHub Pages site has no server. Its web worker loads Pyodide, unpacks the bundle built by
engine.tools.build_browser_bundle, calls `start()` once, and then `request()` for each API call the saved
files can't answer. The engine code runs unchanged, in synthetic mock mode. This module only adapts the
runtime:

- WebAssembly Python has no threads, so thread pools run their work inline. The results are the same, computed
  one after another.
- Requests go through the FastAPI app in-process, via httpx's ASGI transport, exactly as they would over HTTP.
- The database is an SQLite file in the browser's memory, seeded with the build's track record and calibration.
- On the real-data site, provider responses are replayed from the build's recording (mock mode, recorded set);
  each recorded file is downloaded from the site the first time a request needs it.
"""

from __future__ import annotations

import concurrent.futures
import gzip
import json
import logging
import os
import time
import traceback
from concurrent.futures import Future
from pathlib import Path

log = logging.getLogger("engine.browser")

DB_PATH = "/home/pyodide/engine.db"
_client = None


class InlineExecutor:
    """A ThreadPoolExecutor stand-in that runs each task immediately, in the calling thread."""

    def __init__(self, max_workers: int | None = None, *args, **kwargs) -> None:
        pass

    def submit(self, fn, /, *args, **kwargs) -> Future:
        f: Future = Future()
        try:
            f.set_result(fn(*args, **kwargs))
        except BaseException as e:  # delivered through the future, as a thread pool would
            f.set_exception(e)
        return f

    def map(self, fn, *iterables, timeout=None, chunksize=1):
        return iter([fn(*args) for args in zip(*iterables, strict=False)])

    def shutdown(self, wait: bool = True, *, cancel_futures: bool = False) -> None:
        pass

    def __enter__(self) -> InlineExecutor:
        return self

    def __exit__(self, *exc) -> None:
        self.shutdown()


async def _run_sync_inline(func, *args, abandon_on_cancel=False, cancellable=None, limiter=None):
    """anyio.to_thread.run_sync without a thread: FastAPI and Starlette run sync endpoints and background tasks
    through it."""
    return func(*args)


def patch_runtime() -> None:
    """Replace thread-based concurrency with inline execution. Must run before the engine is imported."""
    import anyio.to_thread

    concurrent.futures.ThreadPoolExecutor = InlineExecutor  # type: ignore[misc]
    anyio.to_thread.run_sync = _run_sync_inline  # type: ignore[assignment]


def _py(v):
    """A value from JavaScript (Pyodide JsProxy) as a Python object; Python values pass through."""
    return v.to_py() if hasattr(v, "to_py") else v


def configure(db_path: str = DB_PATH, env: dict | None = None) -> None:
    """The browser engine is always offline: mock mode (synthetic, or a replayed recording), no keys, no network,
    no scheduler. `env` comes from the bundle and may choose the recorded set and its price source."""
    os.environ.update(
        {
            "DATA_MODE": "mock",
            "FIXTURE_SET": "synthetic",
            **{str(k): str(v) for k, v in (env or {}).items()},
            "DATABASE_URL": f"sqlite:///{db_path}",
            "SQLITE_WAL": "false",
            "ENABLE_SCHEDULER": "false",
            "ANTHROPIC_API_KEY": "",
        }
    )


def _gzipped(data: bytes) -> bytes:
    """Some hosts serve .gz files with Content-Encoding: gzip, so the browser hands them over decompressed; store
    them compressed either way."""
    return data if data[:2] == b"\x1f\x8b" else gzip.compress(data, mtime=0)


def use_fixture_fetcher(fetch) -> None:
    """Download recorded provider responses on demand: `fetch(path)` returns the file's bytes or None."""
    from engine.http.client import FixtureStore

    def fetcher(path: str) -> bytes | None:
        data = _py(fetch(path))
        return _gzipped(bytes(data)) if data is not None else None

    FixtureStore.fetcher = fetcher


def start(seed_db_gz: str | None = None, db_path: str = DB_PATH, env=None, fetch_fixture=None) -> dict:
    """Configure the engine, restore the seed database and import the API. Returns the engine's /health."""
    global _client
    t0 = time.perf_counter()
    configure(db_path, _py(env))
    if fetch_fixture is not None:
        use_fixture_fetcher(fetch_fixture)
    if seed_db_gz and Path(seed_db_gz).exists() and not Path(db_path).exists():
        raw = Path(seed_db_gz).read_bytes()
        Path(db_path).write_bytes(gzip.decompress(raw) if raw[:2] == b"\x1f\x8b" else raw)
    patch_runtime()
    logging.getLogger("httpx").setLevel(logging.WARNING)  # one line per in-process request is noise

    import httpx

    from engine.api.main import app
    from engine.db.session import init_db

    init_db()  # creates any table the seed database lacks
    transport = httpx.ASGITransport(app=app)  # the lifespan (init_db, scheduler) is handled above instead
    _client = httpx.AsyncClient(transport=transport, base_url="http://engine", trust_env=False, timeout=None)

    from engine.api.main import health

    info = health()
    info["startup_seconds"] = round(time.perf_counter() - t0, 2)
    return info


async def request(method: str, path: str, body: str | None = None) -> list:
    """Call the API in-process. `path` is as the web app writes it, without the /api prefix.

    Returns [status, response text]; engine crashes come back as a 500 with the error message.
    """
    if _client is None:
        raise RuntimeError("engine not started")
    t0 = time.perf_counter()
    try:
        r = await _client.request(
            method.upper(),
            "/api" + path,
            content=body.encode() if body else None,
            headers={"content-type": "application/json"} if body else None,
        )
        status, text = r.status_code, r.text
    except Exception as e:
        traceback.print_exc()
        status, text = 500, json.dumps({"detail": f"The engine failed: {type(e).__name__}: {e}"})
    log.info("%s %s -> %s in %.2fs", method, path, status, time.perf_counter() - t0)
    return [status, text]
