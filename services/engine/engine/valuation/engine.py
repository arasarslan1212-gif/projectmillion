"""Valuation orchestration: inputs → methods → blend → 12-month distribution, confidence, sanity checks.

12-month target construction (DECISIONS D-002/D-003):
    For intrinsic methods:  T_m = P0 · exp( ln(1 + k_e − dividend yield) + λ · ln(V_m / P0) )
    For analyst targets:    T_m = trusted consensus target (already a 12-month price)
    ln P50 = Σ w_m ln T_m             (weights = profile weight × applicability × measured accuracy, normalized)
    σ_extra² = dispersion of ln T_m across methods + (w_dcf · λ · σ_MonteCarlo)²
    σ_total  = √(σ_market² + σ_extra²) × (1 + k · (1 − confidence/100))
    P10/P90  = P50 · exp(∓ 1.2816 σ_total);  P(price > P0) = Φ(ln(P50/P0) / σ_total)
Probability of a ≥20% drawdown within 12 months comes from simulating daily paths whose annual drift is
drawn from N(ln(P50/P0), σ_extra) with daily volatility σ_market.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import replace
from datetime import timedelta

import numpy as np
from scipy.stats import norm

from engine.analysis.multiples_history import multiple_history
from engine.analysis.risk import realized_vol
from engine.analysis.trust_rating import _safe_section
from engine.fundamentals.ratios import div, series_cagr, stability, yoy
from engine.valuation import models
from engine.valuation.dcf import DcfInputs, monte_carlo, run_dcf, sensitivity_grid, tornado
from engine.valuation.reverse_dcf import assess, implied_fcf_growth, implied_revenue_growth
from engine.valuation.wacc import compute_wacc


def _median(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None and math.isfinite(x)]
    return float(np.median(xs)) if xs else None


def _seed(ctx, base: int) -> int:
    h = hashlib.sha256(f"{ctx.ticker}|{ctx.as_of.isoformat()}|{base}".encode()).hexdigest()
    return int(h[:8], 16)


def consensus_growth(ctx) -> float | None:
    """Revenue growth implied by the next fiscal year's consensus vs. the last reported fiscal year."""
    if ctx.pit or not ctx.fin.annual:
        return None
    fx = ctx.data.estimates(ctx.ticker)
    last = ctx.fin.annual[-1]
    rev_last = last.get("revenue")
    if not fx.value or not rev_last:
        return None
    nxt = sorted(
        (
            e
            for e in fx.value
            if e.metric == "revenue" and e.period_type == "annual" and e.period_end > last.end and e.mean
        ),
        key=lambda e: e.period_end,
    )
    if not nxt:
        return None
    e = nxt[0]
    yrs = max((e.period_end - last.end).days / 365.25, 0.5)
    return (e.mean / rev_last) ** (1 / yrs) - 1


