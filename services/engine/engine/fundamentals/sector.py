"""Sector and analysis-profile detection from SEC SIC codes (GICS is proprietary)."""

from __future__ import annotations

from dataclasses import dataclass

from engine.config import Config, get_config


@dataclass
class SectorInfo:
    sic: int | None
    sic_description: str | None
    sector: str
    sector_label: str
    base_profile: str  # from SIC
    profile: str  # after overlays (growth_unprofitable, biotech_pipeline)
    profile_label: str
    overlay_reason: str | None
    is_financial: bool
    method_note: str


def sector_for_sic(sic: int | None, cfg: Config | None = None) -> str:
    cfg = cfg or get_config()
    if sic is None:
        return cfg["sectors.default_sector"]
    for rule in cfg["sectors.sic_rules"]:
        lo, hi = rule["range"]
        if lo <= sic <= hi:
            return rule["sector"]
    return cfg["sectors.default_sector"]


def profile_for_sic(sic: int | None, cfg: Config | None = None) -> str:
    cfg = cfg or get_config()
    if sic is None:
        return cfg["sectors.default_profile"]
    for rule in cfg["sectors.profile_rules"]:
        if "sic" in rule and sic in rule["sic"]:
            return rule["profile"]
        if "sic_range" in rule and rule["sic_range"][0] <= sic <= rule["sic_range"][1]:
            return rule["profile"]
    return cfg["sectors.default_profile"]


def detect(
    sic: int | None,
    sic_description: str | None,
    ttm_revenue: float | None,
    ttm_operating_margin: float | None,
    revenue_growth: float | None,
    rnd_to_revenue: float | None,
    cfg: Config | None = None,
) -> SectorInfo:
    cfg = cfg or get_config()
    sector = sector_for_sic(sic, cfg)
    base = profile_for_sic(sic, cfg)
    profile, reason = base, None
    financial = base in ("bank", "insurer", "reit", "financial_other")
    if base == "biotech":
        bp = cfg["sectors.biotech_pipeline"]
        small_rev = ttm_revenue is None or ttm_revenue < bp["max_revenue_usd"]
        heavy_rnd = rnd_to_revenue is not None and rnd_to_revenue >= bp["min_rnd_to_revenue"]
        if small_rev or heavy_rnd:
            profile = "biotech_pipeline"
            reason = (
                "revenue is small relative to research spending, so value depends mainly on the drug pipeline"
            )
    if not financial and profile in ("general", "software", "retail", "energy", "biotech"):
        gu = cfg["sectors.growth_unprofitable"]
        if (
            ttm_operating_margin is not None
            and ttm_operating_margin <= gu["max_ttm_operating_margin"]
            and revenue_growth is not None
            and revenue_growth >= gu["min_revenue_growth"]
        ):
            profile = "growth_unprofitable"
            reason = (
                "operating income is negative while revenue is growing quickly, so earnings-based "
                "valuation is not meaningful"
            )
    labels = cfg["sectors.labels"]
    plabels = cfg["sectors.profile_labels"]
    return SectorInfo(
        sic=sic,
        sic_description=sic_description,
        sector=sector,
        sector_label=labels.get(sector, sector),
        base_profile=base,
        profile=profile,
        profile_label=plabels.get(profile, profile),
        overlay_reason=reason,
        is_financial=financial,
        method_note="Sector approximated from the SEC SIC code (GICS classifications are proprietary).",
    )
