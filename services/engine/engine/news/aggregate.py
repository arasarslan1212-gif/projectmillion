"""Sentiment over time, weighted by relevance, materiality, source reliability and breadth of coverage.

    weight(story) = relevance × materiality weight × source reliability × (1 + 0.25 ln(number of outlets))
    daily index(d) = Σ w·s·decay ÷ Σ w·decay over stories published on or before d, decay = 0.5^(age / half-life)
    window score   = Σ w·s ÷ Σ w over stories in the window (e.g. 30 days)

Stories flagged as possible manipulation get weight 0. Days with too little decayed weight show no value rather than
a number resting on one stray headline.
"""

from __future__ import annotations

import math
from datetime import date, timedelta


def story_weight(j: dict, reliability: float, n_sources: int, mat_w: dict) -> float:
    if j.get("suspicious"):
        return 0.0
    return (
        float(j["relevance"])
        * float(mat_w[j["materiality"]])
        * reliability
        * (1 + 0.25 * math.log(max(n_sources, 1)))
    )


def window_score(stories: list[dict], start: date, end: date) -> tuple[float | None, float, int]:
    """(score, total weight, number of stories) for stories dated in (start, end]."""
    sel = [s for s in stories if start < s["date"] <= end and s["weight"] > 0]
    tw = sum(s["weight"] for s in sel)
    if tw <= 0:
        return None, 0.0, len(sel)
    return sum(s["weight"] * s["sentiment"] for s in sel) / tw, tw, len(sel)


def daily_series(stories: list[dict], start: date, end: date, half_life: float, min_weight: float) -> dict:
    dates, vals, counts = [], [], []
    lam = math.log(2) / half_life
    by_day: dict[date, list[dict]] = {}
    for s in stories:
        by_day.setdefault(s["date"], []).append(s)
    num = den = 0.0
    d = start - timedelta(days=int(half_life * 6))
    while d <= end:
        num *= math.exp(-lam)
        den *= math.exp(-lam)
        todays = by_day.get(d, [])
        for s in todays:
            num += s["weight"] * s["sentiment"]
            den += s["weight"]
        if d >= start:
            dates.append(d.isoformat())
            vals.append(round(num / den, 4) if den >= min_weight else None)
            counts.append(len(todays))
        d += timedelta(days=1)
    return {"dates": dates, "sentiment": vals, "stories": counts}


def trend_label(recent: float | None, prior: float | None, threshold: float = 0.1) -> str:
    if recent is None or prior is None:
        return "not enough news to compare"
    diff = recent - prior
    if diff > threshold:
        return "improving"
    if diff < -threshold:
        return "deteriorating"
    return "stable"


def label(score: float | None) -> str | None:
    if score is None:
        return None
    if score >= 0.35:
        return "Positive"
    if score >= 0.1:
        return "Slightly positive"
    if score > -0.1:
        return "Neutral"
    if score > -0.35:
        return "Slightly negative"
    return "Negative"