def dcf_inputs(
    ctx, wacc: float, cfg: dict, universe_margin: float | None
) -> tuple[DcfInputs | None, dict, list[str]]:
    fin = ctx.fin
    t = fin.ttm
    notes: list[str] = []
    dcfg = cfg["dcf"]
    rev = t.get("revenue")
    ebit = t.get("ebit") if t.get("ebit") is not None else t.get("operating_income")
    shares = t.get("shares_diluted") or ctx.shares_outstanding[0]
    if not rev or rev <= 0 or ebit is None or not shares:
        return None, {}, ["DCF needs trailing revenue, operating income and a share count."]
    m0 = ebit / rev
    a = fin.annual[-6:]
    hist_margins = [
        p.get("operating_income") / p.get("revenue")
        for p in a
        if p.get("operating_income") is not None and p.get("revenue")
    ]
    rev_series = fin.annual_series("revenue")
    hist_g = series_cagr(rev_series, 3) or (
        yoy(rev_series[-1][1], rev_series[-2][1]) if len(rev_series) >= 2 else None
    )
    cons_g = consensus_growth(ctx)
    if cons_g is not None and hist_g is not None:
        g1 = 0.6 * cons_g + 0.4 * hist_g
        g_src = f"60% consensus ({cons_g:.1%}) + 40% 3-year history ({hist_g:.1%})"
    elif cons_g is not None:
        g1, g_src = cons_g, f"consensus ({cons_g:.1%})"
    elif hist_g is not None:
        g1, g_src = hist_g, f"3-year revenue CAGR ({hist_g:.1%})"
    else:
        g1, g_src = dcfg["terminal_growth"], "no growth history; terminal growth assumed"
    lo, hi = dcfg["near_term_growth_bounds"]
    if not lo <= g1 <= hi:
        notes.append(f"Near-term growth {g1:.1%} was bounded to [{lo:.0%}, {hi:.0%}].")
        g1 = min(max(g1, lo), hi)
    if ctx.sector.profile == "growth_unprofitable" or m0 <= 0:
        target = max(universe_margin or 0.15, 0.08)
        m_src = f"industry median operating margin of profitable peers ({target:.1%}), reached over {dcfg['margin_convergence_years']} years"
        notes.append(
            "The company is not yet profitable; the DCF assumes margins converge toward the industry level, which is uncertain."
        )
    else:
        med = _median(hist_margins)
        target = 0.5 * m0 + 0.5 * med if med is not None else m0
        m_src = f"average of current ({m0:.1%}) and 5-year median ({(med or m0):.1%}) operating margin"
    tax_eff = div(t.get("income_tax"), t.get("pretax_income")) if (t.get("pretax_income") or 0) > 0 else None
    tlo, thi = dcfg["tax_rate_bounds"]
    tax0 = min(max(tax_eff, tlo), thi) if tax_eff is not None else cfg["wacc"]["marginal_tax_rate"]

    def pct(key: str) -> float | None:
        vals = [p.get(key) / p.get("revenue") for p in a if p.get(key) is not None and p.get("revenue")]
        return _median(vals)

    dna_pct = pct("dna") or 0.0
    capex_pct = pct("capex") or dna_pct
    nwc_vals = []
    for p in a:
        r = p.get("revenue")
        if r:
            nwc_vals.append(
                (
                    (p.get("receivables") or 0.0)
                    + (p.get("inventory") or 0.0)
                    - (p.get("accounts_payable") or 0.0)
                )
                / r
            )
    nwc_pct = _median(nwc_vals) or 0.0
    rf_cap = dcfg["terminal_growth_cap"]
    g_t = min(dcfg["terminal_growth"], rf_cap, wacc - dcfg["min_wacc_minus_g"])
    pension = t.get("pension_funded_status")
    pension_def = -pension if (pension is not None and pension < 0) else 0.0
    inp = DcfInputs(
        revenue0=rev,
        margin0=m0,
        margin_target=target,
        growth1=g1,
        terminal_growth=g_t,
        wacc=wacc,
        tax0=tax0,
        tax_terminal=cfg["wacc"]["marginal_tax_rate"],
        dna_pct=dna_pct,
        capex_pct=capex_pct,
        nwc_pct=nwc_pct,
        debt=t.get("total_debt") or 0.0,
        cash=t.get("cash_and_st") or t.get("cash") or 0.0,
        minority=t.get("minority_interest") or 0.0,
        pension_deficit=pension_def,
        shares=shares,
        years=int(dcfg["years"]),
        margin_years=int(dcfg["margin_convergence_years"]),
        terminal_roic_spread=dcfg["terminal_roic_spread"],
        mid_year=bool(dcfg["mid_year"]),
    )
    sources = {
        "growth1": g_src,
        "margin_target": m_src,
        "tax0": "trailing effective tax rate (bounded)" if tax_eff is not None else "statutory marginal rate",
        "dna_pct": "5-year median D&A ÷ revenue",
        "capex_pct": "5-year median capex ÷ revenue",
        "nwc_pct": "5-year median (receivables + inventory − payables) ÷ revenue",
        "terminal_growth": f"config {dcfg['terminal_growth']:.1%}, capped at {rf_cap:.1%}",
        "shares": "diluted weighted-average shares (latest quarter; includes treasury-method dilution for that period)",
        "pension_deficit": "unfunded pension (XBRL funded status)"
        if pension is not None
        else "not tagged; assumed zero",
    }
    if pension is None:
        notes.append("Pension funded status is not tagged; the equity bridge assumes no pension deficit.")
    return inp, sources, notes


def scenario_values(inp: DcfInputs, cfg: dict) -> dict:
    out = {}
    for name, s in cfg["dcf"]["scenarios"].items():
        g = (
            inp.growth1 * s["growth_mult"] + s["growth_shift"]
            if inp.growth1 > 0
            else inp.growth1 + s["growth_shift"]
        )
        w = inp.wacc + s["wacc_shift"]
        gt = min(inp.terminal_growth, w - cfg["dcf"]["min_wacc_minus_g"])
        si = replace(
            inp, growth1=g, margin_target=inp.margin_target + s["margin_shift"], wacc=w, terminal_growth=gt
        )
        r = run_dcf(si)
        out[name] = {
            "value": r.per_share,
            "growth1": g,
            "margin_target": si.margin_target,
            "wacc": w,
            "terminal_growth": gt,
            "terminal_share": r.terminal_share,
            "probability": cfg["dcf"]["scenario_probabilities"][name],
        }
    return out


