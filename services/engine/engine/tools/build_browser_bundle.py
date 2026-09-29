"""Build the files the in-browser engine loads on the static site (see engine/browser.py).

Output, served next to the site under /engine/:
- engine.zip: the engine package and config, in the repository layout (settings resolve paths from it);
- seed.db.gz: the database after the export (track record, calibration, analyst history, alerts), without the
  tables that are only caches of provider data, which the engine refills on demand;
- wheels/: pure-Python packages the engine needs that Pyodide doesn't ship, pinned to uv.lock;
- bundle.json: what to load, including the Pyodide release and packages (served from Pyodide's CDN);
- with --fixtures (real data): fixtures/<set>/..., the recorded provider responses, which the engine downloads one
  file at a time as requests need them, and the settings that replay them.

Usage (from services/engine):
    python -m engine.tools.build_browser_bundle --db demo.db --out ../../apps/web/public/engine
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import tomllib
import urllib.request
import zipfile
from pathlib import Path

from engine.settings import REPO_ROOT

PYODIDE_VERSION = "314.0.7"  # Python 3.14; its numpy/pandas/scipy are the closest to uv.lock's
PYODIDE_INDEX = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/"
# Loaded from Pyodide's distribution; their dependencies (starlette, anyio, pydantic_core, ...) come along.
PYODIDE_PACKAGES = ["numpy", "pandas", "scipy", "pydantic", "fastapi", "httpx", "sqlalchemy", "pyyaml"]
# Runtime dependencies Pyodide doesn't ship (all pure Python), at the versions uv.lock pins.
EXTRA_WHEELS = ["pydantic-settings", "python-dotenv"]
# Caches of provider data: large, and rebuilt on demand from the synthetic provider.
CACHE_TABLES = ["provider_cache", "prices", "fundamentals"]
ENGINE_DIR = REPO_ROOT / "services" / "engine"


def locked_versions() -> dict[str, str]:
    lock = tomllib.loads((ENGINE_DIR / "uv.lock").read_text())
    return {p["name"]: p["version"] for p in lock["package"]}


def fetch_wheel(name: str, version: str, out_dir: Path, cache: Path | None) -> str:
    """Download the pure-Python wheel from PyPI, checking its SHA-256."""
    meta = json.load(urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json", timeout=60))
    wheels = [f for f in meta["urls"] if f["filename"].endswith("-none-any.whl")]
    if not wheels:
        raise RuntimeError(f"{name} {version} has no pure-Python wheel")
    f = wheels[0]
    src = cache / f["filename"] if cache else None
    if src and src.exists():
        data = src.read_bytes()
    else:
        data = urllib.request.urlopen(f["url"], timeout=120).read()
        if src:
            src.parent.mkdir(parents=True, exist_ok=True)
            src.write_bytes(data)
    if hashlib.sha256(data).hexdigest() != f["digests"]["sha256"]:
        raise RuntimeError(f"checksum mismatch for {f['filename']}")
    (out_dir / f["filename"]).write_bytes(data)
    return f["filename"]


def build_engine_zip(path: Path, fixture_meta: Path | None = None) -> int:
    files = [
        *sorted(
            p for p in (ENGINE_DIR / "engine").rglob("*.py") if "tools" not in p.relative_to(ENGINE_DIR).parts
        ),
        *sorted((REPO_ROOT / "config").glob("*.yaml")),
    ]
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in files:
            z.write(f, f.relative_to(REPO_ROOT).as_posix())
        z.writestr("fixtures/synthetic/", "")
        if fixture_meta:  # pins the recording's "today" (engine.clock)
            z.write(fixture_meta, f"fixtures/{fixture_meta.parent.name}/meta.json")
    return len(files)


KEY_VARS = (
    "FINNHUB_API_KEY",
    "FMP_API_KEY",
    "TIINGO_API_KEY",
    "FRED_API_KEY",
    "MASSIVE_API_KEY",
    "ANTHROPIC_API_KEY",
)


def copy_fixtures(src: Path, out: Path) -> dict:
    """Publish a recorded set for on-demand download (the index is only needed when recording).

    Recordings never store keys (the HTTP client strips them), and this checks it: any file containing the value
    of a key in the environment stops the build, since everything here becomes public."""
    files = [p for p in src.rglob("*.json.gz") if p.is_file()]
    secrets = [v for k in KEY_VARS if len(v := os.environ.get(k, "")) >= 8]
    for p in files:
        text = gzip.decompress(p.read_bytes()).decode("utf-8", "replace")
        if any(v in text for v in secrets):
            raise RuntimeError(f"{p.relative_to(src)} contains an API key; refusing to publish it")
        dest = out / "fixtures" / src.name / p.relative_to(src)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dest)
    return {"files": len(files), "bytes": sum(p.stat().st_size for p in files)}


def build_seed_db(src: Path | None, out: Path) -> dict:
    """Copy the database without the provider caches, compacted and gzipped."""
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "seed.db"
        if src:
            shutil.copyfile(src, db)
        else:  # no export database: an empty schema
            from sqlalchemy import create_engine

            from engine.db.models import Base

            Base.metadata.create_all(create_engine(f"sqlite:///{db}"))
        con = sqlite3.connect(db)
        con.execute("PRAGMA journal_mode=DELETE")
        tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}
        for t in CACHE_TABLES:
            if t in tables:
                con.execute(f"delete from {t}")  # noqa: S608 (fixed table names)
        con.commit()
        con.execute("VACUUM")
        counts = {
            t: con.execute(f"select count(*) from {t}").fetchone()[0]  # noqa: S608
            for t in ("app_snapshots", "snapshot_outcomes", "calibration_changes", "analyst_actions")
            if t in tables
        }
        con.close()
        raw = db.read_bytes()
    with gzip.GzipFile(out, "wb", compresslevel=9, mtime=0) as gz:
        gz.write(raw)
    return {"rows": counts, "bytes": len(raw)}


def build(out: Path, db: Path | None, wheel_cache: Path | None = None, fixtures: Path | None = None) -> dict:
    from engine.api.main import health

    if out.exists():
        shutil.rmtree(out)
    (out / "wheels").mkdir(parents=True)
    pins = locked_versions()
    wheels = [fetch_wheel(n, pins[n], out / "wheels", wheel_cache) for n in EXTRA_WHEELS]
    env, rec = {}, None
    if fixtures:
        meta = json.loads((fixtures / "meta.json").read_text())
        env = {
            "FIXTURE_SET": fixtures.name,
            "DATA_TIER": meta["tier"],
            "PRICE_SOURCE": meta.get("price_source", "auto"),
        }
        rec = copy_fixtures(fixtures, out)
    n_files = build_engine_zip(out / "engine.zip", fixtures / "meta.json" if fixtures else None)
    seed = build_seed_db(db, out / "seed.db.gz")
    h = health()
    bundle = {
        "engine_version": h["engine_version"],
        "config_hash": h["config_hash"],
        "as_of": h["today"],
        "pyodide": {"version": PYODIDE_VERSION, "index_url": PYODIDE_INDEX, "packages": PYODIDE_PACKAGES},
        "wheels": wheels,
        "engine": "engine.zip",
        "seed_db": "seed.db.gz",
        "seed": seed["rows"],
        "env": env,
        "fixtures": "fixtures/" if fixtures else None,
        "recorded": rec,
        "sizes": {p.name: p.stat().st_size for p in sorted(out.iterdir()) if p.is_file()},
    }
    (out / "bundle.json").write_text(json.dumps(bundle, indent=1))
    if rec:
        print(f"recorded responses: {rec['files']} files, {rec['bytes'] / 1e6:.1f} MB (downloaded on demand)")
    print(
        f"engine.zip: {n_files} files, {bundle['sizes']['engine.zip'] / 1e6:.1f} MB; seed database "
        f"{seed['bytes'] / 1e6:.1f} MB ({bundle['sizes']['seed.db.gz'] / 1e6:.1f} MB gzipped); wheels: {wheels}"
    )
    return bundle


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--db", type=Path, help="database to seed from (the static export's); default: empty")
    ap.add_argument("--wheel-cache", type=Path, help="keep downloaded wheels here between builds")
    ap.add_argument(
        "--fixtures", type=Path, help="a recorded fixture set (with meta.json) to replay; default: synthetic"
    )
    a = ap.parse_args()
    build(a.out, a.db, a.wheel_cache, a.fixtures)


if __name__ == "__main__":
    main()
