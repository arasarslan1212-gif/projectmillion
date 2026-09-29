"""What changed in the Risk Factors section (Item 1A) between the last two 10-Ks.

Each risk factor is a paragraph of Item 1A. Paragraphs are matched across the two filings by word overlap (Jaccard
similarity of their word sets): a match at or above `same` is the same risk, below `reworded` it counts as reworded,
and unmatched paragraphs are added or removed. Only each risk's first sentence is shown (a short quotation with a
link to the filing), never the full text.
"""

from __future__ import annotations

import re

from engine.report.context import ReportContext

ITEM_1A = re.compile(r"item\s*1a\.?\s*[:\-–—]?\s*risk\s+factors", re.I)
NEXT_ITEM = re.compile(r"item\s*(1b|1c|2|3|7)\.?\s*[:\-–—]?\s*[a-z]", re.I)
WORD = re.compile(r"[a-z][a-z'-]{2,}")
STOP = frozenset({
    "the", "and", "for", "are", "our", "may", "could", "would", "with", "that", "this", "from", "have", "has", "not",
    "its", "any", "such", "other",
})  # fmt: skip


def risk_section(text: str) -> str | None:
    """Item 1A text. A table of contents also names Item 1A, so the longest candidate section wins."""
    best = None
    for m in ITEM_1A.finditer(text):
        nxt = NEXT_ITEM.search(text, m.end())
        seg = text[m.end() : nxt.start() if nxt else len(text)]
        if best is None or len(seg) > len(best):
            best = seg
    return best.strip() if best and len(best.split()) >= 20 else None


def risk_units(section: str) -> list[dict]:
    paras = [re.sub(r"\s+", " ", p).strip() for p in re.split(r"\n\s*\n|\n", section)]
    out = []
    for p in paras:
        if len(p) < 40:
            continue
        words = frozenset(w for w in WORD.findall(p.lower()) if w not in STOP)
        if len(words) < 5:
            continue
        first = re.split(r"(?<=[.!?])\s", p, maxsplit=1)[0]
        title = first if len(first) <= 200 else first[:197].rsplit(" ", 1)[0] + "…"
        out.append({"title": title, "words": words, "n_words": len(p.split())})
    return out


def _jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if a or b else 0.0


def diff_units(prev: list[dict], cur: list[dict], same: float = 0.9, match: float = 0.5) -> dict:
    used: set[int] = set()
    added, reworded = [], []
    for u in cur:
        best, j_best = None, 0.0
        for j, p in enumerate(prev):
            if j in used:
                continue
            s = _jaccard(u["words"], p["words"])
            if s > j_best:
                best, j_best = j, s
        if best is not None and j_best >= match:
            used.add(best)
            if j_best < same:
                reworded.append({"title": u["title"], "similarity": round(j_best, 2)})
        else:
            added.append({"title": u["title"]})
    removed = [{"title": p["title"]} for j, p in enumerate(prev) if j not in used]
    return {"added": added, "removed": removed, "reworded": reworded}


def risk_factor_changes(ctx: ReportContext) -> dict:
    tenks = [f for f in ctx.filings if f.form in ("10-K", "10-K405")]
    if len(tenks) < 2:
        return {"status": "missing", "reason": "fewer than two 10-K filings to compare"}
    cur_f, prev_f = tenks[-1], tenks[-2]
    texts = []
    for f in (prev_f, cur_f):
        fx = ctx.data.document_text(f)
        if fx.value is None:
            return {"status": "missing", "reason": f"10-K text unavailable ({fx.reason})"}
        sec = risk_section(fx.value)
        if sec is None:
            return {
                "status": "missing",
                "reason": f"no Risk Factors section found in the 10-K filed {f.filed_at}",
            }
        texts.append(sec)
    prev_u, cur_u = risk_units(texts[0]), risk_units(texts[1])
    d = diff_units(prev_u, cur_u)
    return {
        "status": "ok",
        "latest": {"filed": cur_f.filed_at.isoformat(), "url": cur_f.url, "n_risks": len(cur_u),
                   "n_words": sum(u["n_words"] for u in cur_u)},
        "previous": {"filed": prev_f.filed_at.isoformat(), "url": prev_f.url, "n_risks": len(prev_u),
                     "n_words": sum(u["n_words"] for u in prev_u)},
        **d,
        "method": "Paragraphs of Item 1A matched by word overlap; first sentences quoted, full text at the links.",
    }  # fmt: skip
