"""M10 extras: pre-mortem, capital allocation, quantitative views, 10-K risk-factor diff and alerts."""

import copy
from datetime import date

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient
from scipy.stats import norm
from sqlalchemy import delete, select

from engine.alerts import service as alerts
from engine.analysis.filing_diff import diff_units, risk_section, risk_units
from engine.api.main import app
from engine.db import models as m
from engine.db.session import session_scope
from engine.explain.facts import Fact, Facts
from engine.explain.narrative import check_sentence
from engine.llm.validate import unsupported_numbers
from engine.report.builder import contexts, get_section
from engine.report.sections.quant import ols

client = TestClient(app)


# ---- pre-mortem --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("ticker", ["ZZTEC", "ZZREI", "ZZSML"])
def test_premortem_is_grounded_in_facts(ticker):
    e = get_section(ticker, "explain")
    F = Facts()
    F.items = {f["id"]: Fact(**f) for f in e["facts"]}
    pm = e["parts"]["premortem"]
    assert "premortem.fall" in pm["plain"][0]["facts"] and "40%" in pm["plain"][0]["text"]
    assert 2 <= len(pm["plain"]) <= 6 and len(pm["reasons"]) <= 4
    for mode in ("plain", "analyst"):
        for s in pm[mode]:
            assert check_sentence(s, F) == [], s["text"]
    # a degenerate (near-zero) bear case is never offered as a reason
    bear = F.get("val.scenario.bear.value")
    if bear is not None and bear < 0.05 * F.get("price"):
        assert not any("bear" in r["plain"] for r in pm["reasons"])


def test_validator_understands_bounds():
    p = [{"value": 0.9996, "unit": "prob"}]
    assert unsupported_numbers("a >99% chance", p) == []
    assert unsupported_numbers("a >99% chance", [{"value": 0.95, "unit": "prob"}]) == [">99%"]
    assert unsupported_numbers("under <1% odds", [{"value": 0.004, "unit": "prob"}]) == []
    assert unsupported_numbers("under <1% odds", [{"value": 0.02, "unit": "prob"}]) == ["<1%"]


# ---- capital allocation --------------------------------------------------------------------------------------------


def test_capital_allocation_scorecard():
    c = get_section("ZZTEC", "capital")
    assert c["status"] == "ok"
    comps = {k["id"]: k for k in c["components"]}
    ctx = contexts.get("ZZTEC", None, False)
    win = ctx.fin.annual[-5:]
    fcf = sum(p.get("fcf") or 0 for p in win)
    pay = sum((p.get("dividends_paid") or 0) + (p.get("buybacks") or 0) for p in win)
    cov = next(x for x in comps["payouts"]["metrics"] if x["id"] == "payout_coverage")
    assert cov["value"] == pytest.approx(pay / fcf)
    # buybacks judged against the same cash in the market index, year by year
    closes, mkt = ctx.prices["close"], ctx.market_prices["close"]
    own = mk = spent = 0.0
    for p in win:
        bb = p.get("buybacks") or 0
        sl = closes[
            (closes.index > pd.Timestamp(p.end) - pd.Timedelta(days=365))
            & (closes.index <= pd.Timestamp(p.end))
        ]
        ml = mkt[
            (mkt.index > pd.Timestamp(p.end) - pd.Timedelta(days=365)) & (mkt.index <= pd.Timestamp(p.end))
        ]
        if bb > 0 and len(sl) >= 60 and len(ml) >= 60:
            spent += bb
            own += bb * ctx.last_price / sl.mean()
            mk += bb * mkt.iloc[-1] / ml.mean()
    rel = next(x for x in comps["buybacks"]["metrics"] if x["id"] == "buyback_vs_market")
    assert rel["value"] == pytest.approx(own / mk - 1)
    # the score is the weighted mean of the components that apply
    w = {"reinvestment": 0.30, "buybacks": 0.20, "dilution": 0.20, "payouts": 0.15, "dividends": 0.15}
    sc = [(w[k], v["score"]) for k, v in comps.items() if v["score"] is not None]
    assert c["score"]["value"] == pytest.approx(sum(a * b for a, b in sc) / sum(a for a, _ in sc))
    reit = {k["id"]: k for k in get_section("ZZREI", "capital")["components"]}
    assert reit["reinvestment"]["score"] is None and "REIT" in reit["reinvestment"]["skipped"]
    gro = {k["id"]: k for k in get_section("ZZGRO", "capital")["components"]}
    assert gro["dividends"]["skipped"] and "not a negative" in gro["dividends"]["skipped"]


# ---- quantitative views ------------------------------------------------------------------------------------------


def test_ols_recovers_known_coefficients():
    rng = np.random.default_rng(3)
    X = rng.normal(size=(400, 2))
    y = 0.01 + 1.3 * X[:, 0] - 0.4 * X[:, 1] + rng.normal(0, 0.1, 400)
    r = ols(y, X)
    assert r["beta"] == pytest.approx([0.01, 1.3, -0.4], abs=0.02)
    assert abs(r["t"][1]) > 50 and r["r2"] > 0.9


def test_quant_section_and_point_in_time():
    q = get_section("ZZTEC", "quant")
    assert q["factors"]["status"] == "ok" and q["factors"]["n_weeks"] == 156
    ids = [r["id"] for r in q["factors"]["rows"]]
    assert ids[0] == "market" and {"size", "value", "momentum", "quality", "low_vol"} <= set(ids)
    assert {r["id"] for r in q["macro"]["rows"]} == {"DGS10", "BAA10Y", "DCOILWTICO", "DTWEXBGS"}
    s = q["seasonality"]
    assert len(s["rows"]) == 12 and s["t_threshold"] == pytest.approx(norm.ppf(1 - 0.05 / 24))
    past = get_section("ZZTEC", "quant", as_of=date(2023, 6, 30), pit=True)
    assert past["factors"]["end"] <= "2023-06-30"