def bank_scenarios(ctx, ke: float, cfg: dict) -> dict:
    from engine.fundamentals.ratios import ttm_ratios

    base_roe = ttm_ratios(ctx.fin).get("roe")
    out = {}
    if base_roe is None:
        return out
    for name, (droe, dke) in {"bear": (-0.03, 0.01), "base": (0.0, 0.0), "bull": (0.02, -0.005)}.items():
        r = models.excess_return(ctx, ke + dke, cfg["excess_return"], roe_override=base_roe + droe)
        out[name] = {
            "value": r.value,
            "roe": base_roe + droe,
            "cost_of_equity": ke + dke,
            "probability": cfg["dcf"]["scenario_probabilities"][name],
        }
    return out


def confidence_score(ctx, parts: dict, cfg_all: dict) -> dict:
    ccfg = cfg_all["confidence"]
    anch = ccfg["anchors"]
    miss = float(ccfg["missing_component_score"])

    def lin(v, a):
        a0, a100 = a
        return float(min(100.0, max(0.0, (v - a0) / (a100 - a0) * 100.0)))

    comps = {}
    d = parts.get("method_dispersion")
    comps["agreement"] = (
        (lin(d, anch["method_dispersion"]), f"valuation methods disagree by {d:.2f} (log std)")
        if d is not None
        else (miss, "only one method available")
    )
    comps["data"] = (parts["data_score"], parts["data_note"])
    gv = parts.get("growth_volatility")
    eps_pos = parts.get("eps_positive_share")
    if gv is not None:
        pred = 0.6 * lin(gv, anch["growth_volatility"]) + 0.4 * (
            100 * (eps_pos if eps_pos is not None else 0.5)
        )
        comps["predictability"] = (
            pred,
            f"revenue-growth volatility {gv:.1%}; EPS positive in {eps_pos:.0%} of years"
            if eps_pos is not None
            else f"revenue-growth volatility {gv:.1%}",
        )
    else:
        comps["predictability"] = (miss, "fewer than 4 years of revenue history")
    vol = parts.get("volatility")
    comps["volatility"] = (
        (lin(vol, anch["realized_volatility"]), f"realized volatility {vol:.0%}")
        if vol is not None
        else (miss, "no price history")
    )
    ad = parts.get("analyst_dispersion")
    comps["analyst_dispersion"] = (
        (lin(ad, anch["analyst_dispersion"]), f"analyst targets span {ad:.0%} of their mean")
        if ad is not None
        else (miss, "no analyst target data")
    )
    ce = parts.get("calibration_error")
    comps["calibration"] = (
        (lin(ce, anch["calibration_error"]), parts.get("calibration_note", ""))
        if ce is not None
        else (miss, parts.get("calibration_note") or "no track record for similar stocks yet")
    )
    w = ccfg["weights"]
    score = sum(w[k] * comps[k][0] for k in w) / sum(w.values())
    cap = ccfg["profile_caps"].get(ctx.sector.profile)
    capped = False
    if cap is not None and score > cap:
        score, capped = float(cap), True
    level = next(lbl for th, lbl in ccfg["levels"] if score >= th)
    breakdown = [
        {
            "id": k,
            "label": k.replace("_", " ").capitalize(),
            "score": comps[k][0],
            "weight": w[k],
            "note": comps[k][1],
        }
        for k in w
    ]
    worst = min(breakdown, key=lambda x: x["score"])
    best = max(breakdown, key=lambda x: x["score"])
    explain = (
        f"Confidence {score:.0f}/100 ({level}). Highest: {best['label'].lower()} ({best['note']}). "
        f"Lowest: {worst['label'].lower()} ({worst['note']})."
    )
    if capped:
        explain += f" Capped at {cap} for the {ctx.sector.profile_label.lower()} profile."
    return {"score": score, "level": level, "breakdown": breakdown, "capped": capped, "explain": explain}


