from engine.fundamentals.sector import detect, profile_for_sic, sector_for_sic


def test_sic_to_sector_and_profile():
    assert sector_for_sic(3571) == "technology"
    assert sector_for_sic(6021) == "financials"
    assert sector_for_sic(6798) == "real_estate"
    assert sector_for_sic(4911) == "utilities"
    assert sector_for_sic(2834) == "health_care"
    assert sector_for_sic(1311) == "energy"
    assert profile_for_sic(6021) == "bank"
    assert profile_for_sic(6331) == "insurer"
    assert profile_for_sic(6798) == "reit"
    assert profile_for_sic(4911) == "utility"
    assert profile_for_sic(7372) == "software"
    assert profile_for_sic(6211) == "financial_other"


def test_overlays():
    growth = detect(7372, "software", 4e9, -0.05, 0.3, 0.25)
    assert growth.profile == "growth_unprofitable" and growth.overlay_reason
    mature = detect(7372, "software", 4e9, 0.2, 0.3, 0.2)
    assert mature.profile == "software"
    biotech = detect(2834, "pharma", 50e6, -2.0, 0.1, 3.0)
    assert biotech.profile == "biotech_pipeline"
    bank = detect(6021, "bank", 1e9, -0.1, 0.5, None)
    assert bank.profile == "bank" and bank.is_financial  # no growth overlay for financials
