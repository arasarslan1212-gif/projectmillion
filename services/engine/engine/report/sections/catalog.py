"""Ordered list of report sections. The web renders them in this order."""

from __future__ import annotations

from engine.report.sections import (
    analysts,
    chart,
    company,
    fundamentals,
    headline,
    news,
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
    ("analysts", analysts.build),
    ("news", news.build),
    ("fundamentals", fundamentals.build),
    ("risk", risk.build),
    ("peers", peers.build),
]