def value(ctx, include_analysts: bool | None = None) -> dict:
    cfg_all = ctx.cfg.data
    cfg = cfg_all["valuation"]
    if include_analysts is None:
        include_analysts = bool(cfg["analyst_consensus_default_included"])
    p0 = ctx.last_price
    if p0 is None:
        return {"status": "missing", "reason": "no price"}
    w = compute_wacc(ctx, cfg["wacc"])
    prof = ctx.sector.profile
    methods_cfg = (
        cfg["methods"].get(prof) or cfg["methods"].get(ctx.sector.base_profile) or cfg["methods"]["general"]
    )
    peers = _safe_section(ctx, "peers")
    prof_score = profitability_percentile(ctx)
    history = multiple_history(ctx.fin, ctx.prices)
    uni_margin = None
    if ctx.universe:
        ms = [
            r.ratios.get("operating_margin")
            for r in ctx.universe.rows
            if (r.ratios.get("operating_margin") or 0) > 0
        ]
        uni_margin = _median(ms)

    results: dict[str, models.MethodResult] = {}
    dcf_block = None
    if "dcf" in methods_cfg:
        inp, src, notes = dcf_inputs(ctx, w.value, cfg, uni_margin)
        if inp is None:
            results["dcf"] = models.missing("dcf", "Discounted cash flow", notes[0])
        else:
            base = run_dcf(inp)
            mc_cfg = cfg["monte_carlo"]
            rev_s = ctx.fin.annual_series("revenue")
            gvol = stability(
                [yoy(rev_s[i][1], rev_s[i - 1][1]) for i in range(max(1, len(rev_s) - 8), len(rev_s))]
            )
            om = [
                p.get("operating_income") / p.get("revenue")
                for p in ctx.fin.annual[-8:]
                if p.get("operating_income") is not None and p.get("revenue")
            ]
            mvol = stability(om)
            sg = min(max(gvol or 0.05, mc_cfg["growth_sigma_bounds"][0]), mc_cfg["growth_sigma_bounds"][1])
            sm = min(max(mvol or 0.03, mc_cfg["margin_sigma_bounds"][0]), mc_cfg["margin_sigma_bounds"][1])
            mc = monte_carlo(
                inp,
                int(mc_cfg["draws"]),
                _seed(ctx, int(mc_cfg["seed"])),
                sg,
                sm,
                mc_cfg["wacc_sigma"],
                mc_cfg["terminal_growth_sigma"],
                mc_cfg["growth_margin_correlation"],
                cfg["dcf"]["terminal_growth_cap"],
                cfg["dcf"]["min_wacc_minus_g"],
                price=p0,
            )
            fcf_neg = (ctx.fin.ttm.get("fcf") or 0) <= 0
            applic = 1.0
            if fcf_neg or inp.margin0 <= 0:
                applic *= 0.5
                notes.append(
                    "Trailing free cash flow or operating margin is negative, so the DCF depends heavily on assumed future margins."
                )
            if base.terminal_share > 0.85:
                applic *= 0.6
            waccs = [round(w.value + d, 4) for d in (-0.02, -0.01, -0.005, 0, 0.005, 0.01, 0.02)]
            gts = [0.01, 0.015, 0.02, 0.025, 0.03]
            dcf_block = {
                "inputs": inp.to_dict(),
                "input_sources": src,
                "table": base.table,
                "enterprise_value": base.enterprise_value,
                "equity_value": base.equity_value,
                "pv_explicit": base.pv_explicit,
                "pv_terminal": base.pv_terminal,
                "terminal_share": base.terminal_share,
                "per_share": base.per_share,
                "monte_carlo": mc,
                "scenarios": scenario_values(inp, cfg),
                "sensitivity": {"waccs": waccs, "growths": gts, "values": sensitivity_grid(inp, waccs, gts)},
                "tornado": tornado(inp),
                "notes": notes + base.notes,
            }
            results["dcf"] = models.MethodResult(
                "dcf",
                "Discounted cash flow",
                base.per_share,
                applic,
                {
                    "terminal_share": base.terminal_share,
                    "mc_p10": mc["percentiles"]["p10"],
                    "mc_p90": mc["percentiles"]["p90"],
                },
                notes + base.notes,
            )
    rcfg = cfg["relative"]
    if "relative_peers" in methods_cfg:
        results["relative_peers"] = models.relative_peers(ctx, peers, prof_score, rcfg)
    if "relative_history" in methods_cfg:
        results["relative_history"] = models.relative_history(ctx, history, rcfg)
    if "pb_roe_regression" in methods_cfg:
        results["pb_roe_regression"] = models.pb_roe_regression(ctx, peers)
    if "excess_return" in methods_cfg:
        results["excess_return"] = models.excess_return(ctx, w.cost_of_equity, cfg["excess_return"])
    if "ddm" in methods_cfg:
        results["ddm"] = models.ddm(ctx, w.cost_of_equity, cfg["ddm"])
    if "p_ffo_history" in methods_cfg:
        results["p_ffo_history"] = models.p_ffo_history(ctx, history, rcfg)
    if "p_ffo_peers" in methods_cfg:
        results["p_ffo_peers"] = models.p_ffo_peers(ctx, peers)
    if "ev_sales_regression" in methods_cfg:
        results["ev_sales_regression"] = models.ev_sales_regression(ctx, peers)
    analysts = _safe_section(ctx, "analysts")
    if "analyst_consensus" in methods_cfg:
        tgt = (analysts or {}).get("consensus_trusted")
        if tgt:
            results["analyst_consensus"] = models.MethodResult(
                "analyst_consensus",
                "Trusted analyst consensus",
                tgt,
                1.0,
                {"target": tgt},
                ["A 12-month target, not an intrinsic value."],
                kind="target",
            )
        else:
            results["analyst_consensus"] = models.missing(
                "analyst_consensus", "Trusted analyst consensus", "no analyst price targets available"
            )

    # ---- blend ------------------------------------------------------------------------------
    dy = sum(v for d, v in ctx.dividends if (ctx.as_of - d).days <= 365) / p0
    drift = math.log(max(1 + w.cost_of_equity - dy, 0.5))
    lam = float(cfg["convergence_12m"])
    accuracy = method_accuracy(ctx)

    def blend(include_an: bool):
        rows = []
        for mid, r in results.items():
            if r.value is None or r.value <= 0 or r.applicability <= 0:
                continue
            if mid == "analyst_consensus" and not include_an:
                continue
            base_w = float(methods_cfg.get(mid, 0.0))
            acc = accuracy.get(mid, 1.0)
            wt = base_w * r.applicability * acc
            if wt <= 0:
                continue
            t12 = r.value if r.kind == "target" else p0 * math.exp(drift + lam * math.log(r.value / p0))
            rows.append(
                {
                    "id": mid,
                    "label": r.label,
                    "value": r.value,
                    "target_12m": t12,
                    "raw_weight": wt,
                    "base_weight": base_w,
                    "applicability": r.applicability,
                    "accuracy": acc,
                    "kind": r.kind,
                }
            )
        tot = sum(x["raw_weight"] for x in rows)
        for x in rows:
            x["weight"] = x["raw_weight"] / tot if tot else 0.0
        return rows

    rows = blend(include_analysts)
    rows_alt = blend(not include_analysts)
    if not rows:
        return {
            "status": "missing",
            "reason": "no valuation method produced a value",
            "wacc": w.to_dict(),
            "methods": [r.to_dict() for r in results.values()],
        }

    def dist(rows_):
        lnp = sum(x["weight"] * math.log(x["target_12m"]) for x in rows_)
        disp = math.sqrt(sum(x["weight"] * (math.log(x["target_12m"]) - lnp) ** 2 for x in rows_))
        return lnp, disp

    ln_p50, disp12 = dist(rows)
    intr = [x for x in rows if x["kind"] == "intrinsic"]
    iw = sum(x["weight"] for x in intr)
    intrinsic = math.exp(sum(x["weight"] * math.log(x["value"]) for x in intr) / iw) if iw > 0 else None
    disp_intr = (
        math.sqrt(sum(x["weight"] / iw * (math.log(x["value"]) - math.log(intrinsic)) ** 2 for x in intr))
        if intrinsic
        else None
    )
    sigma_mc = (dcf_block or {}).get("monte_carlo", {}).get("log_sd") or 0.0
    w_dcf = next((x["weight"] for x in rows if x["id"] == "dcf"), 0.0)
    sigma_extra = math.sqrt(disp12**2 + (w_dcf * lam * sigma_mc) ** 2)
    vol = realized_vol(ctx.prices["adj_close"]) if not ctx.prices.empty else None
    sigma_mkt = vol if vol is not None else 0.35

    # ---- confidence -----------------------------------------------------------------------
    fin = ctx.fin
    rev_s = fin.annual_series("revenue")
    gvol = stability([yoy(rev_s[i][1], rev_s[i - 1][1]) for i in range(max(1, len(rev_s) - 8), len(rev_s))])
    eps_s = [v for _, v in fin.annual_series("eps_diluted")[-8:]]
    eps_pos = (sum(1 for v in eps_s if v > 0) / len(eps_s)) if eps_s else None
    planned = [m for m in methods_cfg if m != "analyst_consensus"]
    got = [m for m in planned if results.get(m) and results[m].value is not None]
    latest_filing = max((f.filed_at for f in ctx.filings if f.form in ("10-K", "10-Q")), default=None)
    fresh = (
        1.0 if latest_filing and (ctx.as_of - latest_filing).days <= 120 else 0.5 if latest_filing else 0.0
    )
    years = min(fin.years_of_history / 8.0, 1.0)
    data_score = 100 * (0.5 * (len(got) / len(planned) if planned else 0) + 0.3 * years + 0.2 * fresh)
    calib = calibration_for(ctx, vol)
    parts = {
        "method_dispersion": disp_intr if (disp_intr is not None and len(intr) >= 2) else None,
        "data_score": data_score,
        "data_note": f"{len(got)} of {len(planned)} valuation methods had data; {fin.years_of_history} years of filings; latest filing "
        + (f"{(ctx.as_of - latest_filing).days} days old" if latest_filing else "missing"),
        "growth_volatility": gvol,
        "eps_positive_share": eps_pos,
        "volatility": vol,
        "analyst_dispersion": (analysts or {}).get("target_dispersion"),
        "calibration_error": calib.get("error"),
        "calibration_note": calib.get("note"),
    }
    conf = confidence_score(ctx, parts, cfg_all)
    widen = 1 + float(cfg["range"]["confidence_widening"]) * (1 - conf["score"] / 100)
    sigma_total = math.sqrt(sigma_mkt**2 + sigma_extra**2) * widen
    z = float(cfg["range"]["z80"])

    def target_from(lnp: float) -> dict:
        p50 = math.exp(lnp)
        mu = math.log(p50 / p0)
        return {
            "p10": p50 * math.exp(-z * sigma_total),
            "p50": p50,
            "p90": p50 * math.exp(z * sigma_total),
            "implied_return": p50 / p0 - 1,
            "expected_return": math.exp(mu + sigma_total**2 / 2) - 1,
            "prob_up": float(norm.cdf(mu / sigma_total)),
        }

    target = target_from(ln_p50)
    alt_target = target_from(dist(rows_alt)[0]) if rows_alt else None
    target["prob_drawdown_20"] = drawdown_probability(
        ctx, math.log(target["p50"] / p0), sigma_extra * widen, sigma_mkt, cfg
    )

    # ---- reverse DCF --------------------------------------------------------------------------
    rdcf = None
    if ctx.sector.is_financial and "excess_return" in results:
        rdcf = reverse_excess_return(ctx, p0, w.cost_of_equity, cfg)
    elif ctx.market_cap:
        t = fin.ttm
        ev_now = ctx.market_cap + (t.get("net_debt") or 0.0) + (t.get("minority_interest") or 0.0)
        g_t = cfg["dcf"]["terminal_growth"]
        yrs = cfg["dcf"]["years"]
        fcf_implied = rev_implied = None
        fcff0 = None
        if dcf_block:
            inp = DcfInputs(**dcf_block["inputs"])
            fcff0 = (t.get("ebit") or 0) * (1 - inp.tax0) + (t.get("dna") or 0) - (t.get("capex") or 0)
            rev_implied = implied_revenue_growth(inp, p0)
            capex_heavy = inp.capex_pct >= 0.2
        else:
            fcff0 = t.get("fcf")
            capex_heavy = False
        if fcff0 and fcff0 > 0 and not capex_heavy:
            fcf_implied = implied_fcf_growth(fcff0, ev_now, w.value, g_t, yrs)
        cons = consensus_growth(ctx)
        if fcf_implied is not None:
            hist = series_cagr(fin.annual_series("fcf"), 5) or series_cagr(fin.annual_series("fcf"), 3)
            implied, basis = fcf_implied, "free cash flow"
            statement = f"The market is pricing in about {implied:.1%} annual free-cash-flow growth for {yrs} years, then {g_t:.1%} a year."
        elif rev_implied is not None:
            hist = series_cagr(fin.annual_series("revenue"), 3)
            implied, basis = rev_implied, "revenue"
            inp = DcfInputs(**dcf_block["inputs"])
            statement = (
                f"The market price implies first-year revenue growth of about {implied:.1%}, fading to {g_t:.1%} over {yrs} years, "
                f"with operating margins moving to {inp.margin_target:.1%} as in the app's DCF."
            )
        else:
            hist, implied, basis = None, None, None
            statement = "The implied growth rate could not be solved: this profile has no cash-flow model, or cash flow is negative."
        rdcf = {
            "implied_growth": implied,
            "basis": basis,
            "years": yrs,
            "history_growth": hist,
            "consensus_growth": cons,
            "assessment": assess(implied, hist, cons),
            "enterprise_value": ev_now,
            "statement": statement,
            "fcf_implied_growth": fcf_implied,
            "revenue_implied_growth": rev_implied,
        }

    # ---- market-implied reference band ----------------------------------------------------------
    mkt_med = p0 * (1 + w.cost_of_equity - dy)
    market_band = {
        "p10": mkt_med * math.exp(-z * sigma_mkt),
        "p50": mkt_med,
        "p90": mkt_med * math.exp(z * sigma_mkt),
        "sigma": sigma_mkt,
        "note": "Lognormal band from historical volatility and the cost of equity: a sanity check on the range width, not a view.",
    }

    sanity = sanity_checks(ctx, target, dcf_block, peers, w, cfg, p0)
    cone = cone_path(ctx, p0, math.log(target["p50"] / p0), sigma_mkt * widen, sigma_extra * widen)
    scen = (
        dcf_block["scenarios"]
        if dcf_block
        else (bank_scenarios(ctx, w.cost_of_equity, cfg) if prof == "bank" else {})
    )
    mh = {"dates": [h.date for h in history], "series": {}, "bands": {}}
    for key in ("pe", "ev_ebitda", "ev_sales", "p_fcf", "p_b", "p_ffo"):
        vals = [h.values.get(key) for h in history]
        if sum(1 for x in vals if x is not None) >= 8:
            mh["series"][key] = vals
            from engine.analysis.multiples_history import band_stats

            mh["bands"][key] = band_stats(history, key, int(cfg["relative"]["history_years"]), ctx.as_of)
    return {
        "status": "ok",
        "price": p0,
        "multiples_history": mh,
        "wacc": w.to_dict(),
        "methods": [r.to_dict() for r in results.values()],
        "blend": rows,
        "blend_alternative": {
            "include_analysts": not include_analysts,
            "target": alt_target,
            "weights": rows_alt,
        },
        "include_analysts": include_analysts,
        "intrinsic": intrinsic,
        "target": target,
        "sigma": {
            "market": sigma_mkt,
            "method_dispersion": disp12,
            "monte_carlo": sigma_mc,
            "extra": sigma_extra,
            "widening": widen,
            "total": sigma_total,
            "convergence": lam,
            "drift": drift,
            "dividend_yield": dy,
        },
        "confidence": conf,
        "dcf": dcf_block,
        "scenarios": scen,
        "reverse_dcf": rdcf,
        "market_band": market_band,
        "sanity": sanity,
        "cone": cone,
        "accuracy_source": accuracy.get(
            "_source", "no backtest results yet; all methods weighted equally on accuracy"
        ),
    }


