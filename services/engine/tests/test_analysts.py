"""Analyst calls, Trust Scores, consensus and the analysts section."""

from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest
from scipy.stats import spearmanr

from engine.analysts.calls import Call, build_calls, normalize_action, split_factor_after
from engine.analysts.consensus import consensus
from engine.analysts.scoring import (
    PriceBook,
    composite,
    herding,
    raw_metrics,
    score_calls,
    shrink,
    trust_scores,
)
from engine.config import get_config
from engine.report.builder import contexts, get_section

ACFG = get_config().data["analysts"]


def _rec(ticker, d, firm, target=None, rating=None, analyst=None, action=None):
    return {
        "ticker": ticker,
        "date": d,
        "firm": firm,
        "analyst_key": f"name:{analyst.lower()}|{firm.lower()}" if analyst else None,
        "analyst_name": analyst,
        "target": target,
        "target_prior": None,
        "rating": rating,
        "rating_prior": None,
        "action": action,
        "url": None,
        "headline": None,
        "source": "test",
    }


# ---- building calls -------------------------------------------------------------------------------


def test_targets_join_grades_within_window_and_are_split_adjusted():
    recs = [
        _rec("X", date(2020, 1, 2), "Firm A", target=400.0, analyst="Ann"),
        _rec(
            "X", date(2020, 1, 3), "Firm A.", rating="Overweight", action="upgrade"
        ),  # firm name punctuation differs
        _rec("X", date(2020, 12, 1), "Firm A", target=120.0, analyst="Ann"),
        _rec(
            "X", date(2021, 6, 1), "Firm B", rating="Sell", action="init"
        ),  # grade with no target: firm-level call
    ]
    calls = build_calls(recs, {"X": [(date(2020, 8, 31), 4.0)]})
    ann = [c for c in calls if c.analyst_name == "Ann"]
    assert (
        ann[0].target == pytest.approx(100.0) and ann[0].target_raw == 400.0
    )  # pre-split target in today's units
    assert ann[0].rating == "Overweight" and ann[0].rating_norm == 1 and ann[0].action == "upgrade"
    assert ann[1].target == pytest.approx(120.0)
    assert ann[1].rating == "Overweight" and ann[1].rating_source == "carried"  # rating stays until changed
    assert ann[1].target_prior == pytest.approx(100.0) and ann[1].target_change == pytest.approx(0.2)
    assert ann[1].action == "reiteration"
    firm_b = [c for c in calls if c.firm == "Firm B"]
    assert len(firm_b) == 1 and firm_b[0].analyst_key is None and firm_b[0].rating_norm == -1
    assert firm_b[0].action == "initiation"


def test_grade_outside_window_is_not_joined():
    recs = [
        _rec("X", date(2022, 1, 3), "Firm A", target=50.0, analyst="Ann"),
        _rec("X", date(2022, 1, 20), "Firm A", rating="Buy", action="upgrade"),
    ]
    calls = build_calls(recs, {})
    ann = next(c for c in calls if c.analyst_name)
    assert ann.rating is None and ann.action == "initiation"
    assert sum(1 for c in calls if c.analyst_key is None) == 1


def test_dropped_coverage_leaves_the_consensus():
    from engine.analysts.service import active_targets

    d = date(2026, 1, 5)
    calls = [
        Call("X", d, "F", "a", "A", 100.0, 100.0, "Buy", 1, "reported", "initiation"),
        Call("X", d, "G", "b", "B", 120.0, 120.0, "Buy", 1, "reported", "initiation"),
        Call("X", d + timedelta(days=30), "G", "b", "B", None, None, None, None, None, "termination"),
    ]
    act = active_targets(calls, d + timedelta(days=60), 180)
    assert set(act) == {"a"}
    assert normalize_action("terminates_coverage_on") == "termination"


def test_action_vocabularies_and_split_factor():
    assert normalize_action("init") == "initiation"
    assert normalize_action("Initiates Coverage On") == "initiation"
    assert normalize_action("Upgrades") == "upgrade"
    assert normalize_action("downgrade") == "downgrade"
    assert normalize_action("maintain") == "reiteration"
    assert normalize_action("Raises") == "reiteration"
    assert split_factor_after([(date(2020, 8, 31), 4.0), (date(2014, 6, 9), 7.0)], date(2013, 1, 1)) == 28.0
    assert split_factor_after([(date(2020, 8, 31), 4.0)], date(2021, 1, 1)) == 1.0


# ---- scoring a call -------------------------------------------------------------------------------


def _book(start: date, closes: list[float]) -> PriceBook:
    idx = pd.bdate_range(start, periods=len(closes))
    df = pd.DataFrame({"close": closes, "adj_close": closes}, index=idx)
    return PriceBook.from_frame(df)


