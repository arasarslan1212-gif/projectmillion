"""The static demo export: every file the web app's static mode asks for exists and is the live API response.

The expected paths mirror apps/web/lib/static.test.ts, which checks the web side of the same mapping.
"""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from engine.api.main import app
from engine.db import models as m
from engine.db.session import session_scope
from engine.report.builder import section_names
from engine.tools.export_static import RANGES, export, key

client = TestClient(app)


@pytest.fixture
def clean_alerts():
    def wipe():
        with session_scope() as s:
            for t in (m.AlertEvent, m.Alert, m.WatchlistItem):
                s.execute(delete(t))

    wipe()
    yield
    wipe()


def test_key_is_order_and_case_independent():
    assert key(["zzbnk", "ZZTEC"]) == key(("ZZTEC", "ZZBNK")) == "ZZBNK_ZZTEC"


def test_export_writes_every_file_the_web_maps(tmp_path, clean_alerts):
    manifest = export(tmp_path, ["ZZTEC", "ZZBNK"], backtest=False)
    assert manifest["tickers"] == ["ZZTEC", "ZZBNK"]
    assert manifest["synthetic"] is True
    (token,) = manifest["snapshot_tokens"]

    expected = [
        "health.json",
        "meta/definitions.json",
        "meta/methodology.json",
        "symbols.json",
        "manifest.json",
        f"snapshot/{token}.json",
        *(f"report/{t}/{s}.json" for t in ("ZZTEC", "ZZBNK") for s in section_names()),
        *(f"compare/ZZBNK_ZZTEC_{r}.json" for r in RANGES),
        "watchlist/ZZTEC.json",
        "watchlist/ZZBNK.json",
        "watchlist/ZZBNK_ZZTEC.json",
        "watchlist/_empty.json",
        "alerts/inbox.json",
        "alerts/unread.json",
        "track-record/backtest/_all.json",
        "track-record/live/_all.json",
        "track-record/all/_all.json",
        "track-record/ticker/ZZTEC.json",
    ]
    missing = [f for f in expected if not (tmp_path / f).is_file()]
    assert not missing

    # files are the live responses (apart from how long the request took)
    saved = json.loads((tmp_path / "report/ZZBNK/company.json").read_text())
    live = client.get("/api/report/ZZBNK/section/company").json()
    assert {**saved, "timing_ms": None} == {**live, "timing_ms": None}
    cmp = json.loads((tmp_path / "compare/ZZBNK_ZZTEC_1y.json").read_text())
    assert cmp["tickers"] == ["ZZTEC", "ZZBNK"]
    symbols = json.loads((tmp_path / "symbols.json").read_text())
    assert [s["ticker"] for s in symbols if s["exported"]] == ["ZZTEC", "ZZBNK"]
    assert len(symbols) == len(manifest["companies"]) > 50 and all(s["name"] for s in symbols)
    assert "ZQT01" in manifest["companies"] and "ZZMKT" not in manifest["companies"]  # peers yes, funds no
    snap = json.loads((tmp_path / f"snapshot/{token}.json").read_text())
    assert snap["ticker"] == "ZZTEC"