def reverse_excess_return(ctx, p0: float, ke: float, cfg: dict) -> dict | None:
    """For banks and other financials: the sustainable ROE today's price-to-book implies.

    Justified P/B = (ROE − g) ÷ (kₑ − g)  ⇒  implied ROE = g + P/B × (kₑ − g), with g the terminal growth rate.
    """
    from engine.fundamentals.ratios import ttm_ratios

    t = ctx.fin.ttm
    shares, eq = t.get("shares_diluted"), t.get("equity")
    if not shares or not eq or eq <= 0:
        return None
    pb = p0 / (eq / shares)
    g = min(float(cfg["dcf"]["terminal_growth"]), ke - 0.01)
    implied = g + pb * (ke - g)
    trailing = ttm_ratios(ctx.fin).get("roe")
    roes = [div(p.get("net_income"), p.get("equity")) for p in ctx.fin.annual[-5:]]
    hist = _median([r for r in roes if r is not None])
    statement = (
        f"Today's price-to-book of {pb:.2f}× implies a sustainable return on equity of about {implied:.1%} "
        f"(with {g:.1%} long-run growth and an equity cost of {ke:.1%}). Trailing ROE is "
        + (f"{trailing:.1%}" if trailing is not None else "unavailable")
        + "."
    )
    return {
        "implied_growth": None,
        "implied_roe": implied,
        "price_to_book": pb,
        "basis": "return on equity",
        "years": None,
        "history_roe": hist,
        "trailing_roe": trailing,
        "assessment": assess(implied, hist, trailing),
        "statement": statement,
        "cost_of_equity": ke,
        "enterprise_value": None,
        "history_growth": None,
        "consensus_growth": None,
        "fcf_implied_growth": None,
        "revenue_implied_growth": None,
    }


