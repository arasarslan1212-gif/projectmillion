"""Weighted average cost of capital.

cost of equity  = risk-free (FRED 10-year Treasury) + beta × equity risk premium (config)
beta            = 3-year weekly regression vs. the market proxy, Blume-adjusted toward 1
cost of debt    = TTM interest expense ÷ average total debt, bounded to [rf + min spread, rf + max spread]
after-tax debt  = cost of debt × (1 − marginal tax rate)
weights         = market value of equity; book debt as a proxy for its market value
"""

from __future__ import annotations

from dataclasses import dataclass, field

from engine.analysis.risk import beta_regression


@dataclass
class Wacc:
    value: float
    risk_free: float
    risk_free_source: str
    erp: float
    beta: float
    beta_source: str
    cost_of_equity: float
    cost_of_debt_pre_tax: float
    cost_of_debt_after_tax: float
    cost_of_debt_source: str
    tax_rate: float
    weight_equity: float
    weight_debt: float
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def risk_free_rate(ctx, cfg: dict) -> tuple[float, str]:
    fx = ctx.data.macro(cfg["risk_free_series"])
    ctx.sources["macro"] = fx.meta()
    if fx.value and fx.value.points:
        pts = [p for p in fx.value.points if p.date <= ctx.as_of]
        if pts:
            return pts[
                -1
            ].value / 100.0, f"{fx.source} {cfg['risk_free_series']} on {pts[-1].date.isoformat()}"
    return float(
        cfg["risk_free_fallback"]
    ), f"fallback {cfg['risk_free_fallback']:.1%} ({fx.reason or 'FRED unavailable'})"


def compute_wacc(ctx, cfg: dict) -> Wacc:
    notes: list[str] = []
    rf, rf_src = risk_free_rate(ctx, cfg)
    erp = float(cfg["equity_risk_premium"])
    b = None
    if not ctx.prices.empty and not ctx.market_prices.empty:
        b = beta_regression(
            ctx.prices["adj_close"], ctx.market_prices["adj_close"], years=int(cfg["beta_years"])
        )
    if b:
        beta, beta_src = (
            b["adjusted"],
            f"{b['n_weeks']} weekly returns vs. {ctx.benchmark_tickers()[0]}, Blume-adjusted",
        )
    else:
        beta, beta_src = float(cfg["beta_fallback"]), "fallback (insufficient price history)"
        notes.append("Beta could not be estimated; a market beta of 1.0 is assumed.")
    ke = rf + beta * erp
    fin = ctx.fin
    ttm = fin.ttm
    debt = ttm.get("total_debt") or 0.0
    ie = ttm.get("interest_expense")
    prev_debt = None
    if len(fin.quarterly) >= 5:
        prev_debt = fin.quarterly[-5].values.get("total_debt")
    avg_debt = (debt + prev_debt) / 2 if prev_debt else debt
    lo, hi = rf + cfg["cost_of_debt_spread_min"], rf + cfg["cost_of_debt_spread_max"]
    if ie and avg_debt > 0:
        kd_raw = ie / avg_debt
        kd = min(max(kd_raw, lo), hi)
        kd_src = f"interest expense ÷ average debt ({kd_raw:.1%})" + (", bounded" if kd != kd_raw else "")
    else:
        kd = rf + cfg["cost_of_debt_spread_fallback"]
        kd_src = "risk-free + default spread (no interest expense reported)"
    t = float(cfg["marginal_tax_rate"])
    e = ctx.market_cap or 0.0
    total = e + debt
    we, wd = (e / total, debt / total) if total > 0 else (1.0, 0.0)
    w = we * ke + wd * kd * (1 - t)
    lo_w, hi_w = cfg["wacc_bounds"]
    if w < lo_w or w > hi_w:
        notes.append(f"WACC of {w:.1%} was bounded to [{lo_w:.0%}, {hi_w:.0%}].")
        w = min(max(w, lo_w), hi_w)
    notes.append("Debt is weighted at book value as a proxy for market value.")
    if getattr(ctx.sector, "is_financial", False):
        notes.append(
            "For banks, insurers and other financials, debt and deposits are operating items, so the app values equity "
            "directly at the cost of equity; WACC is shown for reference only."
        )
    return Wacc(w, rf, rf_src, erp, beta, beta_src, ke, kd, kd * (1 - t), kd_src, t, we, wd, notes)
