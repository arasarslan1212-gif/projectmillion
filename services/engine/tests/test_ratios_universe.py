from datetime import date

import pytest

from engine.fundamentals.ratios import cagr, period_ratios, series_cagr, yoy
from engine.fundamentals.statements import Period, derive
from engine.fundamentals.universe import frame_year, percentile_of


def _p(values, end=date(2025, 12, 31)):
    p = Period("FY", date(end.year, 1, 1), end, end, None)
    p.values = dict(values)
    derive(p)
    return p


def test_growth_math_by_hand():
    assert cagr(100, 121, 2) == pytest.approx(0.10)
    assert cagr(-5, 10, 3) is None  # undefined across a sign change
    assert yoy(-50, -100) == pytest.approx(0.5)  # a smaller loss is an improvement
    pts = [(date(2020 + i, 12, 31), 100 * 1.1**i) for i in range(6)]
    assert series_cagr(pts, 5) == pytest.approx(0.10)
    assert series_cagr(pts, 10) is None


def test_period_ratios_general():
    prev = _p(
        {
            "equity": 90,
            "total_assets": 190,
            "receivables": 10,
            "inventory": 5,
            "accounts_payable": 8,
            "total_debt": 40,
            "cash": 10,
        }
    )
    cur = _p(
        {
            "revenue": 200,
            "cost_of_revenue": 120,
            "operating_income": 40,
            "interest_expense": 4,
            "pretax_income": 36,
            "income_tax": 9,
            "net_income": 27,
            "dna": 10,
            "cfo": 45,
            "capex": 15,
            "sbc": 4,
            "equity": 110,
            "total_assets": 210,
            "current_assets": 80,
            "current_liabilities": 40,
            "cash": 20,
            "receivables": 14,
            "inventory": 7,
            "accounts_payable": 12,
            "debt_noncurrent": 50,
        }
    )
    r = period_ratios(cur, prev)
    assert r["gross_margin"] == pytest.approx(0.4)
    assert r["operating_margin"] == pytest.approx(0.2)
    assert r["roe"] == pytest.approx(27 / 100)  # average equity
    assert r["interest_coverage"] == pytest.approx(10.0)
    assert r["fcf_margin"] == pytest.approx(30 / 200)
    assert r["fcf_conversion"] == pytest.approx(30 / 27)
    assert r["current_ratio"] == pytest.approx(2.0)
    assert r["dso"] == pytest.approx(12 / (200 / 365))
    assert r["net_debt_to_ebitda"] == pytest.approx((50 - 20) / 50)
    # ROIC: NOPAT at the 25% effective tax rate over average invested capital
    ic_prev, ic_cur = 90 + 40 - 10, 110 + 50 - 20
    assert r["roic"] == pytest.approx(40 * 0.75 / ((ic_prev + ic_cur) / 2))


def test_bank_and_reit_kpis():
    bank = _p(
        {
            "interest_income": 50,
            "interest_expense": 20,
            "noninterest_income": 10,
            "noninterest_expense": 24,
            "net_income": 9,
            "total_assets": 1000,
            "loans": 600,
            "deposits": 800,
            "equity": 90,
        }
    )
    r = period_ratios(bank, _p({"total_assets": 1000, "equity": 90}))
    assert r["nim"] == pytest.approx(30 / 1000)
    assert r["efficiency_ratio"] == pytest.approx(24 / 40)
    assert r["loan_to_deposit"] == pytest.approx(0.75)
    reit = _p({"revenue": 100, "net_income": 20, "dna": 40, "gain_on_sale_re": 5, "capex": 3})
    rr = period_ratios(reit, None)
    assert rr["ffo"] == pytest.approx(55)
    assert rr["affo"] == pytest.approx(52)


def test_frame_year_respects_filing_lag():
    assert frame_year(date(2026, 9, 25), 120) == 2025
    assert frame_year(date(2026, 3, 1), 120) == 2024  # FY2025 10-Ks may not all be filed yet


def test_percentile_direction_and_winsorizing():
    pop = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    assert percentile_of(10, pop) == pytest.approx(95.0)
    assert percentile_of(10, pop, higher_is_better=False) == pytest.approx(5.0)
    assert percentile_of(1e9, pop) == percentile_of(10, pop)  # an outlier can't exceed the top bucket
    assert percentile_of(None, pop) is None
    assert percentile_of(3, [1]) is None
