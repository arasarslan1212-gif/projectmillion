"""Normalizing broker rating vocabularies to +1 (buy), 0 (hold), -1 (sell)."""

from __future__ import annotations

BUY = {
    "buy",
    "strong buy",
    "outperform",
    "overweight",
    "accumulate",
    "positive",
    "add",
    "sector outperform",
    "market outperform",
    "top pick",
    "conviction buy",
    "long-term buy",
    "moderate buy",
    "speculative buy",
    "outperformer",
    "above average",
    "buy (high risk)",
}
HOLD = {
    "hold",
    "neutral",
    "equal-weight",
    "equal weight",
    "market perform",
    "sector perform",
    "peer perform",
    "in-line",
    "in line",
    "sector weight",
    "mixed",
    "market weight",
    "perform",
    "average",
    "fair value",
    "neutral weight",
}
SELL = {
    "sell",
    "strong sell",
    "underperform",
    "underweight",
    "reduce",
    "negative",
    "sector underperform",
    "market underperform",
    "below average",
    "underperformer",
}


def normalize_rating(rating: str | None) -> int | None:
    if not rating:
        return None
    r = rating.strip().lower()
    if r in BUY:
        return 1
    if r in HOLD:
        return 0
    if r in SELL:
        return -1
    if "buy" in r or "outperform" in r or "overweight" in r:
        return 1
    if "sell" in r or "underperform" in r or "underweight" in r:
        return -1
    if "hold" in r or "neutral" in r or "perform" in r or "weight" in r:
        return 0
    return None


def rating_label(norm: int | None) -> str:
    return {1: "Buy", 0: "Hold", -1: "Sell"}.get(norm, "Unrated") if norm is not None else "Unrated"
