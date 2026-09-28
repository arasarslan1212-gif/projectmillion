"""The number validator: every number in LLM-written text must come from the facts it was given.

Numbers are extracted with their form (percent, money, multiple, basis points or plain) and the scale they were
written in (K/M/B/T). A text number matches a fact when it equals the fact's value rounded to the precision the
text shows: "12.3%" matches 0.12345, "$1.2B" matches 1.23e9, "0.4" matches 0.4123. Numbers that appear inside a
fact's own text (a quoted headline, a label, a date) are allowed too, since quoting them is not inventing.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

_SCALE = {
    "k": 1e3, "thousand": 1e3,
    "m": 1e6, "mn": 1e6, "million": 1e6,
    "b": 1e9, "bn": 1e9, "billion": 1e9,
    "t": 1e12, "tn": 1e12, "trillion": 1e12,
}  # fmt: skip

_NUM = re.compile(
    r"(?P<sign>[-+−–])?(?P<cur>\$)?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?:\s?(?P<scale>thousand|million|billion|trillion|mn|bn|tn|[kKmMbBtT])(?![A-Za-z]))?"
    r"(?:\s?(?P<unit>%|×|x(?![A-Za-z])|pp(?![A-Za-z])|percentage points?|bps|basis points))?",
)


@dataclass
class Num:
    raw: str
    value: float  # natural units: "12.5%" -> 12.5 (kind pct), "$1.2B" -> 1.2e9
    kind: str  # pct | bps | multiple | money | plain
    decimals: int  # decimals as written (in the written scale)
    scale: float  # 1, 1e3, 1e6, 1e9 or 1e12 as written


def extract_numbers(text: str) -> list[Num]:
    out = []
    for mt in _NUM.finditer(text):
        start, end = mt.start("num"), mt.end("num")
        if start > 0 and (text[start - 1].isalpha() or text[start - 1] in "_"):
            continue  # part of a token such as "Q2" or "FY2026"
        if end < len(text) and text[end].isalpha() and not mt.group("scale") and not mt.group("unit"):
            continue  # "2nd", "10-K" style tokens
        num = mt.group("num")
        dec = len(num.split(".")[1]) if "." in num else 0
        scale = _SCALE.get((mt.group("scale") or "").lower(), 1.0)
        v = float(num.replace(",", "")) * scale
        unit = (mt.group("unit") or "").lower()
        sign = mt.group("sign")
        # a leading hyphen is only a minus sign when it cannot be a range/compound dash ("7-day")
        if sign in ("−", "–") or (sign == "-" and (start < 2 or not text[start - 2].isalnum())):
            v = -v
        kind = (
            "pct" if unit in ("%", "pp") or unit.startswith("percentage")
            else "bps" if unit in ("bps", "basis points")
            else "multiple" if unit in ("x", "×")
            else "money" if mt.group("cur")
            else "plain"
        )  # fmt: skip
        out.append(Num(mt.group(0).strip(), v, kind, dec, scale))
    return out


def _consistent(written: float, decimals: int, scale: float, target: float) -> bool:
    """Is `written` what `target` looks like when rounded to `decimals` places at `scale`? Sign-insensitive,
    because prose often carries the sign in words ("fell 3%")."""
    tol = 0.5 * 10 ** (-decimals) * scale
    return abs(abs(written) - abs(target)) <= tol * (1 + 1e-9) + 1e-12


def allowed_values(facts: list[dict]) -> list[tuple[float, str]]:
    """(value, unit) pairs from facts, plus every number that appears in a fact's text fields."""
    vals: list[tuple[float, str]] = []
    for f in facts:
        v = f.get("value")
        if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
            vals.append((float(v), f.get("unit", "plain")))
        for k in ("label", "text", "headline", "date", "period"):
            if isinstance(f.get(k), str):
                for n in extract_numbers(f[k]):
                    vals.append((n.value / 100, "pct") if n.kind == "pct" else (n.value, "plain"))
    return vals


def matches(n: Num, allowed: list[tuple[float, str]]) -> bool:
    for v, unit in allowed:
        pct_like = unit in ("pct", "prob")
        if n.kind == "pct":
            if _consistent(n.value, n.decimals, 1.0, v * 100 if pct_like else v):
                return True
        elif n.kind == "bps":
            if _consistent(n.value, n.decimals, 1.0, v * 1e4 if pct_like else v):
                return True
        elif _consistent(n.value, n.decimals, n.scale, v):
            return True
    return False


def unsupported_numbers(text: str, facts: list[dict], always_ok: tuple[float, ...] = ()) -> list[str]:
    """Numbers in `text` that no fact supports. `always_ok` whitelists structural plain numbers
    (for example the digest's 7- and 30-day windows)."""
    allowed = allowed_values(facts)
    bad = []
    for n in extract_numbers(text):
        if n.kind == "plain" and n.scale == 1.0 and any(abs(abs(n.value) - a) < 1e-9 for a in always_ok):
            continue
        if not matches(n, allowed):
            bad.append(n.raw)
    return bad
