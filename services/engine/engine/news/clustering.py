"""Deduplicating news into story clusters.

Two items are the same story when they share a URL, or when their normalized headlines are similar enough
(Jaccard similarity of word sets, stop words and outlet names removed) and were published within a window of each
other. Items are grouped greedily in time order; a cluster's representative is its earliest item from the most
reliable source.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from engine.providers.models import NewsItem

_STOP = set(
    [
        "a",
        "an",
        "the",
        "and",
        "or",
        "of",
        "to",
        "in",
        "on",
        "for",
        "with",
        "by",
        "at",
        "from",
        "as",
        "is",
        "are",
        "was",
        "be",
        "its",
        "it",
        "this",
        "that",
        "after",
        "amid",
        "over",
        "into",
        "new",
        "says",
        "said",
        "report",
        "reports",
        "reported",
        "update",
        "updates",
        "synthetic",
    ]
)
_TOKEN = re.compile(r"[a-z0-9]+")


def normalize(headline: str, outlets: tuple[str, ...] = ()) -> frozenset[str]:
    h = headline.lower()
    h = re.sub(r"^\[[^\]]*\]\s*", "", h)  # "[Synthetic] ..." style prefixes
    for o in outlets:
        h = h.replace(o.lower(), " ")
    return frozenset(t for t in _TOKEN.findall(h) if t not in _STOP and len(t) > 1)


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _canon_url(u: str) -> str:
    u = re.sub(r"^https?://(www\.)?", "", u.strip().lower())
    return u.split("?")[0].split("#")[0].rstrip("/")


@dataclass
class Cluster:
    id: str
    items: list[NewsItem] = field(default_factory=list)
    tokens: frozenset[str] = frozenset()

    @property
    def first_seen(self) -> datetime:
        return min(i.published_at for i in self.items)

    @property
    def sources(self) -> list[str]:
        return sorted({i.source_name or i.provider for i in self.items})


def cluster(items: list[NewsItem], window_hours: float, threshold: float, reliability) -> list[Cluster]:
    """reliability(source_name) -> 0..1, used only to pick each cluster's representative."""
    outlets = tuple(sorted({i.source_name for i in items if i.source_name}, key=len, reverse=True))
    seen_urls: dict[str, Cluster] = {}
    clusters: list[Cluster] = []
    window = timedelta(hours=window_hours)
    for it in sorted(items, key=lambda i: i.published_at):
        cu = _canon_url(it.url)
        if cu in seen_urls:
            seen_urls[cu].items.append(it)
            continue
        toks = normalize(it.headline, outlets)
        best, best_sim = None, 0.0
        for c in reversed(clusters):
            if it.published_at - c.first_seen > window:
                break
            sim = jaccard(toks, c.tokens)
            if sim > best_sim:
                best, best_sim = c, sim
        if best is not None and best_sim >= threshold:
            best.items.append(it)
            best.tokens = best.tokens | toks
        else:
            cid = hashlib.sha1(f"{it.ticker}|{cu}".encode()).hexdigest()[:12]
            best = Cluster(cid, [it], toks)
            clusters.append(best)
            # keep clusters ordered by first_seen for the window scan
        seen_urls[cu] = best
    for c in clusters:
        c.items.sort(key=lambda i: (-reliability(i.source_name), i.published_at))
    return clusters
