"""Historical valuation multiples, point-in-time.

For each quarter, trailing-twelve-month fundamentals become known on that quarter's filing date. The
multiple for that date uses the closing price on the filing date. The result is a series with no
look-ahead that can be compared with today's multiple (mean ± 1σ bands, z-scores).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from engine.data.prices import price_on_or_before
from engine.fundamentals.statements import Financials

MULTIPLES = ("pe", "ev_ebitda", "ev_sales", "p_fcf", "p_b", "p_ffo", "p_tbv")


@dataclass
class MultiplePoint:
    date: str
    values: dict[str, float | None]


def _ttm(quarters, i: int, key: str) -> float | None:
    if i < 3:
        return None
    vals = [quarters[j].values.get(key) for j in range(i - 3, i + 1)]
    if any(v is None for v in vals):
        return None
    return float(sum(vals))


def multiple_history(fin: Financials, prices: pd.DataFrame) -> list[MultiplePoint]:
    q = fin.quarterly
    out: list[MultiplePoint] = []
    for i in range(3, len(q)):
        p = q[i]
        if not p.filed:
            continue
        filed = max(p.filed.values())
        price = price_on_or_before(prices, filed)
        shares = p.values.get("shares_diluted")
        if price is None or not shares:
            continue
        mcap = price * shares
        ni = _ttm(q, i, "net_income")
        rev = _ttm(q, i, "revenue")
        ebitda = _ttm(q, i, "ebitda")
        fcf = _ttm(q, i, "fcf")
        dna = _ttm(q, i, "dna")
        gains = _ttm(q, i, "gain_on_sale_re") or 0.0
        nd = p.values.get("net_debt")
        ev = mcap + nd if nd is not None else None
        eq = p.values.get("equity")
        te = p.values.get("tangible_equity")
        ffo = (ni + dna - gains) if (ni is not None and dna is not None) else None
        vals = {
            "pe": mcap / ni if (ni and ni > 0) else None,
            "ev_ebitda": ev / ebitda if (ev is not None and ebitda and ebitda > 0) else None,
            "ev_sales": ev / rev if (ev is not None and rev and rev > 0) else None,
            "p_fcf": mcap / fcf if (fcf and fcf > 0) else None,
            "p_b": mcap / eq if (eq and eq > 0) else None,
            "p_ffo": mcap / ffo if (ffo and ffo > 0) else None,
            "p_tbv": mcap / te if (te and te > 0) else None,
        }
        out.append(MultiplePoint(filed.isoformat(), vals))
    return out


def band_stats(history: list[MultiplePoint], key: str, years: int, as_of) -> dict | None:
    cutoff = pd.Timestamp(as_of) - pd.DateOffset(years=years)
    vals = [
        h.values[key] for h in history if h.values.get(key) is not None and pd.Timestamp(h.date) >= cutoff
    ]
    if len(vals) < 8:
        return None
    arr = np.array(vals, dtype=float)
    # winsorize the history at the 5th/95th percentiles so one extreme quarter doesn't dominate the band
    lo, hi = np.percentile(arr, [5, 95])
    arr = np.clip(arr, lo, hi)
    return {
        "mean": float(arr.mean()),
        "std": float(arr.std(ddof=1)),
        "median": float(np.median(arr)),
        "n": int(len(arr)),
    }


def zscore(current: float | None, stats: dict | None) -> float | None:
    if current is None or stats is None or stats["std"] <= 0:
        return None
    return (current - stats["mean"]) / stats["std"]