def _call(d, target, norm, key="name:a|f", firm="F", ticker="X"):
    return Call(
        ticker,
        d,
        firm,
        key,
        "A",
        target,
        target,
        {1: "Buy", 0: "Hold", -1: "Sell"}.get(norm),
        norm,
        "reported",
        "reiteration",
    )


def test_call_scoring_hit_error_and_excess():
    n = 400
    stock = _book(date(2020, 1, 1), list(np.linspace(100, 160, n)))  # +60% steady climb
    mkt = _book(date(2020, 1, 1), list(np.linspace(100, 110, n)))
    books = {"X": stock, "M": mkt}
    d0 = pd.Timestamp(stock.dates[0]).date()
    as_of = pd.Timestamp(stock.dates[-1]).date()
    calls = [
        _call(d0, 130.0, 1),  # bullish target reached
        _call(d0, 200.0, 1, key="name:b|f"),  # bullish target not reached
        _call(d0, 90.0, -1, key="name:c|f"),  # bearish call on a rising stock
    ]
    df = score_calls(calls, books, {"X": ("M", None)}, as_of, ACFG, {"X": "technology"})
    p12 = stock.close[252]
    assert list(df["hit"]) == [1.0, 0.0, 0.0]
    assert df["ape"].iloc[0] == pytest.approx(abs(p12 / 130 - 1))
    r12, m12 = stock.adj[252] / 100 - 1, mkt.adj[252] / 100 - 1
    assert df["x_12m_mkt"].iloc[0] == pytest.approx(r12 - m12)
    assert df["x_12m_mkt"].iloc[2] == pytest.approx(-(r12 - m12))  # a Sell call is scored on the reverse
    assert np.isnan(df["x_12m_sec"].iloc[0])  # no sector fund given
    assert df["optimism_bias"].iloc[1] == pytest.approx(200 / 100 - 1 - (p12 / 100 - 1))


def test_no_look_ahead_for_unmatured_horizons():
    n = 300
    stock = _book(date(2020, 1, 1), list(np.linspace(100, 130, n)))
    books = {"X": stock, "M": stock}
    as_of = pd.Timestamp(stock.dates[-1]).date()
    recent = pd.Timestamp(stock.dates[-100]).date()  # 99 trading days before the report date
    df = score_calls([_call(recent, 150.0, 1)], books, {"X": ("M", None)}, as_of, ACFG, {})
    row = df.iloc[0]
    assert np.isnan(row["hit"]) and np.isnan(row["ape"]) and np.isnan(row["x_6m_mkt"])
    assert not np.isnan(row["x_3m_mkt"])  # 63 trading days have passed
    future = score_calls(
        [_call(as_of + timedelta(days=5), 150.0, 1)], books, {"X": ("M", None)}, as_of, ACFG, {}
    )
    assert future.empty  # calls after the report date do not exist yet


def test_shrinkage_three_for_three_does_not_outrank_sixty_for_ninety():
    rows = []
    d = date(2025, 1, 1)
    for _ in range(3):
        rows.append(
            {
                "analyst_key": "lucky",
                "hit": 1.0,
                "ape": 0.2,
                "directional": 0.0,
                "optimism_bias": 0.1,
                "weight": 1.0,
                "dir_source": "rating",
                "dir": 1,
                "scored": True,
                "date": d,
            }
        )
    for i in range(90):
        rows.append(
            {
                "analyst_key": "steady",
                "hit": 1.0 if i < 60 else 0.0,
                "ape": 0.2,
                "directional": 0.0,
                "optimism_bias": 0.1,
                "weight": 1.0,
                "dir_source": "rating",
                "dir": 1,
                "scored": True,
                "date": d,
            }
        )
    df = pd.DataFrame(rows)
    prior = {"hit_rate": 0.5, "mape": 0.2, "directional": 0.0, "optimism_bias": 0.1}
    k = ACFG["shrinkage_k"]
    lucky = shrink(raw_metrics(df[df.analyst_key == "lucky"]), prior, k)
    steady = shrink(raw_metrics(df[df.analyst_key == "steady"]), prior, k)
    assert lucky["hit_rate"] == pytest.approx((3 + k * 0.5) / (3 + k))
    assert steady["hit_rate"] == pytest.approx((60 + k * 0.5) / (90 + k))
    assert steady["hit_rate"] > lucky["hit_rate"]
    assert composite(steady, ACFG)[0] > composite(lucky, ACFG)[0]


