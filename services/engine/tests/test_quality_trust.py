from datetime import date

import pytest

from engine.analysis import quality as q
from engine.analysis.trust_rating import anchor_inverse, anchor_score, grade_for
from engine.config import get_config
from engine.fundamentals.statements import Period, derive
from engine.report.builder import get_section


def _p(values, year=2025):
    p = Period("FY", date(year, 1, 1), date(year, 12, 31), date(year, 12, 31), None)
    p.values = dict(values)
    derive(p)
    return p


def test_altman_z_manufacturer_by_hand():
    p = _p(
        {
            "current_assets": 400,
            "current_liabilities": 200,
            "retained_earnings": 300,
            "operating_income": 150,
            "total_assets": 1000,
            "total_liabilities": 500,
            "revenue": 1200,
            "equity": 500,
        }
    )
    s = q.altman_z(p, market_cap=1500, manufacturer=True)
    expected = 1.2 * 0.2 + 1.4 * 0.3 + 3.3 * 0.15 + 0.6 * 3.0 + 1.0 * 1.2
    assert s.value == pytest.approx(expected)
    assert s.zone == "safe"
    s2 = q.altman_z(p, market_cap=None, manufacturer=False)
    assert s2.value == pytest.approx(6.56 * 0.2 + 3.26 * 0.3 + 6.72 * 0.15 + 1.05 * 1.0)
    assert s2.variant.startswith("Altman Z''")


def test_piotroski_counts_signals():
    prev2 = _p({"total_assets": 900}, 2023)
    prev = _p(
        {
            "net_income": 50,
            "cfo": 60,
            "total_assets": 1000,
            "revenue": 800,
            "gross_profit": 300,
            "current_assets": 300,
            "current_liabilities": 200,
            "debt_noncurrent": 300,
            "shares_diluted": 100,
        },
        2024,
    )
    cur = _p(
        {
            "net_income": 80,
            "cfo": 100,
            "total_assets": 1050,
            "revenue": 950,
            "gross_profit": 380,
            "current_assets": 350,
            "current_liabilities": 200,
            "debt_noncurrent": 250,
            "shares_diluted": 98,
        },
        2025,
    )
    s = q.piotroski_f(cur, prev, prev2)
    assert s.value == 9
    worse = _p(
        {
            "net_income": -10,
            "cfo": -5,
            "total_assets": 1100,
            "revenue": 700,
            "gross_profit": 200,
            "current_assets": 250,
            "current_liabilities": 260,
            "debt_noncurrent": 400,
            "shares_diluted": 120,
        },
        2025,
    )
    assert q.piotroski_f(worse, prev, prev2).value <= 2


def test_beneish_neutral_company_scores_low():
    base = {
        "revenue": 1000,
        "receivables": 100,
        "gross_profit": 400,
        "current_assets": 300,
        "ppe": 400,
        "total_assets": 1000,
        "dna": 50,
        "sga": 200,
        "current_liabilities": 200,
        "debt_noncurrent": 200,
        "net_income": 80,
        "cfo": 100,
    }
    s = q.beneish_m(_p(base, 2025), _p(base, 2024))
    # all indices = 1 and TATA = -0.02: M = -4.84 + 0.92+0.528+0.404+0.892+0.115-0.172 - 0.09358 - 0.327
    assert s.value == pytest.approx(
        -4.84 + 0.920 + 0.528 + 0.404 + 0.892 + 0.115 - 0.172 + 4.679 * (-0.02) - 0.327
    )
    assert s.zone == "unlikely"


def test_anchor_mapping_and_grades():
    assert anchor_score(0.5, [0.0, 1.0]) == 50
    assert anchor_score(5.0, [5.0, 0.0]) == 0  # lower-is-better anchors are just reversed
    assert anchor_score(-1.0, [5.0, 0.0]) == 100  # clipped
    assert anchor_inverse(60, [5.0, 0.0]) == pytest.approx(2.0)
    bands = get_config()["trust_rating.grade_bands"]
    assert grade_for(92, bands) == "A+" and grade_for(71, bands) == "B" and grade_for(12, bands) == "F"


def test_config_weights_sum_to_one():
    for prof, w in get_config()["trust_rating.weights"].items():
        assert sum(w.values()) == pytest.approx(1.0), prof


def test_red_flags_fire_on_troubled_small_cap_and_not_on_healthy_company():
    risk = get_section("ZZSML", "risk")["red_flags"]
    ids = {f["id"] for f in risk["triggered"]}
    assert {"going_concern", "restatement", "auditor_change", "late_filing", "customer_concentration"} <= ids
    conc = next(f for f in risk["triggered"] if f["id"] == "customer_concentration")
    assert conc["value"] == pytest.approx(0.38)
    healthy = get_section("ZZTEC", "risk")["red_flags"]
    assert not {f["id"] for f in healthy["triggered"]} & {"going_concern", "restatement", "late_filing"}
    bank = get_section("ZZBNK", "risk")["red_flags"]
    assert any(n["id"] == "altman_z" and "not applicable" in n["reason"] for n in bank["not_checked"])


def test_trust_rating_reweights_missing_pillars_and_applies_caps():
    t = get_section("ZZSML", "trust")
    avail = [p for p in t["pillars"] if p["score"] is not None]
    assert sum(p["effective_weight"] for p in avail) == pytest.approx(1.0)
    assert t["missing_pillars"]  # analysts/management have no data for the small cap
    fh = next(p for p in t["pillars"] if p["id"] == "financial_health")
    assert fh["score"] <= 20  # going-concern cap (already below it here)
    caps = get_config()["trust_rating.red_flag_penalties"]
    for p in t["pillars"]:
        for fid in p["capped_by"]:
            assert p["score"] == caps[fid]["cap"]
    assert sum(d["points"] for d in t["deductions"]) > 20  # deductions accrued ...
    assert t["score"] == pytest.approx(max(0.0, t["raw_score"] - 20))  # ... but the total is capped
    healthy = get_section("ZZTEC", "trust")
    assert healthy["score"] > t["score"] + 30
    assert healthy["grade"] is not None


def test_bank_uses_bank_metrics():
    t = get_section("ZZBNK", "trust")
    fh = next(p for p in t["pillars"] if p["id"] == "financial_health")
    assert [m["id"] for m in fh["metrics"]] == ["equity_to_assets", "loan_to_deposit"]
    prof = next(p for p in t["pillars"] if p["id"] == "profitability")
    assert "rotce" in [m["id"] for m in prof["metrics"]]