def profitability_percentile(ctx) -> float | None:
    """Sector percentile of the company's returns and margins (0–100), used to adjust peer multiples.

    Computed here rather than taken from the Trust Rating so the two never depend on each other
    (the Trust Rating's valuation pillar uses this section's output).
    """
    from engine.fundamentals.ratios import ttm_ratios
    from engine.fundamentals.universe import percentile_of

    if ctx.universe is None:
        return None
    ttm = ttm_ratios(ctx.fin)
    keys = ("roe", "rotce") if ctx.sector.is_financial else ("roic", "operating_margin")
    pcts = []
    for k in keys:
        pop = [r.ratios.get(k) for r in ctx.universe.rows if r.ratios.get(k) is not None]
        if len(pop) >= 8 and ttm.get(k) is not None:
            pcts.append(percentile_of(ttm[k], pop))
    return float(np.mean(pcts)) if pcts else None


def method_accuracy(ctx) -> dict:
    """Relative accuracy multipliers per method from the backtest (M8). Defaults to 1.0."""
    try:
        from engine.track.calibration import method_accuracy_weights

        return method_accuracy_weights(ctx.sector.profile)
    except Exception:
        return {"_source": "no backtest results yet; all methods weighted equally on accuracy"}


def calibration_for(ctx, vol: float | None) -> dict:
    try:
        from engine.track.calibration import bucket_calibration

        return bucket_calibration(ctx, vol)
    except Exception:
        return {"error": None, "note": "no track record for similar stocks yet"}


