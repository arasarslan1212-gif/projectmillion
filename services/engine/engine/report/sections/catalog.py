"""Ordered list of report sections. The web renders them in this order."""

from __future__ import annotations

from engine.report.sections import (
    chart,
    company,
    fundamentals,
    headline,
    overview,
    peers,
    risk,
    trust,
    valuation,
)

SECTIONS = [
    ("company", company.build),
    ("headline", headline.build),
    ("overview", overview.build),
    ("chart", chart.build),
    ("trust", trust.build),
    ("valuation", valuation.build),
    ("fundamentals", fundamentals.build),
    ("risk", risk.build),
    ("peers", peers.build),
]
