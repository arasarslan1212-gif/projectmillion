from fastapi.testclient import TestClient

from engine.api.main import app
from engine.report.builder import get_section


def test_bank_profile_switches_kpis_and_marks_untagged_items():
    f = get_section("ZZBNK", "fundamentals")
    kpis = {m["id"]: m for m in f["sector_kpis"]}
    assert 0.01 < kpis["nim"]["value"] < 0.06
    assert kpis["cet1"]["value"] is None and "XBRL" in kpis["cet1"]["reason"]
    q = {m["id"]: m for m in f["quality"]["metrics"]}
    assert q["roic"]["value"] is None and "not meaningful" in q["roic"]["reason"]
    income_keys = [r["key"] for r in f["annual"]["statements"]["income"]]
    assert "net_interest_income" in income_keys and "gross_profit" not in income_keys


def test_reit_and_growth_kpis():
    reit = {m["id"]: m for m in get_section("ZZREI", "fundamentals")["sector_kpis"]}
    assert reit["ffo"]["value"] > 0 and reit["occupancy"]["value"] is None
    gro = {m["id"]: m for m in get_section("ZZGRO", "fundamentals")["sector_kpis"]}
    assert gro["rule_of_40"]["value"] is not None


def test_statement_values_and_common_size():
    f = get_section("ZZTEC", "fundamentals")
    inc = {r["key"]: r for r in f["annual"]["statements"]["income"]}
    assert inc["revenue"]["common_size"][-1] == 1.0
    gp = inc["gross_profit"]
    assert 0.3 < gp["common_size"][-1] < 0.6
    assert f["estimates"]["rows"] and f["estimates"]["rows"][0]["label"].endswith("E")


def test_overview_is_written_from_facts_only():
    o = get_section("ZZTEC", "overview")
    assert (
        "fictional company generated for software testing" not in o["description"]
    )  # provider text not reproduced
    assert "revenue" in o["description"]
    facts = {m["id"]: m for m in o["facts"]}
    assert facts["founded"]["value"] is None and facts["founded"]["reason"]


def test_peer_override_and_ranks():
    with TestClient(app) as c:
        auto = c.get("/api/report/ZZUTL/section/peers").json()
        assert auto["rows"][0]["is_subject"] and len(auto["rows"]) > 3
        custom = c.get("/api/report/ZZUTL/section/peers", params={"peers": "ZQU01,ZQU02,ZQU03"}).json()
        assert [r["ticker"] for r in custom["rows"]] == ["ZZUTL", "ZQU01", "ZQU02", "ZQU03"]
        assert "chosen by you" in custom["selection_note"]
        pe = [r["metrics"]["pe"] for r in auto["rows"] if r["metrics"]["pe"]]
        assert all(3 < x < 200 for x in pe)