def drawdown_probability(ctx, mu: float, sigma_extra: float, sigma_mkt: float, cfg: dict) -> float:
    mc = cfg["monte_carlo"]
    n, days = int(mc["path_draws"]), int(mc["path_days"])
    rng = np.random.default_rng(_seed(ctx, int(mc["seed"]) + 1))
    drift = mu + sigma_extra * rng.standard_normal(n)
    # log-price increments whose median path ends at ln(P50/P0) (mu is already a median log return)
    daily = drift[:, None] / days + sigma_mkt / math.sqrt(days) * rng.standard_normal((n, days))
    path = np.exp(np.cumsum(daily, axis=1))
    path = np.concatenate([np.ones((n, 1)), path], axis=1)
    peak = np.maximum.accumulate(path, axis=1)
    mdd = (path / peak - 1).min(axis=1)
    return float(np.mean(mdd <= -0.2))


def cone_path(ctx, p0: float, mu: float, s_mkt: float, s_extra: float) -> dict:
    """P10/P50/P90 for every business day of the next 12 months (charts space points by index, not time)."""
    import pandas as pd

    z = 1.2816
    start = ctx.last_price_date or ctx.as_of
    days = pd.bdate_range(start, start + timedelta(days=365))
    dates, p10, p50, p90 = [], [], [], []
    for d in days:
        tt = (d.date() - start).days / 365.25
        s = math.sqrt(s_mkt**2 * tt + (s_extra * tt) ** 2)
        c = math.log(p0) + mu * tt
        dates.append(d.date().isoformat())
        p10.append(round(math.exp(c - z * s), 4))
        p50.append(round(math.exp(c), 4))
        p90.append(round(math.exp(c + z * s), 4))
    return {
        "dates": dates,
        "p10": p10,
        "p50": p50,
        "p90": p90,
        "note": "Market uncertainty grows with √time; valuation uncertainty grows linearly as the gap to value closes.",
    }


