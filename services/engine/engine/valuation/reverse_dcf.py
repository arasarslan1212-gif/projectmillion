"""Reverse DCF: the growth rate the current price implies.

Solves for a constant annual free-cash-flow growth rate over the explicit horizon (then the configured
terminal growth) such that the discounted value equals today's enterprise value. When trailing FCF is
not positive, it instead solves for the near-term revenue growth in the full DCF model.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
from scipy.optimize import brentq

from engine.valuation.dcf import DcfInputs, run_dcf


def pv_constant_growth(
    fcf0: float, g: float, wacc: float, g_t: float, years: int, mid_year: bool = True
) -> float:
    t = np.arange(1, years + 1, dtype=float)
    fcf = fcf0 * (1 + g) ** t
    expo = t - 0.5 if mid_year else t
    pv = float(np.sum(fcf * (1 + wacc) ** (-expo)))
    tv = fcf[-1] * (1 + g_t) / (wacc - g_t)
    return pv + tv * (1 + wacc) ** (-years)


def implied_fcf_growth(fcf0: float, target_ev: float, wacc: float, g_t: float, years: int) -> float | None:
    if fcf0 <= 0 or target_ev <= 0 or wacc <= g_t:
        return None
    f = lambda g: pv_constant_growth(fcf0, g, wacc, g_t, years) - target_ev  # noqa: E731
    lo, hi = -0.5, 1.0
    if f(lo) > 0 or f(hi) < 0:
        return None
    return float(brentq(f, lo, hi, xtol=1e-7))


def implied_revenue_growth(inp: DcfInputs, target_per_share: float) -> float | None:
    def f(g: float) -> float:
        return (run_dcf(replace(inp, growth1=g)).per_share or 0.0) - target_per_share

    lo, hi = -0.3, 1.2
    try:
        if f(lo) > 0 or f(hi) < 0:
            return None
        return float(brentq(f, lo, hi, xtol=1e-6))
    except ValueError:
        return None


def assess(implied: float | None, history: float | None, consensus: float | None) -> str | None:
    """Label the implied growth against what the company has delivered and what analysts expect."""
    if implied is None:
        return None
    refs = [x for x in (history, consensus) if x is not None]
    if not refs:
        return "no history to compare"
    hi, lo = max(refs), min(refs)
    if implied > hi + 0.03:
        return "demanding"
    if implied < lo - 0.03:
        return "modest"
    return "in line with history and expectations"
