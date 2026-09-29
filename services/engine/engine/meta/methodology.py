"""The Methodology page, generated from the engine configuration.

Every parameter comes from config/engine.yaml as loaded by the engine (so the page cannot drift from what runs),
annotated with the comments written next to it in the file. Metric definitions come from config/metrics.yaml.
Only the short introductions below are prose; every number on the page is a configuration value.
"""

from __future__ import annotations

import re
from pathlib import Path

from engine import clock
from engine.config import ENGINE_VERSION, get_config, load_metric_defs
from engine.legal import DISCLAIMER_FULL

SECTIONS: list[tuple[str, str, str]] = [
    ("trust_rating", "Trust Rating",
     "Metrics are scored 0–100 against the company's SEC industry universe (or fixed anchors), averaged into ten "
     "pillars, and the pillars weighted by the company's profile. Red flags then deduct points."),
    ("red_flags", "Red flags",
     "Specific warning signs, each with a threshold and a deduction from the Trust Rating."),
    ("valuation", "Price target and valuation",
     "Several valuation methods, weighted by profile, applicability and measured accuracy. Each method's long-term "
     "value is converted to a 12-month figure; the weighted blend is P50, and the 80% range comes from market "
     "volatility plus disagreement between methods."),
    ("confidence", "Confidence",
     "How much the app trusts its own estimate: method agreement, data quality, predictability, volatility, analyst "
     "dispersion and the track record for similar stocks."),
    ("analysts", "Analyst Trust Scores",
     "Each analyst's past price targets and ratings are scored point-in-time against what the stock did, shrunk "
     "towards firm and sector averages when the record is short."),
    ("news", "News and sentiment",
     "Stories are deduplicated, classified, weighted by relevance, materiality and source reliability, and "
     "aggregated into 7- and 30-day scores."),
    ("earnings", "Earnings", "Windows for reactions, drift and estimate revisions."),
    ("dividends", "Dividend safety", "Components, weights and anchors of the dividend safety score."),
    ("ownership", "Ownership and insiders", "Look-back windows and the insider cluster rule."),
    ("capital", "Capital allocation scorecard",
     "How management used the cash the business produced: returns on new capital, buyback timing against the "
     "market, dilution, payouts against free cash flow and dividend safety. A separate section, not a Trust Rating "
     "pillar."),
    ("quant", "Quantitative views",
     "Factor exposures and macro sensitivity from weekly-return regressions, and month-of-year returns with a "
     "multiple-testing correction. Every estimate is shown with its t-statistic."),
    ("alerts", "Alerts",
     "What the daily alert job checks for the watchlist, and the thresholds it uses."),
    ("llm", "Language model use",
     "Where a language model writes text, what it may see, and the budget. Every number it writes is checked "
     "against the facts it cites; failures fall back to templates."),
    ("track", "Track record and calibration",
     "How snapshots are graded, when the track record feeds back into confidence and method weights, and the "
     "rules for applying a recalibration."),
    ("sectors", "Sectors and analysis profiles", "How SIC codes map to sectors and profiles."),
    ("peers", "Peers", "How peer groups are chosen."),
    ("pit", "Point-in-time rules", "Lags that keep past reports from seeing data published later."),
    ("benchmarks", "Benchmarks", "Market and sector reference series."),
    ("data", "Data freshness", "How long each kind of data is cached before it is fetched again."),
]  # fmt: skip

PRINCIPLES = [
    "Numbers come from tested code; a language model only writes words, and every number it writes is checked "
    "against the facts it cites.",
    "Every figure carries its source and as-of date. Missing data is shown as missing, never filled in.",
    "Uncertainty is part of the answer: every target is a range with a confidence level.",
    "Analysis is sector-aware (banks, insurers, REITs and utilities are valued differently) and point-in-time.",
    "The app grades itself: every report is stored and scored when its 12-month horizon passes.",
]

_KEY = re.compile(r"^(\s*)([A-Za-z0-9_]+):(.*)$")


def _split_comment(rest: str) -> tuple[str, str | None]:
    """Split `value  # comment`, ignoring '#' inside quotes."""
    q = None
    for i, ch in enumerate(rest):
        if ch in "\"'" and (q is None or q == ch):
            q = None if q == ch else ch
        elif ch == "#" and q is None and (i == 0 or rest[i - 1].isspace()):
            return rest[:i].rstrip(), rest[i + 1 :].strip()
    return rest.rstrip(), None


def comment_map(text: str) -> dict[str, str]:
    """Dotted key path -> the comment lines directly above it and its inline comment."""
    out: dict[str, str] = {}
    stack: list[tuple[int, str]] = []
    pending: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            c = s.lstrip("#").strip()
            if c and not set(c) <= set("-=_ "):
                pending.append(c)
            continue
        mt = _KEY.match(line)
        if not mt or s.startswith("-"):
            continue
        indent, key, rest = len(mt.group(1)), mt.group(2), mt.group(3)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        if indent == 0:
            pending = [p for p in pending if not p.lower().startswith(("engine configuration", "the hash"))]
        path = ".".join([k for _, k in stack] + [key])
        _, inline = _split_comment(rest)
        parts = [*pending, *([inline] if inline else [])]
        if parts:
            out[path] = " ".join(parts)
        pending = []
        stack.append((indent, key))
    return out


def _node(key: str, value, path: str, comments: dict[str, str]) -> dict:
    n = {"key": key, "path": path, "comment": comments.get(path)}
    if isinstance(value, dict):
        n["children"] = [_node(str(k), v, f"{path}.{k}", comments) for k, v in value.items()]
    else:
        n["value"] = value
    return n


def build() -> dict:
    cfg = get_config()
    text = Path(cfg.path).read_text() if getattr(cfg, "path", None) else ""
    comments = comment_map(text)
    raw = cfg.data
    sections = []
    for key, title, intro in SECTIONS:
        if key not in raw:
            continue
        sections.append({
            "id": key, "title": title, "intro": intro, "comment": comments.get(key),
            "params": _node(key, raw[key], key, comments)["children"] if isinstance(raw[key], dict) else [],
        })  # fmt: skip
    defs = load_metric_defs()
    glossary = sorted(
        ({"id": k, **v} for k, v in defs.items()), key=lambda d: str(d.get("label") or d["id"]).lower()
    )
    return {
        "engine_version": ENGINE_VERSION,
        "config_hash": cfg.hash,
        "config_version": raw.get("config_version"),
        "generated_at": clock.now().isoformat(),
        "principles": PRINCIPLES,
        "sections": sections,
        "glossary": glossary,
        "disclaimer": DISCLAIMER_FULL,
    }
