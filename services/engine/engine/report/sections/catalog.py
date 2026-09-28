"""Ordered list of report sections. The web renders them in this order."""

from __future__ import annotations

from engine.report.sections import chart, company

SECTIONS = [
    ("company", company.build),
    ("chart", chart.build),
]