def test_hierarchy_ticker_record_shrinks_toward_sector_then_all():
    rows = []
    for t, sec, n, hit in (("A", "tech", 40, 0.8), ("B", "tech", 2, 0.0), ("C", "energy", 40, 0.3)):
        for i in range(n):
            rows.append(
                {
                    "ticker": t,
                    "sector": sec,
                    "analyst_key": "x",
                    "firm": "F",
                    "hit": hit if hit in (0.0,) else float(i < hit * n),
                    "ape": 0.2,
                    "directional": 0.0,
                    "optimism_bias": 0.0,
                    "weight": 1.0,
                    "dir_source": "rating",
                    "dir": 1,
                    "scored": True,
                    "date": date(2025, 1, 1),
                }
            )
    df = pd.DataFrame(rows)
    s = trust_scores(df, "B", "tech", ACFG, "analyst")["x"]
    # On B the analyst went 0 for 2, but their tech record (mostly A, 32/42) dominates the estimate.
    assert s["raw_ticker"]["hit_rate"]["value"] == 0.0
    assert 0.55 < s["metrics"]["hit_rate"] < s["raw_sector"]["hit_rate"]["value"] + 0.01


def test_herding_measures_moves_toward_consensus():
    d = date(2024, 1, 1)
    calls = []
    for i, (who, tgt) in enumerate((("o1", 100.0), ("o2", 102.0), ("o3", 98.0))):
        calls.append(
            Call("X", d + timedelta(days=i), "F", who, who, tgt, tgt, None, None, None, "initiation")
        )
    herder = Call(
        "X",
        d + timedelta(days=10),
        "F",
        "h",
        "h",
        101.0,
        101.0,
        None,
        None,
        None,
        "reiteration",
        target_prior=150.0,
    )
    loner = Call(
        "X",
        d + timedelta(days=11),
        "F",
        "l",
        "l",
        160.0,
        160.0,
        None,
        None,
        None,
        "reiteration",
        target_prior=150.0,
    )
    h = herding([*calls, herder, loner], 180)
    assert h["h"]["value"] == pytest.approx((50 - 1) / 50, abs=0.01)
    assert h["l"]["value"] < 0


# ---- consensus --------------------------------------------------------------------------------------


def _row(who, target, score, stale=False, norm=1, days=10):
    return {
        "who": who,
        "target": target,
        "trust_score": score,
        "stale": stale,
        "rating_norm": norm,
        "days_old": days,
        "analyst": who,
        "firm": "F",
    }


def test_consensus_all_vs_trusted_and_outliers():
    rows = [
        _row("a", 100, 90),
        _row("b", 120, 30),
        _row("c", 110, 60, norm=0),
        _row("old", 300, 90, stale=True, days=400),
        _row("typo", 1000, 50),
    ]
    cs = consensus(rows, 100.0, ACFG, prior_score=50)
    assert cs["n_outliers"] == 1 and rows[4]["outlier"] and rows[4]["stale"]
    assert cs["all"] == pytest.approx(110.0)
    g = ACFG["trusted_weight_gamma"]
    w = np.array([0.9, 0.3, 0.6]) ** g
    assert cs["trusted"] == pytest.approx(float(np.dot(w, [100, 120, 110]) / w.sum()))
    assert cs["trusted"] < cs["all"]  # the best analyst has the lowest target
    assert cs["dispersion"] == pytest.approx((120 - 100) / 110)
    assert cs["upside_trusted"] == pytest.approx(cs["trusted"] / 100 - 1)
    assert sum(cs["weights"].values()) == pytest.approx(1.0)
    # rating: stale-for-ratings rows (> 12 months) drop out; outliers keep their rating
    assert cs["average_rating"] == pytest.approx((1 + 1 + 0 + 1) / 4)


# ---- the section on the synthetic market ----------------------------------------------------------------


@pytest.fixture(scope="module")
def zztec():
    return get_section("ZZTEC", "analysts")


def test_section_consensus_matches_rows(zztec):
    a = zztec
    assert a["status"] == "ok" and a["granularity"] == "analyst"
    active = [r for r in a["rows"] if not r["stale"] and r["target"]]
    assert active and all(r["days_old"] <= ACFG["stale_months"] * 30 for r in active)
    assert a["consensus_all"] == pytest.approx(np.mean([r["target"] for r in active]))
    assert a["trusted_upside"] == pytest.approx(a["consensus_trusted"] / a["price"] - 1)
    assert all(0 <= r["trust_score"] <= 100 for r in a["rows"] if r["trust_score"] is not None)
    assert a["rows"] == sorted(a["rows"], key=lambda r: r["stale"])  # active first
    assert a["coverage"]["stocks"] >= 5 and a["coverage"]["scored_calls"] > 500
    assert a["methodology"] and a["firm_cards"]
    for c in a["firm_cards"]:
        assert c["summary"] and c["reasoning"] is None and "does not include" in c["reasoning_note"]