def sanity_checks(
    ctx, target: dict, dcf: dict | None, peers: dict | None, w, cfg: dict, p0: float
) -> list[dict]:
    sc = cfg["sanity"]
    out = []
    move = target["p50"] / p0 - 1
    if abs(move) > sc["max_move"]:
        out.append(
            {
                "id": "large_move",
                "severity": "high",
                "message": f"The central target implies a {move:+.0%} move; treat it with extra caution.",
            }
        )
    if dcf:
        if dcf["terminal_share"] > sc["max_terminal_share"]:
            out.append(
                {
                    "id": "terminal_value",
                    "severity": "medium",
                    "message": f"The terminal value is {dcf['terminal_share']:.0%} of the DCF enterprise value (above {sc['max_terminal_share']:.0%}), so the DCF rests mostly on long-run assumptions.",
                }
            )
        if (ctx.fin.ttm.get("fcf") or 0) <= 0:
            out.append(
                {
                    "id": "negative_fcf",
                    "severity": "medium",
                    "message": "Trailing free cash flow is negative, which makes the DCF unreliable.",
                }
            )
        if w.value - dcf["inputs"]["terminal_growth"] < cfg["dcf"]["min_wacc_minus_g"] + 0.001:
            out.append(
                {
                    "id": "wacc_near_g",
                    "severity": "medium",
                    "message": "WACC is close to terminal growth; the DCF is very sensitive to both.",
                }
            )
    latest = max((f.filed_at for f in ctx.filings if f.form in ("10-K", "10-Q")), default=None)
    if latest is None or (ctx.as_of - latest).days > sc["stale_filing_days"]:
        out.append(
            {
                "id": "stale_filings",
                "severity": "medium",
                "message": "The latest periodic filing is more than "
                + str(sc["stale_filing_days"])
                + " days old; fundamentals may be stale.",
            }
        )
    if ctx.last_price_date and (ctx.as_of - ctx.last_price_date).days > sc["stale_price_days"]:
        out.append(
            {
                "id": "stale_price",
                "severity": "medium",
                "message": f"The last price is from {ctx.last_price_date.isoformat()}.",
            }
        )
    n_peers = len([r for r in (peers or {}).get("rows", []) if not r["is_subject"]])
    if n_peers < cfg["relative"]["min_peers"]:
        out.append(
            {
                "id": "few_peers",
                "severity": "low",
                "message": f"Only {n_peers} peers were available, too few for a reliable relative valuation.",
            }
        )
    if ctx.sector.profile == "biotech_pipeline":
        out.append(
            {
                "id": "pipeline",
                "severity": "high",
                "message": "Pipeline-driven biotech: value depends on trial and approval outcomes the model cannot estimate precisely.",
            }
        )
    return out
