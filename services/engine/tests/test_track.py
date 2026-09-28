"""Track record: snapshots, outcome grading, statistics, point-in-time backtest, recalibration and methodology."""

import math
import uuid
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from engine import clock
from engine.config import get_config
from engine.db import models as m
from engine.db.session import session_scope
from engine.report.builder import contexts, get_section
from engine.track import backtest, calibration, metrics, scoring, snapshots
from engine.track.metrics import Z80


@pytest.fixture
def clean_track():
    def wipe():
        with session_scope() as s:
            for t in (m.SnapshotOutcome, m.AppSnapshot, m.CalibrationChange):
                s.execute(delete(t))
        calibration._frames.clear()
        calibration._changes.clear()
        contexts.d.clear()

    wipe()
    yield
    wipe()


def _count(model, *where) -> int:
    with session_scope() as s:
        return int(s.scalar(select(func.count()).select_from(model).where(*where)) or 0)


# ---- grading ----------------------------------------------------------------------------------------------------


def test_grade_and_realized_return():
    g = scoring.grade(100, 80, 110, 140, 0.7, 0.25)
    assert g["realized_price"] == pytest.approx(125) and g["in_band"] and g["realized_up"]
    assert g["abs_pct_err"] == pytest.approx(125 / 110 - 1)
    assert g["brier"] == pytest.approx(0.09)
    idx = pd.bdate_range("2024-01-01", "2025-01-10")
    closes = pd.Series(np.linspace(10, 20, len(idx)), index=idx)
    r = scoring.realized_return(
        closes, date(2024, 1, 6), date(2025, 1, 5)
    )  # weekend dates use the prior close
    assert r == pytest.approx(closes[:"2025-01-03"].iloc[-1] / closes[:"2024-01-05"].iloc[-1] - 1)
    stale = closes[:"2024-06-28"]
    assert (
        scoring.realized_return(stale, date(2024, 1, 5), date(2025, 1, 5)) is None
    )  # no price near the horizon


# ---- statistics ---------------------------------------------------------------------------------------------------