def test_scores_recover_synthetic_skill_and_bias():
    """The synthetic analysts have known skill and optimism; the scores must rank them the right way."""
    from engine import clock
    from engine.analysts.scoring import all_scope_scores
    from engine.analysts.service import prepare
    from engine.data.service import get_data
    from engine.synthetic.world import get_world

    get_section("ZZTEC", "analysts")  # ingests the synthetic universe
    prep = prepare(get_data(), get_config(), clock.today(), True)
    sc = all_scope_scores(prep["df"], ACFG, "analyst")
    truth = {f"name:{a['name'].lower()}|{a['firm'].lower()}": a for a in get_world().analysts}
    keys = sorted(k for k in sc if k in truth)
    assert len(keys) >= 12
    score = [sc[k]["score"] for k in keys]
    assert (
        spearmanr([sc[k]["metrics"]["optimism_bias"] for k in keys], [truth[k]["bias"] for k in keys])[0]
        > 0.5
    )
    assert spearmanr(score, [truth[k]["bias"] for k in keys])[0] < 0
    assert spearmanr(score, [truth[k]["skill"] for k in keys])[0] > 0


def test_accurate_analyst_outscores_noisy_one_on_same_stock():
    rng = np.random.default_rng(3)
    n = 252 * 7
    px = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.018, n)))
    mkt = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n)))
    stock, bench = _book(date(2015, 1, 1), list(px)), _book(date(2015, 1, 1), list(mkt))
    calls = []
    for i in range(0, n - 252, 21):
        d = pd.Timestamp(stock.dates[i]).date()
        truth12 = px[i + 252]
        for key, sd in (("name:sharp|f", 0.05), ("name:noisy|g", 0.45)):
            tgt = truth12 * float(np.exp(rng.normal(0, sd)))
            norm = 1 if tgt > px[i] * 1.08 else -1 if tgt < px[i] * 0.94 else 0
            calls.append(_call(d, tgt, norm, key=key, firm=key[-1].upper()))
    as_of = pd.Timestamp(stock.dates[-1]).date()
    df = score_calls(calls, {"X": stock, "M": bench}, {"X": ("M", None)}, as_of, ACFG, {"X": "technology"})
    s = trust_scores(df, "X", "technology", ACFG, "analyst")
    assert s["name:sharp|f"]["score"] > s["name:noisy|g"]["score"] + 15
    assert s["name:sharp|f"]["metrics"]["mape"] < s["name:noisy|g"]["metrics"]["mape"]
    assert s["name:sharp|f"]["metrics"]["directional"] > s["name:noisy|g"]["metrics"]["directional"]


def test_uncovered_stock_reports_missing_not_invented():
    a = get_section("ZZSML", "analysts")
    assert a["status"] == "missing" and "No analyst" in a["reason"]
    v = get_section("ZZSML", "valuation")
    an = next(m for m in v["methods"] if m["id"] == "analyst_consensus")
    assert an["value"] is None and an["reason"]


def test_valuation_blends_trusted_consensus(zztec):
    v = get_section("ZZTEC", "valuation")
    row = next(r for r in v["blend"] if r["id"] == "analyst_consensus")
    assert row["target_12m"] == pytest.approx(zztec["consensus_trusted"])
    h = get_section("ZZTEC", "headline")
    assert h["consensus"]["trusted"] == pytest.approx(zztec["consensus_trusted"])


def test_analysts_point_in_time():
    as_of = date(2024, 6, 28)
    a = get_section("ZZTEC", "analysts", as_of=as_of, pit=True)
    assert a["status"] == "ok"
    assert all(date.fromisoformat(r["date"]) <= as_of for r in a["rows"])
    ctx = contexts.get("ZZTEC", as_of, True)
    from engine.analysts.service import compute

    df = compute(ctx)["calls_frame"]
    assert max(df["date"]) <= as_of
    last_matured = pd.Timestamp(ctx.prices.index[-253]).date()
    assert df.loc[df["date"] > last_matured, "hit"].isna().all()
    assert df.loc[df["date"] <= last_matured - timedelta(days=5), "hit"].notna().any()


def test_consensus_only_tier(reset_env, monkeypatch):
    monkeypatch.setenv("DATA_TIER", "free")
    reset_env()
    a = get_section("ZZTEC", "analysts")
    assert a["granularity"] == "consensus" and a["status"] == "partial"
    assert "unavailable on this data tier" in a["granularity_label"]
    assert a["consensus_trusted"] is None and a["rows"] == []
    assert sum(a["rating_history"]["buy"]) + sum(a["rating_history"]["hold"]) > 0


def test_nightly_job_stores_scores():
    from sqlalchemy import select

    from engine import clock
    from engine.analysts.service import score_and_store
    from engine.data.service import get_data
    from engine.db import models as m
    from engine.db.session import session_scope

    res = score_and_store(get_data(), get_config(), clock.today(), True)
    assert res["analysts"] >= 12 and res["firms"] >= 5
    with session_scope() as s:
        rows = s.execute(select(m.AnalystScore)).scalars().all()
        assert all(0 <= r.trust_score <= 100 for r in rows if r.trust_score is not None)
        assert any(r.excess_12m is not None for r in rows)
