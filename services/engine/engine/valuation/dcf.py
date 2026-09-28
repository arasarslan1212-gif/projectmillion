"""Free-cash-flow-to-the-firm DCF, vectorized so the same code runs one scenario or 10,000 Monte Carlo draws.

Per year t = 1..N:
    revenue_t   = revenue_{t-1} × (1 + g_t), with g_t fading linearly from g1 to the terminal growth g_T
    margin_t    = m0 + (m_target − m0) × min(t / M, 1)                 (EBIT margin; GAAP EBIT already deducts SBC)
    NOPAT_t     = EBIT_t × (1 − tax_t)   (no tax on losses)
    reinvest_t  = (capex% − D&A%) × revenue_t + NWC% × (revenue_t − revenue_{t-1})
    FCFF_t      = NOPAT_t − reinvest_t
Terminal value (at year N): FCFF_{N+1} / (WACC − g_T), where FCFF_{N+1} = NOPAT_{N+1} × (1 − g_T / ROIC_T) and
ROIC_T = WACC + spread, so terminal reinvestment is consistent with terminal growth.
Enterprise value = Σ PV(FCFF_t) (mid-year discounting) + PV(TV). Equity = EV − debt + cash − minorities − pension deficit.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace

import numpy as np


@dataclass(frozen=True)
class DcfInputs:
    revenue0: float
    margin0: float  # current EBIT margin
    margin_target: float
    growth1: float  # first-year revenue growth
    terminal_growth: float
    wacc: float
    tax0: float
    tax_terminal: float
    dna_pct: float
    capex_pct: float
    nwc_pct: float
    debt: float
    cash: float
    minority: float
    pension_deficit: float
    shares: float
    years: int = 10
    margin_years: int = 5
    terminal_roic_spread: float = 0.02
    mid_year: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DcfResult:
    per_share: float | None
    enterprise_value: float
    equity_value: float
    pv_explicit: float
    pv_terminal: float
    terminal_share: float
    table: list[dict]
    notes: list[str]


def _paths(inp: DcfInputs, g1: np.ndarray, mt: np.ndarray, wacc: np.ndarray, gT: np.ndarray):
    n = inp.years
    t = np.arange(1, n + 1, dtype=float)
    frac = (t - 1) / max(n - 1, 1)
    g = g1[:, None] + (gT[:, None] - g1[:, None]) * frac[None, :]
    rev = inp.revenue0 * np.cumprod(1.0 + g, axis=1)
    rev_prev = np.concatenate([np.full((len(g1), 1), inp.revenue0), rev[:, :-1]], axis=1)
    mfrac = np.minimum(t / max(inp.margin_years, 1), 1.0)
    margin = inp.margin0 + (mt[:, None] - inp.margin0) * mfrac[None, :]
    ebit = rev * margin
    tax = inp.tax0 + (inp.tax_terminal - inp.tax0) * np.minimum(t / 5.0, 1.0)
    nopat = np.where(ebit > 0, ebit * (1.0 - tax[None, :]), ebit)
    reinvest = (inp.capex_pct - inp.dna_pct) * rev + inp.nwc_pct * (rev - rev_prev)
    fcff = nopat - reinvest
    expo = t - 0.5 if inp.mid_year else t
    df = (1.0 + wacc[:, None]) ** (-expo[None, :])
    pv = fcff * df
    roic_t = wacc + inp.terminal_roic_spread
    nopat_next = nopat[:, -1] * (1.0 + gT)
    fcff_next = np.where(nopat_next > 0, nopat_next * (1.0 - gT / roic_t), nopat_next)
    tv = fcff_next / (wacc - gT)
    pv_tv = tv * (1.0 + wacc) ** (-float(n))
    ev = pv.sum(axis=1) + pv_tv
    equity = ev - inp.debt + inp.cash - inp.minority - inp.pension_deficit
    return {
        "g": g,
        "rev": rev,
        "margin": margin,
        "ebit": ebit,
        "nopat": nopat,
        "reinvest": reinvest,
        "fcff": fcff,
        "df": df,
        "pv": pv,
        "tv": tv,
        "pv_tv": pv_tv,
        "ev": ev,
        "equity": equity,
    }


def run_dcf(inp: DcfInputs) -> DcfResult:
    r = _paths(
        inp,
        np.array([inp.growth1]),
        np.array([inp.margin_target]),
        np.array([inp.wacc]),
        np.array([inp.terminal_growth]),
    )
    ev = float(r["ev"][0])
    eq = float(r["equity"][0])
    notes = []
    if inp.wacc - inp.terminal_growth < 0.01:
        notes.append("WACC is within 1 point of terminal growth; the terminal value is extremely sensitive.")
    per_share = eq / inp.shares if inp.shares > 0 else None
    if per_share is not None and per_share < 0:
        notes.append("Debt exceeds the modeled enterprise value; equity value is floored at zero.")
        per_share = 0.0
    pv_tv = float(r["pv_tv"][0])
    table = []
    for i in range(inp.years):
        table.append(
            {
                "year": i + 1,
                "growth": float(r["g"][0, i]),
                "revenue": float(r["rev"][0, i]),
                "margin": float(r["margin"][0, i]),
                "ebit": float(r["ebit"][0, i]),
                "nopat": float(r["nopat"][0, i]),
                "reinvestment": float(r["reinvest"][0, i]),
                "fcff": float(r["fcff"][0, i]),
                "discount_factor": float(r["df"][0, i]),
                "pv": float(r["pv"][0, i]),
            }
        )
    return DcfResult(
        per_share,
        ev,
        eq,
        float(r["pv"][0].sum()),
        pv_tv,
        pv_tv / ev if ev > 0 else float("nan"),
        table,
        notes,
    )


def per_share_vector(inp: DcfInputs, g1, mt, wacc, gT) -> np.ndarray:
    r = _paths(
        inp, np.asarray(g1, float), np.asarray(mt, float), np.asarray(wacc, float), np.asarray(gT, float)
    )
    v = r["equity"] / inp.shares
    return np.maximum(v, 0.0)


def monte_carlo(
    inp: DcfInputs,
    draws: int,
    seed: int,
    sigma_g: float,
    sigma_m: float,
    sigma_wacc: float,
    sigma_gT: float,
    rho_gm: float,
    g_cap: float,
    min_spread: float,
    price: float | None = None,
) -> dict:
    """Correlated draws of growth and target margin; independent WACC and terminal growth.

    Terminal growth is constrained to ≤ g_cap and ≤ WACC − min_spread for every draw.
    """
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((draws, 4))
    zg = z[:, 0]
    zm = rho_gm * z[:, 0] + np.sqrt(1 - rho_gm**2) * z[:, 1]
    g1 = inp.growth1 + sigma_g * zg
    mt = inp.margin_target + sigma_m * zm
    wacc = np.maximum(inp.wacc + sigma_wacc * z[:, 2], 0.03)
    gT = np.minimum(np.minimum(inp.terminal_growth + sigma_gT * z[:, 3], g_cap), wacc - min_spread)
    vals = per_share_vector(inp, g1, mt, wacc, gT)
    pcts = np.percentile(vals, [5, 10, 25, 50, 75, 90, 95])
    pos = vals[vals > 0]
    log_sd = float(np.std(np.log(pos))) if len(pos) > 10 else None
    hist, edges = np.histogram(
        vals, bins=40, range=(float(np.percentile(vals, 0.5)), float(np.percentile(vals, 99.5)))
    )
    return {
        "draws": draws,
        "seed": seed,
        "percentiles": {
            k: float(v) for k, v in zip(("p5", "p10", "p25", "p50", "p75", "p90", "p95"), pcts, strict=True)
        },
        "mean": float(vals.mean()),
        "log_sd": log_sd,
        "zero_share": float(np.mean(vals <= 0)),
        "share_above_price": float(np.mean(vals > price)) if price else None,
        "histogram": {"counts": hist.tolist(), "edges": edges.tolist()},
        "inputs": {
            "sigma_growth": sigma_g,
            "sigma_margin": sigma_m,
            "sigma_wacc": sigma_wacc,
            "sigma_terminal_growth": sigma_gT,
            "growth_margin_correlation": rho_gm,
        },
    }


def sensitivity_grid(inp: DcfInputs, waccs: list[float], growths: list[float]) -> list[list[float | None]]:
    grid = []
    for w in waccs:
        row = []
        for g in growths:
            if w - g < 0.005:
                row.append(None)
                continue
            row.append(float(per_share_vector(inp, [inp.growth1], [inp.margin_target], [w], [g])[0]))
        grid.append(row)
    return grid


def tornado(inp: DcfInputs) -> list[dict]:
    base = run_dcf(inp).per_share or 0.0
    specs = [
        ("growth1", "Near-term revenue growth", 0.05, "pct_points"),
        ("margin_target", "Target operating margin", 0.03, "pct_points"),
        ("wacc", "WACC", 0.01, "pct_points"),
        ("terminal_growth", "Terminal growth", 0.005, "pct_points"),
        ("capex_pct", "Capex % of revenue", 0.02, "pct_points"),
        ("tax_terminal", "Long-run tax rate", 0.05, "pct_points"),
    ]
    out = []
    for field, label, delta, unit in specs:
        lo_inp = replace(inp, **{field: getattr(inp, field) - delta})
        hi_inp = replace(inp, **{field: getattr(inp, field) + delta})
        if field == "terminal_growth":
            hi_inp = replace(hi_inp, terminal_growth=min(hi_inp.terminal_growth, inp.wacc - 0.01))
        if field == "wacc":
            lo_inp = replace(lo_inp, wacc=max(lo_inp.wacc, inp.terminal_growth + 0.01))
        lo, hi = run_dcf(lo_inp).per_share or 0.0, run_dcf(hi_inp).per_share or 0.0
        out.append(
            {
                "driver": label,
                "field": field,
                "delta": delta,
                "unit": unit,
                "low": lo,
                "high": hi,
                "base": base,
                "range": abs(hi - lo),
            }
        )
    out.sort(key=lambda x: -x["range"])
    return out
