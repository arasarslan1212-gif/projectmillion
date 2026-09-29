"""Compare mode, the watchlist (portfolio) summary and shareable snapshot links."""

import math
from datetime import timedelta

import numpy as np
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from engine.api.main import app
from engine.db import models as m
from engine.db.session import session_scope
from engine.report.builder import contexts, get_section
from engine.track import calibration
from engine.views.multi import COMPARE_METRICS, compare, portfolio

client = TestClient(app)


@pytest.fixture
def clean_snapshots():
    def wipe():
        with session_scope() as s:
            for t in (m.SnapshotOutcome, m.AppSnapshot, m.CalibrationChange):
                s.execute(delete(t))
        calibration._frames.clear()
        calibration._changes.clear()

    wipe()
    yield
    wipe()


def test_compare_reuses_report_numbers():
    c = compare(["ZZTEC", "zzbnk", "ZZSML", "NOPE"], "1y")
    assert c["tickers"] == ["ZZTEC", "ZZBNK", "ZZSML"]
    assert c["errors"] == [{"ticker": "NOPE", "error": "'NOPE' is not a US-listed ticker"}]
    first_ids = [x["id"] for x in c["rows"][0]["metrics"]]
    for row in c["rows"]:
        # the same metrics in the same order for every company, so the table lines up
        assert len(row["metrics"]) == len(COMPARE_METRICS) and [x["id"] for x in row["metrics"]] == first_ids
        comp = get_section(row["ticker"], "company")
        assert row["metrics"][0]["value"] == comp["stats"]["market_cap"]["value"]
        head = get_section(row["ticker"], "headline")
        assert row["trust"] == head["trust"] and row["target"] == head["target"]
    ch = c["chart"]
    assert 240 <= len(ch["dates"]) <= 260
    for t in c["tickers"]:
        assert ch["series"][t][0] == pytest.approx(100) and len(ch["series"][t]) == len(ch["dates"])
    assert ch["benchmark"]["values"][0] == pytest.approx(100)
    assert ch["dates"] == sorted(ch["dates"])
    five = compare(["ZZTEC", "ZZBNK"], "5y")["chart"]
    assert 240 <= len(five["dates"]) <= 270  # thinned to weekly


def test_compare_api_validation():
    assert client.get("/api/compare?tickers=A,B,C,D,E").status_code == 422
    assert client.get("/api/compare?tickers=ZZTEC,ZZBNK&range=10y").status_code == 422
    assert client.get("/api/compare?tickers=ZZTEC,ZZBNK").status_code == 200


def test_portfolio_aggregate_is_equal_weight():
    tickers = ["ZZTEC", "ZZBNK", "ZZREI", "ZZUTL"]
    p = portfolio(tickers)
    assert [h["ticker"] for h in p["holdings"]] == tickers
    a = p["aggregate"]
    trust = [get_section(t, "headline")["trust"]["score"] for t in tickers]
    assert a["trust_mean"] == pytest.approx(float(np.mean(trust)))
    assert a["trust_min"] == pytest.approx(min(trust))
    # portfolio volatility recomputed by hand from the same price window
    import pandas as pd

    px = (
        pd.DataFrame({t: contexts.get(t, None, False).prices["adj_close"] for t in tickers})
        .dropna()
        .iloc[-253:]
    )
    r = np.log(px).diff().dropna()
    port = r.mean(axis=1)  # equal weights on log returns approximates the same covariance quadratic form
    w = np.full(4, 0.25)
    expected = math.sqrt(w @ (r.cov().to_numpy() * 252) @ w)
    assert a["vol"] == pytest.approx(expected, rel=1e-9)
    assert a["vol"] == pytest.approx(float(port.std() * math.sqrt(252)), rel=1e-9)
    assert a["diversification_ratio"] >= 1.0
    assert -1 <= a["avg_correlation"] <= 1 and len(a["correlation"]["matrix"]) == 4
    assert sum(s["n"] for s in a["sectors"]) == 4
    assert portfolio([]) == {"holdings": [], "aggregate": None, "errors": []}


def test_share_freezes_the_report_and_later_shows_the_outcome(clean_snapshots):
    r1 = client.post("/api/report/ZZUTL/share").json()
    assert r1["created"] and len(r1["token"]) >= 12
    r2 = client.post("/api/report/ZZUTL/share").json()
    assert r2 == {**r1, "created": False}  # the same frozen link all day
    snap = client.get(f"/api/snapshot/{r1['token']}").json()
    assert snap["ticker"] == "ZZUTL" and snap["outcome"] is None
    secs = snap["report"]["sections"]
    assert {"company", "valuation", "explain", "trust"} <= set(secs)
    assert snap["target"]["p50"] == pytest.approx(secs["valuation"]["target"]["p50"])
    # the shared link is the graded snapshot: once graded, the outcome appears
    with session_scope() as s:
        row = s.scalars(select(m.AppSnapshot).where(m.AppSnapshot.share_token == r1["token"])).one()
        s.add(m.SnapshotOutcome(snapshot_id=row.id, horizon_date=row.as_of + timedelta(days=365), realized_price=70.0,
                                realized_return=0.1, in_band=True, abs_pct_err=0.1, realized_up=True, brier=0.1))  # fmt: skip
    graded = client.get(f"/api/snapshot/{r1['token']}").json()
    assert graded["outcome"]["in_band"] is True and graded["outcome"]["realized_price"] == 70.0
    assert client.get("/api/snapshot/nope").status_code == 404
    assert client.post("/api/report/NOPE/share").status_code == 404
