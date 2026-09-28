"""The number contract between engine and web: every figure is a Metric dict.

The web never computes numbers; it formats `value` according to `unit` and shows the tooltip from
the definitions registry (`def`) plus `source` and `as_of`.
"""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any


def _clean(v: Any) -> Any:
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    if hasattr(v, "item"):
        v = v.item()
    return v


def metric(
    id: str,
    label: str,
    value: float | int | None,
    unit: str,
    *,
    source: str | None = None,
    as_of: date | datetime | str | None = None,
    reason: str | None = None,
    def_id: str | None = None,
    note: str | None = None,
    extra: dict | None = None,
) -> dict:
    """unit: usd | usd_per_share | pct | ratio | x | count | score | days | years | text | date | shares."""
    v = _clean(value)
    status = "ok" if v is not None else "insufficient_data"
    if isinstance(as_of, (date, datetime)):
        as_of = as_of.isoformat()
    out = {
        "id": id,
        "label": label,
        "value": v,
        "unit": unit,
        "status": status,
        "reason": reason if v is None else None,
        "source": source,
        "as_of": as_of,
        "def": def_id or id,
    }
    if note:
        out["note"] = note
    if extra:
        out.update(extra)
    return out


def missing(id: str, label: str, unit: str, reason: str, **kw) -> dict:
    return metric(id, label, None, unit, reason=reason, **kw)


def safe_div(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b == 0:
        return None
    try:
        r = a / b
    except ZeroDivisionError:
        return None
    return None if (isinstance(r, float) and (math.isnan(r) or math.isinf(r))) else r


def section(
    name: str, *, status: str = "ok", reason: str | None = None, sources: list[dict] | None = None, **body
) -> dict:
    return {"section": name, "status": status, "reason": reason, "sources": sources or [], **body}
