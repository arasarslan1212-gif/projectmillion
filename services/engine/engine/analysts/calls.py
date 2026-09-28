"""Turn raw analyst records into normalized calls.

A *call* is one analyst (or firm) publishing a price target and/or a rating on a stock on a date.

Provider shapes differ:
- FMP `price-target-news` carries the analyst's name and target but no rating, while FMP `grades` carries
  the firm's rating but no analyst. A target is joined to a grade from the same firm within ± a few days.
- Benzinga (via Massive) carries analyst, rating and target in one record.
- Grades that match no target stay as firm-level calls (rating only).

Published targets are in the share units of their date; they are split-adjusted to today's units so they
compare with split-adjusted prices.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

from engine.analysts.ratings import normalize_rating, rating_label


@dataclass
class Call:
    ticker: str
    date: date
    firm: str
    analyst_key: str | None
    analyst_name: str | None
    target: float | None  # split-adjusted to current share units
    target_raw: float | None
    rating: str | None
    rating_norm: int | None
    rating_source: str | None  # reported | carried | None
    action: str  # initiation | upgrade | downgrade | reiteration
    target_prior: float | None = None  # this analyst's previous target on this stock (split-adjusted)
    rating_prior: str | None = None
    url: str | None = None
    headline: str | None = None
    source: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def who(self) -> str:
        """Identity used for 'latest call per analyst': the analyst when known, else the firm."""
        return self.analyst_key or f"firm:{self.firm.strip().lower()}"

    @property
    def target_change(self) -> float | None:
        if self.target is None or not self.target_prior:
            return None
        return self.target / self.target_prior - 1


def normalize_action(action: str | None) -> str | None:
    if not action:
        return None
    a = action.strip().lower()
    if "terminat" in a or "suspend" in a or "drop" in a:
        return "termination"
    if a.startswith("init") or "initiat" in a or "coverage" in a or a.startswith("assum"):
        return "initiation"
    if "upgrade" in a or a == "up":
        return "upgrade"
    if "downgrade" in a or a == "down":
        return "downgrade"
    if a in ("maintain", "maintains", "reiterate", "reiterates", "reiterated", "hold", "main", "target"):
        return "reiteration"
    if "raise" in a or "lower" in a or "cut" in a or "adjust" in a:
        return "reiteration"
    return None


def split_factor_after(splits: list[tuple[date, float]], d: date) -> float:
    """Product of split ratios effective after `d` (a 4-for-1 split after d gives 4)."""
    f = 1.0
    for sd, ratio in splits:
        if sd > d and ratio > 0:
            f *= ratio
    return f


def _norm_key(firm: str) -> str:
    return " ".join(firm.lower().replace(",", " ").replace(".", " ").split())


def build_calls(
    records: list[dict],
    splits: dict[str, list[tuple[date, float]]],
    join_days: int = 3,
    rating_stale_days: int = 365,
) -> list[Call]:
    """records: dicts with ticker, date, firm, analyst_key, analyst_name, target, target_prior, rating,
    rating_prior, action, url, headline, source (the persisted analyst_actions rows)."""
    by_ticker: dict[str, list[dict]] = {}
    for r in records:
        by_ticker.setdefault(r["ticker"].upper(), []).append(r)
    out: list[Call] = []
    for ticker, rows in by_ticker.items():
        sp = splits.get(ticker, [])
        targets = [r for r in rows if r.get("target") is not None]
        grades = [r for r in rows if r.get("target") is None and r.get("rating")]
        grades_by_firm: dict[str, list[dict]] = {}
        for g in grades:
            grades_by_firm.setdefault(_norm_key(g["firm"]), []).append(g)
        used: set[int] = set()
        calls: list[Call] = []
        for r in sorted(targets, key=lambda x: x["date"]):
            rating, rating_prior, action = (
                r.get("rating"),
                r.get("rating_prior"),
                normalize_action(r.get("action")),
            )
            if not rating:
                cands = [
                    g
                    for g in grades_by_firm.get(_norm_key(r["firm"]), [])
                    if abs((g["date"] - r["date"]).days) <= join_days
                ]
                if cands:
                    g = min(cands, key=lambda g: (abs((g["date"] - r["date"]).days), id(g) in used))
                    used.add(id(g))
                    rating, rating_prior = g.get("rating"), g.get("rating_prior")
                    action = normalize_action(g.get("action")) or action
            f = split_factor_after(sp, r["date"])
            calls.append(
                Call(
                    ticker=ticker,
                    date=r["date"],
                    firm=r["firm"],
                    analyst_key=r.get("analyst_key"),
                    analyst_name=r.get("analyst_name"),
                    target=r["target"] / f,
                    target_raw=r["target"],
                    rating=rating,
                    rating_norm=normalize_rating(rating),
                    rating_source="reported" if rating else None,
                    action=action or "",
                    rating_prior=rating_prior,
                    url=r.get("url"),
                    headline=r.get("headline"),
                    source=r.get("source", ""),
                )
            )
        for g in grades:
            if id(g) in used:
                continue
            calls.append(
                Call(
                    ticker=ticker,
                    date=g["date"],
                    firm=g["firm"],
                    analyst_key=None,
                    analyst_name=None,
                    target=None,
                    target_raw=None,
                    rating=g["rating"],
                    rating_norm=normalize_rating(g["rating"]),
                    rating_source="reported",
                    action=normalize_action(g.get("action")) or "",
                    rating_prior=g.get("rating_prior"),
                    url=g.get("url"),
                    headline=g.get("headline"),
                    source=g.get("source", ""),
                )
            )
        out.extend(_sequence(calls, rating_stale_days))
    out.sort(key=lambda c: (c.date, c.ticker, c.firm))
    return out


def _sequence(calls: list[Call], rating_stale_days: int) -> list[Call]:
    """Per analyst (or firm) and stock: prior target, carried-forward rating, and the action type."""
    calls = sorted(calls, key=lambda c: c.date)
    last: dict[str, Call] = {}
    out = []
    for c in calls:
        prev = last.get(c.who)
        if prev is not None:
            if c.target is not None and prev.target is not None:
                c = replace(c, target_prior=prev.target)
            if (
                c.rating is None
                and prev.rating is not None
                and (c.date - prev.date).days <= rating_stale_days
            ):
                c = replace(c, rating=prev.rating, rating_norm=prev.rating_norm, rating_source="carried")
            if c.rating_prior is None and prev.rating is not None:
                c = replace(c, rating_prior=prev.rating)
        if not c.action:
            if prev is None:
                action = "initiation"
            elif (
                c.rating_norm is not None
                and prev.rating_norm is not None
                and c.rating_norm != prev.rating_norm
            ):
                action = "upgrade" if c.rating_norm > prev.rating_norm else "downgrade"
            else:
                action = "reiteration"
            c = replace(c, action=action)
        last[c.who] = c
        out.append(c)
    return out


def direction(c: Call, price: float | None, threshold: float) -> tuple[int, str]:
    """+1 bullish, −1 bearish, 0 neutral; the rating wins, else the target's implied move."""
    if c.rating_norm is not None:
        return c.rating_norm, "rating"
    if c.target is not None and price:
        up = c.target / price - 1
        if up >= threshold:
            return 1, "implied by target"
        if up <= -threshold:
            return -1, "implied by target"
        return 0, "implied by target"
    return 0, "none"


def label_for(c: Call) -> str:
    return c.rating or rating_label(c.rating_norm)
