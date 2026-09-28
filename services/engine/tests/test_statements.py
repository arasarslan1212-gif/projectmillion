"""Point-in-time statements: exactness vs. the synthetic truth, no look-ahead, restatements, splits."""

from datetime import date

import pytest

from engine.fundamentals.statements import build_financials
from engine.providers.sec_edgar import SecEdgar
from engine.synthetic.world import get_world


@pytest.fixture(scope="module")
def zztec_facts():
    return SecEdgar().company_facts(9900001)


def test_quarters_match_truth_including_ytd_derivation(zztec_facts):
    fin = build_financials(zztec_facts, date(2026, 9, 25), [(date(2020, 8, 31), 4.0)])
    truth = {q.end: q for q in get_world().companies["ZZTEC"].quarters}
    checked = 0
    for p in fin.quarterly:
        q = truth[p.end]
        for k in ("revenue", "net_income", "cfo", "capex", "operating_income"):
            if k in p.values:
                assert p.values[k] == pytest.approx(q.flows[k], rel=1e-6, abs=2)
                checked += 1
    assert checked > 200
    # cash-flow quarters are derived from YTD values
    assert any(p.derived.get("cfo") == "derived from year-to-date values" for p in fin.quarterly)


def test_no_lookahead(zztec_facts):
    as_of = date(2019, 6, 1)
    fin = build_financials(zztec_facts, as_of, [])
    for p in fin.annual + fin.quarterly:
        for d in p.filed.values():
            assert d <= as_of
    assert fin.annual[-1].end < as_of


def test_split_adjusts_share_counts_to_current_units(zztec_facts):
    splits = [(date(2020, 8, 31), 4.0)]
    before = build_financials(zztec_facts, date(2020, 6, 30), splits)  # split not yet happened
    after = build_financials(zztec_facts, date(2026, 9, 25), splits)
    fy2019_before = next(p for p in before.annual if p.end.year == 2019)
    fy2019_after = next(p for p in after.annual if p.end.year == 2019)
    # as of mid-2020 the FY2019 share count is in pre-split units; later it is restated ×4
    assert fy2019_after.values["shares_diluted"] == pytest.approx(
        fy2019_before.values["shares_diluted"] * 4, rel=1e-6
    )
    assert fy2019_after.values["eps_diluted"] == pytest.approx(
        fy2019_before.values["eps_diluted"] / 4, rel=1e-3
    )


def test_restatement_visible_only_after_it_is_filed():
    facts = SecEdgar().company_facts(9900006)  # ZZSML: 10-K/A filed 2026-06-15 restates FY2024
    pre = build_financials(facts, date(2026, 6, 1), [])
    post = build_financials(facts, date(2026, 7, 1), [])
    ni_pre = next(p for p in pre.annual if p.end.year == 2024).values["net_income"]
    ni_post = next(p for p in post.annual if p.end.year == 2024).values["net_income"]
    assert ni_post < ni_pre < 0  # losses got larger after restatement


def test_ttm_is_sum_of_last_four_quarters(zztec_facts):
    fin = build_financials(zztec_facts, date(2026, 9, 25), [(date(2020, 8, 31), 4.0)])
    last4 = fin.quarterly[-4:]
    assert fin.ttm["revenue"] == pytest.approx(sum(q.values["revenue"] for q in last4))
    assert "sum of 4 quarters" in fin.ttm_note
    assert fin.ttm["fcf"] == pytest.approx(fin.ttm["cfo"] - fin.ttm["capex"])
