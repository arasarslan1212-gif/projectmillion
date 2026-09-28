"""Earnings, dividends and ownership sections."""

from datetime import date, timedelta

import pandas as pd
import pytest

from engine.config import get_config
from engine.providers.models import InsiderTransaction
from engine.report.builder import contexts, get_section
from engine.report.sections.earnings import reaction
from engine.report.sections.ownership import insider_summary


def _series(values, start="2026-01-05"):
    return pd.Series(values, index=pd.bdate_range(start, periods=len(values)), dtype=float)


def test_reaction_windows_by_timing():
    px = _series([100, 100, 110, 121, 121, 121, 121, 121])  # Mon 5 Jan .. ; report on Wed 7 Jan (index 2)
    d = date(2026, 1, 7)
    # before open: base = Tue close 100, first reacting session = Wed 110
    assert reaction(px, None, d, "bmo", 1)["ret"] == pytest.approx(0.10)
    # after close: base = Wed close 110, first reacting session = Thu 121
    assert reaction(px, None, d, "amc", 1)["ret"] == pytest.approx(0.10)
    # unknown: from Tue 100 through Thu 121, covering both
    assert reaction(px, None, d, None, 1)["ret"] == pytest.approx(0.21)
    mkt = _series([100, 100, 101, 102, 102, 102, 102, 102])
    assert reaction(px, mkt, d, "amc", 1)["excess"] == pytest.approx(0.10 - (102 / 101 - 1))
    assert reaction(px, None, date(2026, 1, 14), "amc", 5)["ret"] is None  # not enough sessions after


def test_earnings_section():
    e = get_section("ZZBNK", "earnings")
    assert e["status"] == "ok" and 0 < len(e["quarters"]) <= 12
    as_of = contexts.get("ZZBNK", None, False).as_of
    assert all(date.fromisoformat(q["date"]) <= as_of for q in e["quarters"])
    beats = [q["eps_surprise"] > 0 for q in e["quarters"] if q["eps_surprise"] is not None]
    assert e["metrics"]["beat_rate"]["value"] == pytest.approx(sum(beats) / len(beats))
    assert date.fromisoformat(e["next_date"]) > as_of and e["next_in_days"] > 0
    assert e["guidance"]["status"] == "not_available" and e["guidance_hit_rate"] is None


def test_earnings_point_in_time_has_no_future_date():
    e = get_section("ZZBNK", "earnings", as_of=date(2025, 6, 30), pit=True)
    assert e["next_date"] is None
    assert all(q["date"] <= "2025-06-30" for q in e["quarters"])


def test_dividends_payer_and_non_payer():
    d = get_section("ZZBNK", "dividends")
    assert d["status"] == "ok" and d["pays_dividend"]
    ann = {a["year"]: a["dps"] for a in d["annual"]}
    ys = sorted(ann)
    streak = 0
    for a, b in zip(reversed(ys[:-1]), reversed(ys[1:]), strict=True):
        if b - a == 1 and ann[b] > ann[a] * 1.001:
            streak += 1
        else:
            break
    assert d["metrics"]["streak"]["value"] == streak
    assert d["metrics"]["cagr_5y"]["value"] == pytest.approx((ann[ys[-1]] / ann[ys[-6]]) ** (1 / 5) - 1)
    assert 0 <= d["metrics"]["safety"]["value"] <= 100
    g = get_section("ZZGRO", "dividends")
    assert g["status"] == "not_applicable" and not g["pays_dividend"]


def test_utility_dividend_safety_skips_fcf_payout():
    d = get_section("ZZUTL", "dividends")
    comps = {c["id"]: c for c in d["safety_components"]}
    assert comps["fcf_payout"]["skipped"] and comps["fcf_payout"]["score"] is None
    assert (
        comps["leverage"]["anchors"]
        == get_config().data["dividends"]["profile_anchors"]["utility"]["leverage"]
    )


def _tx(name, code, d, shares=1000, price=10.0, plan=None):
    return InsiderTransaction(ticker="X", filer_name=name, tx_date=d, filed_at=d + timedelta(days=2), code=code,
                              acquired=code in "PMA", shares=shares, price=price, plan_10b5_1=plan,
                              accession=f"{name}{d}", derivative=False)  # fmt: skip


def test_insider_classes_and_cluster_rule():
    cfg = get_config().data["ownership"]
    as_of = date(2026, 9, 25)
    txs = [
        _tx("A", "P", date(2026, 8, 1)),
        _tx("B", "P", date(2026, 8, 20)),
        _tx("C", "P", date(2026, 8, 29)),  # third distinct buyer within 30 days of the first
        _tx("A", "P", date(2026, 3, 1)),  # an isolated purchase: not a cluster
        _tx("D", "S", date(2026, 7, 1), shares=500, price=20.0, plan=True),
        _tx("E", "S", date(2026, 7, 2), shares=500, price=20.0, plan=False),
        _tx("F", "M", date(2026, 7, 3)),
        _tx("G", "F", date(2026, 7, 4)),
        _tx("H", "S", date(2023, 1, 1)),  # outside the 24-month window
    ]
    s = insider_summary(txs, as_of, cfg)
    assert len(s["clusters"]) == 1 and s["clusters"][0]["insiders"] == ["A", "B", "C"]
    assert s["buy_6m"] == pytest.approx(3 * 10_000) and s["sell_6m"] == pytest.approx(20_000)
    assert s["sell_6m_plan"] == pytest.approx(10_000)
    assert s["counts"] == {"purchase": 4, "sale": 2, "exercise": 1, "tax": 1}


def test_ownership_section_and_point_in_time():
    o = get_section("ZZBNK", "ownership")
    assert o["status"] == "ok"
    assert o["metrics"]["clusters"]["value"] == 1  # the synthetic bank has one planted cluster buy
    bb = o["buybacks"]
    if bb["years"]:
        shares = sum(y["spent"] / y["avg_price"] for y in bb["years"])
        p0 = contexts.get("ZZBNK", None, False).last_price
        assert bb["return_on_buybacks"] == pytest.approx(shares * p0 / bb["spent"] - 1)
    old = get_section("ZZBNK", "ownership", as_of=date(2025, 12, 31), pit=True)
    assert all(r["date"] <= "2025-12-31" for r in (old["insiders"] or {}).get("rows", []))
    si = old["short_interest"]["series"]
    assert si[-1]["date"] <= (date(2025, 12, 31) - timedelta(days=12)).isoformat()