# ---- 10-K risk factors ----------------------------------------------------------------------------------------------


def test_risk_section_skips_table_of_contents_and_diffs():
    text = (
        "Table of contents\nItem 1A. Risk Factors 12\nItem 1B. Unresolved Staff Comments 20\n\n"
        "Item 1A. Risk Factors\nCompetition: we face intense competition from larger companies with more resources.\n"
        "Supply chain: we depend on a limited number of suppliers for key components of our products.\n"
        "Item 1B. Unresolved Staff Comments\nNone."
    )
    sec = risk_section(text)
    assert sec.startswith("Competition") and "Unresolved" not in sec
    prev = risk_units(sec)
    cur = risk_units(
        "Competition: we face intense competition from larger companies with more resources and new entrants.\n"
        "Going concern: recurring losses raise substantial doubt about our ability to continue operating as planned."
    )
    d = diff_units(prev, cur)
    assert len(d["added"]) == 1 and d["added"][0]["title"].startswith("Going concern")
    assert len(d["removed"]) == 1 and d["removed"][0]["title"].startswith("Supply chain")
    assert len(d["reworded"]) == 1 and d["reworded"][0]["title"].startswith("Competition")


def test_zzsml_latest_10k_adds_going_concern_risk():
    r = get_section("ZZSML", "risk")["risk_factor_changes"]
    assert r["status"] == "ok" and r["latest"]["filed"] > r["previous"]["filed"]
    assert any(x["title"].startswith("Going concern") for x in r["added"])


# ---- alerts --------------------------------------------------------------------------------------------------------


@pytest.fixture
def clean_alerts():
    def wipe():
        with session_scope() as s:
            for t in (m.AlertEvent, m.Alert, m.WatchlistItem):
                s.execute(delete(t))

    wipe()
    yield
    wipe()


def test_alerts_sync_evaluate_dedupe_and_rules(clean_alerts):
    assert alerts.sync_watchlist(["zztec", "ZZBNK"]) == ["ZZTEC", "ZZBNK"]
    res = alerts.evaluate()
    ib = alerts.inbox()
    kinds = {e["kind"] for e in ib["events"]}
    assert res["new_events"] == len(ib["events"]) > 0
    assert {"analyst_change", "insider_cluster"} <= kinds  # ZZTEC high-trust downgrade, ZZBNK cluster buy
    for e in ib["events"]:
        if e["kind"] == "analyst_change":
            score = float(e["title"].rsplit("Trust Score ", 1)[1].rstrip(")"))
            assert score >= 70 and e["url"]
    assert alerts.evaluate()["new_events"] == 0  # stored once
    # switching a kind off stops it being evaluated
    alerts.set_rule("analyst_change", False)
    with session_scope() as s:
        for r in s.scalars(select(m.Alert).where(m.Alert.kind == "analyst_change", m.Alert.ticker != "*")):
            r.params_json = {**(r.params_json or {}), "since": "2020-01-01"}
        s.execute(delete(m.AlertEvent))
    alerts.evaluate()
    assert all(e["kind"] != "analyst_change" for e in alerts.inbox()["events"])
    assert alerts.mark_read() >= 0 and alerts.unread_count() == 0
    # removing a stock from the watchlist removes its rules
    alerts.sync_watchlist(["ZZBNK"])
    with session_scope() as s:
        assert not s.scalars(select(m.Alert).where(m.Alert.ticker == "ZZTEC")).first()


def test_band_and_trigger_alerts_fire_on_change(clean_alerts):
    alerts.sync_watchlist(["ZZUTL"])
    alerts.evaluate()  # first run: remembers the band state and the trigger thresholds
    with session_scope() as s:
        band = s.scalars(select(m.Alert).where(m.Alert.ticker == "ZZUTL", m.Alert.kind == "band")).one()
        assert band.params_json["band"] == "inside"
        band.params_json = {**band.params_json, "band": "above"}  # pretend it had been above the range
        trig = s.scalars(select(m.Alert).where(m.Alert.ticker == "ZZUTL", m.Alert.kind == "trigger")).one()
        base = copy.deepcopy(trig.params_json["triggers"])  # JSON columns only save a new object
        assert "leverage" in base
        base["leverage"]["threshold"] = -10.0  # any leverage now "crosses" it
        trig.params_json = {**trig.params_json, "triggers": base}
    alerts.evaluate()
    ev = {e["kind"]: e for e in alerts.inbox()["events"]}
    assert "moved back inside" in ev["band"]["title"]
    assert "first watched" in ev["trigger"]["detail"]


def test_alerts_api(clean_alerts):
    assert client.put("/api/watchlist", json={"tickers": ["ZZTEC"]}).json() == {"tickers": ["ZZTEC"]}
    assert client.post("/api/alerts/run").json()["tickers"] == 1
    body = client.get("/api/alerts").json()
    assert body["watchlist"] == ["ZZTEC"] and len(body["rules"]) == 5
    assert client.get("/api/alerts/unread").json()["unread"] == body["unread"]
    assert client.put("/api/alerts/rules/nope", json={"enabled": False}).status_code == 404
    assert client.post("/api/alerts/read", json={}).json()["marked"] == body["unread"]