def _simulated(n=4000, sigma_true=0.3, sigma_model=0.3, seed=1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    price = np.full(n, 100.0)
    mu = rng.normal(0.05, 0.1, n)
    p50 = price * np.exp(mu)
    realized = p50 * np.exp(sigma_true * rng.standard_normal(n))
    prob_up = 1 - np.array([math.erfc(x / math.sqrt(2)) / 2 for x in mu / sigma_model])
    df = pd.DataFrame({
        "ticker": [f"T{i % 40}" for i in range(n)],
        "as_of": [date(2020, 1, 31) + timedelta(days=30 * (i % 48)) for i in range(n)],
        "price": price, "p50": p50, "p10": p50 * np.exp(-Z80 * sigma_model), "p90": p50 * np.exp(Z80 * sigma_model),
        "prob_up": prob_up, "prob_up_raw": prob_up, "sigma_total_raw": sigma_model, "realized_price": realized,
        "realized_return": realized / price - 1, "trust_rating": rng.uniform(20, 90, n), "profile": "general",
        "vol_bucket": "mid", "size_bucket": "large", "is_backtest": True, "methods": [[] for _ in range(n)],
    })  # fmt: skip
    df["in_band"] = (df["realized_price"] >= df["p10"]) & (df["realized_price"] <= df["p90"])
    df["realized_up"] = df["realized_price"] > df["price"]
    df["abs_pct_err"] = (df["realized_price"] / df["p50"] - 1).abs()
    df["brier"] = (df["prob_up"] - df["realized_up"].astype(float)) ** 2
    return df


def test_statistics_on_a_calibrated_forecast():
    df = _simulated()
    s = metrics.summary(df)
    assert s["coverage"] == pytest.approx(0.8, abs=0.03)
    lo, hi = s["coverage_ci"]
    assert lo < s["coverage"] < hi and hi - lo < 0.04
    assert s["brier_skill"] > 0  # the forecast knows the drift, so it beats the base rate
    for row in metrics.interval_coverage(df, [0.2, 0.5, 0.8]):
        assert row["actual"] == pytest.approx(row["nominal"], abs=0.03)
    assert all(abs(b["share"] - 0.1) < 0.03 for b in metrics.pit_histogram(df))
    rel = metrics.reliability(df, 10)
    assert all(abs(b["forecast"] - b["observed"]) < 0.08 for b in rel if b["n"] > 200)
    tb = metrics.trust_buckets(df, 5)
    assert [b["bucket"] for b in tb["buckets"]] == [1, 2, 3, 4, 5]
    assert tb["buckets"][0]["trust_hi"] <= tb["buckets"][1]["trust_lo"] + 1e-9


def test_wilson_interval():
    assert metrics.wilson(0, 0) is None
    lo, hi = metrics.wilson(8, 10)
    assert 0.44 < lo < 0.5 and 0.94 < hi < 0.98


# ---- recalibration --------------------------------------------------------------------------------------------------


def test_fit_widens_overconfident_ranges():
    cfg = get_config()
    df = _simulated(sigma_true=0.3, sigma_model=0.18)
    res = calibration.fit(df, cfg)
    assert res["sigma_scale"] == pytest.approx(0.3 / 0.18, rel=0.08)
    assert res["apply_scale"]
    assert res["metrics"]["coverage_scaled_out_of_fold"] == pytest.approx(0.8, abs=0.03)
    ys = res["prob_map"]["y"]
    assert all(b >= a for a, b in zip(ys, ys[1:], strict=False)) and min(ys) >= 0.02 and max(ys) <= 0.98
    small = calibration.fit(df.head(20), cfg)
    assert not small["apply_scale"] and not small["apply_map"] and "needed" in small["reason"]


def test_fit_leaves_a_calibrated_model_alone():
    res = calibration.fit(_simulated(), get_config())
    assert not res["apply_scale"] and not res["apply_map"]


def test_applied_recalibration_reaches_valuation_point_in_time(clean_track):
    base = get_section("ZZTEC", "valuation")
    fitted = clock.today() - timedelta(days=10)
    with session_scope() as s:
        s.add(m.CalibrationChange(
            id=str(uuid.uuid4()), fitted_on=fitted, data_cutoff=fitted, is_synthetic=True, n=500, sigma_scale=1.5,
            prob_map_json={"x": [0.0, 1.0], "y": [0.3, 0.7]}, metrics_json={}, applied=True, reason="test",
            engine_version="t", config_hash="t",
        ))  # fmt: skip
    contexts.d.clear()
    v = get_section("ZZTEC", "valuation")
    assert v["sigma"]["total"] == pytest.approx(v["sigma"]["total_raw"] * 1.5)
    assert v["target"]["calibration"]["sigma_scale"] == 1.5
    assert v["target"]["prob_up"] == pytest.approx(0.3 + 0.4 * v["target"]["prob_up_raw"])
    assert v["target"]["p50"] == pytest.approx(base["target"]["p50"], rel=1e-6)  # the median is never moved
    # a report dated before the fit does not see it
    old = get_section("ZZTEC", "valuation", as_of=fitted - timedelta(days=30), pit=True)
    assert old["target"]["calibration"] is None and old["sigma"]["calibration_scale"] == 1.0


# ---- snapshots and the backtest -------------------------------------------------------------------------------------


def test_live_snapshot_once_per_day(clean_track):
    ctx = contexts.get("ZZUTL", None, False)
    assert snapshots.record_live(ctx) == "new"
    assert snapshots.record_live(ctx) is not None
    assert _count(m.AppSnapshot, m.AppSnapshot.ticker == "ZZUTL") == 1
    pit = contexts.get("ZZUTL", date(2025, 6, 30), True)
    assert snapshots.record_live(pit) is None  # point-in-time views are never snapshotted
    with session_scope() as s:
        row = s.scalars(select(m.AppSnapshot)).one()
        v = get_section("ZZUTL", "valuation")
        assert row.p50 == pytest.approx(v["target"]["p50"]) and not row.is_backtest and row.is_synthetic
        assert {x["id"] for x in row.report_json["methods"]} == {b["id"] for b in v["blend"]}


def test_backtest_is_point_in_time_raw_and_idempotent(clean_track):
    dates = backtest.walk_dates(date(2023, 3, 31), date(2024, 3, 31), 6)
    assert dates == [date(2023, 3, 31), date(2023, 9, 29), date(2024, 3, 29)]
    res = backtest.run(["ZZTEC", "ZZBNK"], date(2023, 3, 31), 6, end=date(2024, 3, 31))
    assert res["stored"] == 6 and res["failed"] == 0 and res["scored"] == 6
    df = scoring.outcomes_frame(synthetic=True, backtest=True)
    assert len(df) == 6
    for _, r in df.iterrows():
        ctx = contexts.get(r["ticker"], r["as_of"], True)
        assert r["price"] == pytest.approx(ctx.last_price)  # the price the report saw that day
        assert ctx.last_price_date <= r["as_of"]
        assert r["horizon_date"] == r["as_of"] + timedelta(days=365)
    with calibration.raw_model():
        v = get_section("ZZTEC", "valuation", as_of=date(2023, 3, 31), pit=True)
    assert "backtest run" in v["accuracy_source"]
    backtest.run(["ZZTEC", "ZZBNK"], date(2023, 3, 31), 6, end=date(2024, 3, 31))
    assert (
        _count(m.AppSnapshot, m.AppSnapshot.is_backtest.is_(True)) == 6
    )  # re-running replaces, never duplicates


def test_track_record_api(clean_track):
    from engine.api.main import app

    backtest.run(["ZZTEC", "ZZUTL"], date(2022, 3, 31), 6, end=date(2024, 3, 31))
    c = TestClient(app)
    r = c.get("/api/track-record?kind=backtest").json()
    assert r["results"]["summary"]["n"] == 10 and r["counts"]["backtest"]["scored"] == 10
    assert any("Survivorship" in x for x in r["caveats"]) and any("Synthetic" in x for x in r["caveats"])
    assert r["results"]["interval_coverage"][-2]["nominal"] == 0.8
    live = c.get("/api/track-record?kind=live").json()
    assert live["results"]["summary"]["n"] == 0
    t = c.get("/api/track-record/ZZTEC").json()
    assert len(t["snapshots"]) == 5 and all(x["outcome"] for x in t["snapshots"])
    assert c.get("/api/track-record?kind=nope").status_code == 422


# ---- methodology --------------------------------------------------------------------------------------------------


def test_methodology_is_generated_from_config():
    from engine.meta.methodology import build, comment_map

    doc = build()
    cfg = get_config()
    assert doc["config_hash"] == cfg.hash
    ids = [s["id"] for s in doc["sections"]]
    assert {"trust_rating", "valuation", "confidence", "track", "analysts"} <= set(ids)

    def find(nodes, path):
        for n in nodes:
            if n["path"] == path:
                return n
            if "children" in n and path.startswith(n["path"] + "."):
                return find(n["children"], path)

    val = next(s for s in doc["sections"] if s["id"] == "valuation")
    n = find(val["params"], "valuation.convergence_12m")
    assert n["value"] == cfg["valuation"]["convergence_12m"] and "log-gap" in n["comment"]
    erp = find(val["params"], "valuation.wacc.equity_risk_premium")
    assert erp["value"] == cfg["valuation"]["wacc"]["equity_risk_premium"] and "4–6%" in erp["comment"]
    cm = comment_map("a:\n  # above b\n  b: 1  # inline\n  c: '#not a comment'\n")
    assert cm == {"a.b": "above b inline"}
    assert len(doc["glossary"]) > 50 and "not investment advice" in doc["disclaimer"].lower()


def test_point_in_time_peers_see_prices_from_their_date():
    """Regression: peer prices for an old report date used to come from a window ending today (so none)."""
    as_of = date(2022, 6, 30)
    p = get_section("ZZTEC", "peers", as_of=as_of, pit=True)
    peers = [r for r in p["rows"] if not r["is_subject"]]
    assert sum(1 for r in peers if r["metrics"]["market_cap"]) >= 3
    assert p["medians"]["pe"] is not None
    v = get_section("ZZTEC", "valuation", as_of=as_of, pit=True)
    rel = next(x for x in v["methods"] if x["id"] == "relative_peers")
    assert rel["value"] is not None
