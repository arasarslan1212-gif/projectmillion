"""Ordered list of report sections. The web renders them in this order."""

from __future__ import annotations

from engine.report.sections import chart, company, fundamentals, overview, peers

SECTIONS = [
    ("company", company.build),
    ("overview", overview.build),
    ("chart", chart.build),
    ("fundamentals", fundamentals.build),
    ("peers", peers.build),
]
