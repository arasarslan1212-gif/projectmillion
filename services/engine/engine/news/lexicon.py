"""Deterministic news classification: the fallback when the LLM is not configured, over budget, or fails.

It reads only the headline (and the provider's short teaser), so it is cruder than the LLM: sentiment comes from
finance word lists with simple negation, the event type from keyword rules, materiality from the event type and
the strength of the wording, and relevance from whether the company is named. It writes no summaries; the UI says
so rather than paraphrasing a headline and calling it a summary.

`injection_signals` is used on every path: text that addresses an AI system is flagged and excluded from sentiment.
"""

from __future__ import annotations

import math
import re

EVENT_TYPES = (
    "earnings", "guidance", "m&a", "legal_regulatory", "product", "management",
    "macro", "analyst_action", "capital_return", "other",
)  # fmt: skip

POSITIVE = {
    "beat", "beats", "tops", "topped", "exceeds", "exceeded", "surge", "surges", "surged", "soar", "soars", "jump",
    "jumps", "rally", "rallies", "record", "raise", "raises", "raised", "boost", "boosts", "upgrade", "upgrades",
    "upgraded", "strong", "stronger", "growth", "grows", "expands", "expansion", "wins", "won", "approval",
    "approved", "approves", "launch", "launches", "unveils", "breakthrough", "profit", "profitable", "gain", "gains",
    "outperform", "buyback", "repurchase", "accelerates", "robust", "higher", "improves", "improved", "settles",
    "resolves", "partnership", "award", "awarded", "optimistic", "upbeat", "rebound", "rebounds",
}  # fmt: skip
NEGATIVE = {
    "miss", "misses", "missed", "falls", "fell", "drop", "drops", "plunge", "plunges", "slump", "slumps", "tumble",
    "tumbles", "cut", "cuts", "trims", "lowers", "lowered", "downgrade", "downgrades", "downgraded", "weak", "weaker",
    "weakness", "softer", "slows", "slowdown", "loss", "losses", "lawsuit", "sues", "sued", "probe", "investigation",
    "investigates", "review", "fine", "fined", "penalty", "recall", "recalls", "fraud", "halt", "halts", "delay",
    "delays", "delayed", "warning", "warns", "layoffs", "resigns", "departs", "exits", "default", "bankruptcy",
    "decline", "declines", "declined", "lower", "concern", "concerns", "risk", "weighs", "pressure", "underperform",
    "sell", "dispute", "breach", "shortfall", "suspends", "suspended", "doubt", "restatement", "restate",
}  # fmt: skip
NEGATIONS = {"not", "no", "never", "without", "fails", "failed", "denies"}

# Checked in order; each key matches on word boundaries. Macro phrases come first so "rate outlook weighs on
# sector peers" is not read as company guidance.
_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("macro", ("rate outlook", "interest rates", "fed", "inflation", "tariffs?", "economy", "sector peers",
               "recession", "macro", "jobs report", "industry peers")),
    ("analyst_action", ("upgrades?", "downgrades?", "upgraded", "downgraded", "initiates coverage", "price target",
                        "reiterates", "overweight", "underweight", "outperform", "underperform", "coverage of",
                        "rating (buy|sell|hold|neutral|overweight|underweight|outperform|underperform)")),
    ("earnings", ("results", "earnings", "quarterly profit", "eps", "tops estimates", "misses estimates",
                  "beats estimates", "fiscal q[1-4]", "revenue (miss|beat)")),
    ("guidance", ("outlook", "guidance", "forecast", "full-year", "sees fy", "expects")),
    ("m&a", ("acquires?", "acquisition", "merger", "merge", "takeover", "to buy", "buyout", "divests?", "spin off",
             "spinoff", "stake in")),
    ("legal_regulatory", ("regulators?", "lawsuit", "sues", "probe", "investigation", "antitrust", "settles?",
                          "patent", "court", "sec", "doj", "ftc", "fined?", "penalty", "recalls?", "subpoena",
                          "review of", "fda", "approv(al|als|ed|es)")),
    ("capital_return", ("buyback", "repurchase", "dividend")),
    ("management", ("ceo", "cfo", "coo", "chief [a-z]+ officer", "names new", "appoints", "resigns", "steps down",
                    "board", "executive", "succession")),
    ("product", ("products?", "launch(es)?", "unveils", "introduces", "release", "offering", "platform",
                 "contract", "partnership", "expands")),
]  # fmt: skip
_RULE_RE = [(name, re.compile(r"\b(" + "|".join(keys) + r")\b")) for name, keys in _RULES]

_HIGH_WORDS = ("plunge", "soar", "surge", "record", "fraud", "bankruptcy", "halt", "restate", "going concern")
_INJECTION = re.compile(
    r"(ignore|disregard|forget)\s+(all\s+|any\s+|the\s+)?(previous|prior|above|earlier)?\s*(instructions|rules|prompts?)"
    r"|system\s*prompt|you\s+are\s+(an?\s+)?(ai|assistant|language model)|as an ai\b|^\s*(assistant|system)\s*:"
    r"|output\s+(a\s+)?sentiment|rate\s+this\s+(stock|company)|give\s+\w+\s+a\s+(trust|rating)",
    re.IGNORECASE | re.MULTILINE,
)
_WORD = re.compile(r"[a-z][a-z'&-]*")


def injection_signals(*texts: str | None) -> str | None:
    for t in texts:
        if t and (mt := _INJECTION.search(t)):
            return f"contains text addressed to an AI system (“{mt.group(0).strip()[:60]}”)"
    return None


def _strip(h: str) -> str:
    return re.sub(r"^\[[^\]]*\]\s*", "", h)


def sentiment(text: str) -> float:
    words = _WORD.findall(_strip(text).lower())
    score = 0.0
    for i, w in enumerate(words):
        s = 1.0 if w in POSITIVE else -1.0 if w in NEGATIVE else 0.0
        if s and any(x in NEGATIONS for x in words[max(0, i - 3) : i]):
            s = -s
        score += s
    return float(math.tanh(0.7 * score))


def event_type(text: str) -> str:
    t = _strip(text).lower()
    for name, rx in _RULE_RE:
        if rx.search(t):
            return name
    return "other"


def materiality(ev: str, text: str, sent: float) -> str:
    t = text.lower()
    if ev in ("earnings", "guidance", "m&a") or any(w in t for w in _HIGH_WORDS):
        return "high"
    if ev == "legal_regulatory" and sent < -0.3:
        return "high"
    if ev in ("legal_regulatory", "management", "capital_return", "analyst_action", "product"):
        return "medium"
    return "low"


def relevance(text: str, ticker: str, names: list[str]) -> float:
    t = _strip(text).lower()
    if re.search(rf"\b{re.escape(ticker.lower())}\b", t) or any(n and n.lower() in t for n in names):
        return 0.6 if any(k in t for k in ("peers", "sector", "industry", "rivals")) else 1.0
    return 0.3


def classify(headline: str, teaser: str | None, ticker: str, names: list[str]) -> dict:
    text = headline if not teaser else f"{headline}. {teaser}"
    ev = event_type(headline)
    s = sentiment(headline)
    return {
        "summary": None,
        "sentiment": round(s, 3),
        "relevance": relevance(headline, ticker, names),
        "materiality": materiality(ev, text, s),
        "event_type": ev,
        "suspicious": False,
    }
