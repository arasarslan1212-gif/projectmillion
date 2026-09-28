"""Trust Rating: a 0–100 score of how strong, reliable and reasonably priced the business is relative to
its sector. Every metric, weight, anchor and penalty comes from config/engine.yaml (trust_rating).

Scoring:
1. Each metric is scored 0–100. It is a sector percentile against the SEC-frames industry universe
   when at least `min_universe` peers have the metric; otherwise a linear map between the metric's
   anchors, clipped. Composite scores with published thresholds always use anchors.
2. A pillar score is the mean of its available metric scores, capped by any triggered red flag
   mapped to that pillar.
3. The Trust Rating is the weighted mean of available pillar scores (weights by sector profile,
   renormalized over the pillars that have data), minus overall red-flag deductions, clipped to 0–100.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import numpy as np

from engine.analysis import quality as q
from engine.analysis.multiples_history import band_stats, multiple_history, zscore
from engine.analysis.risk import beta_regression, downside_deviation, max_drawdown, realized_vol
from engine.analysis.technicals import momentum_12_1, total_return, trend_score
from engine.fundamentals.ratios import div, ratio_history, series_cagr, stability, ttm_ratios
from engine.fundamentals.universe import percentile_of

if TYPE_CHECKING:
    from engine.report.context import ReportContext


@dataclass
class MetricScore:
    id: str
    label: str
    unit: str
    value: float | None
    score: float | None
    basis: str | None  # sector | anchor
    percentile: float | None
    n: int | None
    source: str | None
    note: str | None = None
    reason: str | None = None
    target_up: dict | None = None
    target_down: dict | None = None


@dataclass
class PillarScore:
    id: str
    label: str
    score: float | None
    weight: float
    effective_weight: float
    metrics: list[MetricScore] = field(default_factory=list)
    capped_by: list[str] = field(default_factory=list)
    explanation: str = ""
    raise_if: str | None = None
    lower_if: str | None = None


def grade_for(score: float | None, bands: list) -> str | None:
    if score is None:
        return None
    for threshold, grade in bands:
        if score >= threshold:
            return grade
    return bands[-1][1]


def anchor_score(value: float, anchors: list[float]) -> float:
    a0, a100 = anchors
    if a100 == a0:
        return 50.0
    return float(min(100.0, max(0.0, (value - a0) / (a100 - a0) * 100.0)))


def anchor_inverse(score: float, anchors: list[float]) -> float:
    a0, a100 = anchors
    return a0 + (a100 - a0) * score / 100.0


def _population(ctx: ReportContext, key: str | None) -> list[float]:
    if not key or ctx.universe is None:
        return []
    return [r.ratios.get(key) for r in ctx.universe.rows if r.ratios.get(key) is not None]


def _safe_section(ctx: ReportContext, name: str) -> dict | None:
    """Another section's output if it is registered and computed without error."""
    from engine.report.builder import _REGISTRY, _ensure_registered

    _ensure_registered()
    fn = _REGISTRY.get(name)
    if fn is None:
        return None
    try:
        out = ctx.section(name, fn)
    except Exception:
        return None
    return out if out and out.get("status") in ("ok", "partial") else None


def collect_values(
    ctx: ReportContext, quality_scores: dict
) -> dict[str, tuple[float | None, str | None, str | None]]:
    """metric id -> (value, source label, note/reason)."""
    fin = ctx.fin
    ttm = ttm_ratios(fin)
    src_f = ctx.sources.get("fundamentals", {}).get("source")
    src_p = ctx.sources.get("prices", {}).get("source")
    vals: dict[str, tuple[float | None, str | None, str | None]] = {}

    for k in (
        "net_debt_to_ebitda",
        "interest_coverage",
        "current_ratio",
        "debt_to_equity",
        "debt_to_assets",
        "equity_to_assets",
        "loan_to_deposit",
        "fcf_conversion",
        "sbc_pct_revenue",
        "roic",
        "gross_margin",
        "operating_margin",
        "net_margin",
        "roe",
        "rotce",
        "efficiency_ratio",
        "nim",
        "combined_ratio",
        "ffo_margin",
    ):
        vals[k] = (ttm.get(k), src_f, None)
    a = fin.annual
    vals["accruals_ratio"] = (quality_scores.get("accruals_ratio"), src_f, None)
    for key in ("altman", "beneish", "piotroski"):
        s = quality_scores.get(key) or {}
        mid = {"altman": "altman_z", "beneish": "beneish_m", "piotroski": "piotroski_f"}[key]
        vals[mid] = (s.get("value"), src_f, s.get("variant") or s.get("reason"))

    ann, _ = ratio_history(fin)
    om = [r["ratios"].get("operating_margin") for r in ann[-8:]]
    ro = [r["ratios"].get("roic") for r in ann[-8:]]
    vals["margin_stability"] = (stability(om), src_f, None)
    ro_vals = [x for x in ro if x is not None]
    ro_std = stability(ro_vals)
    vals["roic_persistence"] = (
        ro_std / max(abs(float(np.mean(ro_vals))), 0.05) if ro_std is not None else None,
        src_f,
        "Standard deviation of annual ROIC divided by its mean (lower = more persistent returns).",
    )

    rev = fin.annual_series("revenue")
    vals["revenue_growth"] = (
        (rev[-1][1] / rev[-2][1] - 1) if len(rev) >= 2 and rev[-2][1] > 0 else None,
        src_f,
        None,
    )
    vals["revenue_cagr_3y"] = (series_cagr(rev, 3), src_f, None)
    vals["eps_cagr_3y"] = (series_cagr(fin.annual_series("eps_diluted"), 3), src_f, None)
    vals["fcf_cagr_3y"] = (series_cagr(fin.annual_series("fcf"), 3), src_f, None)
    ffo_ps = []
    for p in a:
        ni, dna, sh = p.get("net_income"), p.get("dna"), p.get("shares_diluted")
        if ni is not None and dna is not None and sh:
            ffo_ps.append((p.end, (ni + dna - (p.get("gain_on_sale_re") or 0.0)) / sh))
    vals["ffo_per_share_cagr_3y"] = (series_cagr(ffo_ps, 3), src_f, None)

    # adjusted vs GAAP EPS gap (last 4 reported quarters)
    gap = None
    if not ctx.pit:
        ev = ctx.data.earnings(ctx.ticker)
        if ev.value:
            gaps = []
            reported = [e for e in ev.value if e.eps_actual is not None and e.date <= ctx.as_of][-4:]
            for e in reported:
                gq = next(
                    (
                        p
                        for p in reversed(fin.quarterly)
                        if timedelta(0) <= (e.date - p.end) <= timedelta(days=75)
                    ),
                    None,
                )
                g_eps = gq.get("eps_diluted") if gq else None
                if g_eps is None:
                    continue
                denom = max(abs(e.eps_actual), abs(g_eps), 1e-9)
                gaps.append(abs(e.eps_actual - g_eps) / denom)
            gap = float(np.mean(gaps)) if len(gaps) >= 2 else None
            ctx.sources.setdefault("earnings", ev.meta())
    vals["gaap_adjusted_gap"] = (
        gap,
        "earnings provider vs. SEC EPS",
        "Average gap between the adjusted EPS the provider reports and GAAP diluted EPS over the last four quarters.",
    )

    # estimate revisions (needs accumulated daily snapshots)
    vals["estimate_revision"] = (estimate_revision(ctx), "consensus snapshots", None)

    # valuation vs peers & history
    peers = _safe_section(ctx, "peers")
    company = _safe_section(ctx, "company")
    if peers and company:
        med = peers.get("medians") or {}
        st = company["stats"]
        subj = peers["rows"][0]["metrics"]
        pe_now = st["pe"]["value"]
        vals["pe_vs_peers"] = (
            div(pe_now, med.get("pe")) if pe_now and med.get("pe") else None,
            "peer table",
            None,
        )
        ev_now = st["ev_ebitda"]["value"]
        vals["ev_ebitda_vs_peers"] = (
            div(ev_now, med.get("ev_ebitda")) if ev_now and med.get("ev_ebitda") else None,
            "peer table",
            None,
        )
        vals["ev_sales_vs_peers"] = (
            div(subj.get("ev_sales"), med.get("ev_sales"))
            if subj.get("ev_sales") and med.get("ev_sales")
            else None,
            "peer table",
            None,
        )
        vals["p_fcf_vs_peers"] = (
            div(subj.get("p_fcf"), med.get("p_fcf")) if subj.get("p_fcf") and med.get("p_fcf") else None,
            "peer table",
            None,
        )
        vals["pb_vs_peers"] = (
            div(subj.get("p_b"), med.get("p_b")) if subj.get("p_b") and med.get("p_b") else None,
            "peer table",
            None,
        )
    hist = multiple_history(fin, ctx.prices)
    for key, mid in (
        ("pe", "pe_vs_history"),
        ("ev_sales", "ev_sales_vs_history"),
        ("p_ffo", "p_ffo_vs_history"),
    ):
        stats = band_stats(hist, key, 5, ctx.as_of)
        cur = current_multiple(ctx, key)
        vals[mid] = (
            zscore(cur, stats),
            "own history (point-in-time)",
            None if stats else "fewer than 8 historical quarters",
        )
    val = _safe_section(ctx, "valuation")
    up = None
    if val and val.get("intrinsic", {}).get("value") and ctx.last_price:
        up = val["intrinsic"]["value"] / ctx.last_price - 1
    vals["dcf_upside"] = (up, "app valuation", None)
    vals["model_upside"] = (up, "app valuation", None)
    if val and val.get("wacc", {}).get("value") is not None and ttm.get("roic") is not None:
        vals["roic_minus_wacc"] = (ttm["roic"] - val["wacc"]["value"], "app valuation", None)
    else:
        vals["roic_minus_wacc"] = (None, None, "needs the valuation engine's WACC")

    # momentum
    px = ctx.prices
    adj = px["adj_close"] if not px.empty else None
    vals["momentum_12_1"] = (momentum_12_1(adj) if adj is not None else None, src_p, None)
    rs = None
    if adj is not None and not ctx.sector_prices.empty:
        a6, s6 = total_return(adj, 126), total_return(ctx.sector_prices["adj_close"], 126)
        rs = (a6 - s6) if (a6 is not None and s6 is not None) else None
    vals["rel_strength_6m"] = (rs, f"{src_p}; sector proxy {ctx.benchmark_tickers()[1]}", None)
    vals["trend_score"] = (trend_score(px["close"]) if not px.empty else None, src_p, None)

    # sentiment
    news = _safe_section(ctx, "news")
    vals["news_sentiment_30d"] = (
        (news or {}).get("sentiment_30d"),
        "news analysis",
        None if news else "news sentiment not available",
    )
    vals["insider_net_buying"] = insider_net_buying(ctx)
    si_pct, dtc, si_src = short_interest_metrics(ctx)
    vals["short_interest_pct_float"] = (si_pct, si_src, None)
    vals["days_to_cover"] = (dtc, si_src, None)

    # analysts
    an = _safe_section(ctx, "analysts")
    if an:
        vals["upside_trusted_consensus"] = (an.get("trusted_upside"), "analyst data", None)
        vals["trust_weighted_rating"] = (an.get("trust_weighted_rating"), "analyst data", None)
    mg = _safe_section(ctx, "earnings")
    vals["guidance_hit_rate"] = ((mg or {}).get("guidance_hit_rate"), "earnings history", None)

    # risk
    if adj is not None:
        vals["volatility_1y"] = (realized_vol(adj), src_p, None)
        dd = max_drawdown(adj, 756)
        vals["max_drawdown_3y"] = (dd["max_drawdown"] if dd else None, src_p, None)
        vals["downside_deviation"] = (downside_deviation(adj), src_p, None)
        b = (
            beta_regression(adj, ctx.market_prices["adj_close"], years=3)
            if not ctx.market_prices.empty
            else None
        )
        vals["beta"] = (b["adjusted"] if b else None, f"{src_p}; {ctx.benchmark_tickers()[2]}", None)
    return vals


def current_multiple(ctx: ReportContext, key: str) -> float | None:
    fin = ctx.fin
    mcap = ctx.market_cap
    t = fin.ttm
    if mcap is None:
        return None
    if key == "pe":
        ni = t.get("net_income")
        return mcap / ni if ni and ni > 0 else None
    if key == "ev_sales":
        nd = t.get("net_debt")
        rev = t.get("revenue")
        return (mcap + nd) / rev if (nd is not None and rev) else None
    if key == "p_ffo":
        ni, dna = t.get("net_income"), t.get("dna")
        if ni is None or dna is None:
            return None
        ffo = ni + dna - (t.get("gain_on_sale_re") or 0.0)
        return mcap / ffo if ffo > 0 else None
    return None


def estimate_revision(ctx: ReportContext, days: int = 90) -> float | None:
    if ctx.pit:
        return None
    rows = [r for r in ctx.data.estimate_history(ctx.ticker) if r["metric"] == "annual:eps"]
    if not rows:
        return None
    periods = sorted({r["period_end"] for r in rows if r["period_end"] > ctx.as_of})
    if not periods:
        return None
    cur_p = periods[0]
    series = sorted(
        (r["as_of"], r["mean"]) for r in rows if r["period_end"] == cur_p and r["mean"] is not None
    )
    if len(series) < 2 or (series[-1][0] - series[0][0]).days < days * 0.8:
        return None
    base = next((m for d, m in series if (series[-1][0] - d).days <= days), series[0][1])
    return (series[-1][1] - base) / abs(base) if base else None


def insider_net_buying(ctx: ReportContext) -> tuple[float | None, str | None, str | None]:
    txs = ctx.insiders
    if txs is None:
        return None, None, ctx.missing.get("insiders")
    since = ctx.as_of - timedelta(days=182)
    buys = sum(
        (t.shares * (t.price or 0)) for t in txs if t.code == "P" and t.tx_date >= since and not t.derivative
    )
    sells = sum(
        (t.shares * (t.price or 0))
        for t in txs
        if t.code == "S" and t.tx_date >= since and not t.derivative and not t.plan_10b5_1
    )
    mcap = ctx.market_cap
    if not mcap:
        return None, None, "market cap unavailable"
    return (
        (buys - sells) / mcap,
        ctx.sources.get("insiders", {}).get("source"),
        ("Open-market purchases minus discretionary sales (10b5-1 plan sales excluded) over 6 months."),
    )


def short_interest_metrics(ctx: ReportContext) -> tuple[float | None, float | None, str | None]:
    fx = ctx.data.short_interest(ctx.ticker)
    ctx.sources["short_interest"] = fx.meta()
    pts = [
        p
        for p in (fx.value or [])
        if p.settlement_date
        <= ctx.as_of - timedelta(days=int(ctx.cfg.get("pit.short_interest_lag_days", 12)))
    ]
    if not pts:
        return None, None, fx.source
    last = pts[-1]
    float_sh = None
    if not ctx.pit:
        fl = ctx.data.shares_float(ctx.ticker).value
        float_sh = fl.get("floatShares") if isinstance(fl, dict) else None
    denom = float_sh or ctx.shares_outstanding[0]
    return (last.short_interest / denom if denom else None), last.days_to_cover, fx.source


def compute_trust(ctx: ReportContext, quality_scores: dict, flags: dict) -> dict:
    cfg = ctx.cfg["trust_rating"]
    prof = ctx.sector.profile
    base_prof = ctx.sector.base_profile
    weights = cfg["weights"].get(prof) or cfg["weights"].get(base_prof) or cfg["weights"]["default"]
    min_n = int(cfg["min_universe"])
    specs = cfg["metrics"]
    values = collect_values(ctx, quality_scores)
    triggered = {f["id"] for f in flags.get("triggered", [])}
    penalties = cfg["red_flag_penalties"]
    pillars: list[PillarScore] = []

    for pid, label in cfg["pillar_labels"].items():
        plist = cfg["pillars"][pid]
        metric_ids = plist.get(prof) or plist.get(base_prof) or plist["default"]
        ms: list[MetricScore] = []
        for mid in metric_ids:
            spec = specs[mid]
            value, source, note = values.get(mid, (None, None, None))
            if value is not None and isinstance(value, float) and math.isnan(value):
                value = None
            pop = _population(ctx, spec.get("universe"))
            score = pct = None
            basis = None
            n = None
            if value is not None:
                if len(pop) >= min_n:
                    pct = percentile_of(value, pop, spec["direction"] == "higher")
                    score, basis, n = pct, "sector", len(pop)
                else:
                    score, basis = anchor_score(value, spec["anchors"]), "anchor"
            m = MetricScore(
                mid,
                spec["label"],
                spec["unit"],
                value,
                score,
                basis,
                pct,
                n,
                source,
                note=note if value is not None else None,
                reason=None if value is not None else (note or "insufficient data"),
            )
            if score is not None:
                m.target_up = _target(spec, pop, min_n, 60.0) if score < 60 else None
                m.target_down = _target(spec, pop, min_n, 40.0) if score > 40 else None
            ms.append(m)
        scored = [m for m in ms if m.score is not None]
        pscore = float(np.mean([m.score for m in scored])) if scored else None
        capped = []
        if pscore is not None:
            for fid, pen in penalties.items():
                if fid in triggered and pen["pillar"] == pid and pscore > pen["cap"]:
                    pscore = float(pen["cap"])
                    capped.append(fid)
        w = float(weights.get(pid, 0.0))
        p = PillarScore(pid, label, pscore, w, 0.0, ms, capped)
        p.explanation, p.raise_if, p.lower_if = _explain_pillar(ctx, p, scored)
        pillars.append(p)

    avail = [p for p in pillars if p.score is not None and p.weight > 0]
    total_w = sum(p.weight for p in avail)
    for p in avail:
        p.effective_weight = p.weight / total_w if total_w else 0.0
    raw = sum(p.score * p.effective_weight for p in avail) if avail else None
    deductions = [
        {"flag": fid, "points": pen["overall"]} for fid, pen in penalties.items() if fid in triggered
    ]
    ded = min(sum(d["points"] for d in deductions), float(cfg.get("max_total_deduction", 20)))
    score = max(0.0, min(100.0, raw - ded)) if raw is not None else None
    coverage = total_w / sum(float(weights.get(p.id, 0)) for p in pillars) if pillars else 0.0
    grade = grade_for(score, cfg["grade_bands"])
    missing = [
        {"id": p.id, "label": p.label, "reason": _missing_reason(p)} for p in pillars if p.score is None
    ]
    return {
        "score": score,
        "raw_score": raw,
        "grade": grade,
        "coverage": coverage,
        "deductions": deductions,
        "profile": prof,
        "weights": weights,
        "pillars": [_pillar_dict(p) for p in pillars],
        "missing_pillars": missing,
        "method": (
            "Weighted mean of pillar scores (weights for the "
            f"{ctx.sector.profile_label} profile, renormalized over pillars with data), minus red-flag deductions. "
            "Metrics are sector percentiles when at least "
            f"{min_n} industry peers report them, otherwise mapped between documented anchors."
        ),
    }


def _target(spec: dict, pop: list[float], min_n: int, score: float) -> dict | None:
    if len(pop) >= min_n:
        p = score if spec["direction"] == "higher" else 100 - score
        v = float(np.percentile(np.clip(pop, *np.percentile(pop, [1, 99])), p))
        return {"value": v, "basis": f"sector {int(score)}th-percentile level"}
    return {"value": anchor_inverse(score, spec["anchors"]), "basis": f"anchor level scoring {int(score)}"}


_PROPER = {
    "Altman",
    "Piotroski",
    "Beneish",
    "EPS",
    "FCF",
    "ROIC",
    "ROE",
    "P/E",
    "P/B",
    "P/FCF",
    "P/FFO",
    "EV/EBITDA",
    "EV/Sales",
    "FFO",
    "GAAP",
}


def _lc(label: str) -> str:
    """Lowercase a label's first word for mid-sentence use, keeping names and acronyms intact."""
    first = label.split(" ", 1)[0]
    if first in _PROPER or (len(first) > 1 and first[1:].lower() != first[1:]):
        return label
    return label[0].lower() + label[1:]


def _band(score: float) -> str:
    if score >= 75:
        return "strong"
    if score >= 60:
        return "above average"
    if score >= 40:
        return "about average"
    if score >= 25:
        return "below average"
    return "weak"


def _fmt(v: float | None, unit: str) -> str:
    if v is None:
        return "n/a"
    if unit == "pct":
        return f"{v * 100:.1f}%"
    if unit == "x":
        return f"{v:.2f}×"
    if unit == "days":
        return f"{v:.1f} days"
    if unit == "score":
        return f"{v:.0f}"
    return f"{v:.2f}"


def _explain_pillar(
    ctx: ReportContext, p: PillarScore, scored: list[MetricScore]
) -> tuple[str, str | None, str | None]:
    if p.score is None:
        return f"{p.label}: insufficient data ({_missing_reason(p)}).", None, None
    best = max(scored, key=lambda m: m.score)
    worst = min(scored, key=lambda m: m.score)
    rel = "vs. the sector" if any(m.basis == "sector" for m in scored) else "on absolute benchmarks"
    text = f"{p.label} is {_band(p.score)} {rel} ({p.score:.0f}/100). Strongest: {_lc(best.label)} at {_fmt(best.value, best.unit)}"
    if worst is not best:
        text += f"; weakest: {_lc(worst.label)} at {_fmt(worst.value, worst.unit)}"
    text += "."
    if p.capped_by:
        text += f" Capped because of red flag(s): {', '.join(p.capped_by)}."
    k = len(scored)
    raise_if = lower_if = None
    if worst.target_up and worst.score is not None:
        gain = (60 - worst.score) / k
        raise_if = (
            f"If {_lc(worst.label)} moved from {_fmt(worst.value, worst.unit)} to {_fmt(worst.target_up['value'], worst.unit)} "
            f"({worst.target_up['basis']}), this pillar would rise about {gain:.0f} points."
        )
    if best.target_down and best.score is not None and best is not worst:
        loss = (best.score - 40) / k
        lower_if = (
            f"If {_lc(best.label)} moved from {_fmt(best.value, best.unit)} to {_fmt(best.target_down['value'], best.unit)} "
            f"({best.target_down['basis']}), this pillar would fall about {loss:.0f} points."
        )
    return text, raise_if, lower_if


def _missing_reason(p: PillarScore) -> str:
    reasons = [m.reason for m in p.metrics if m.reason]
    return "; ".join(dict.fromkeys(reasons))[:300] or "no inputs available"


def _pillar_dict(p: PillarScore) -> dict[str, Any]:
    return {
        "id": p.id,
        "label": p.label,
        "score": p.score,
        "weight": p.weight,
        "effective_weight": p.effective_weight,
        "capped_by": p.capped_by,
        "explanation": p.explanation,
        "raise_if": p.raise_if,
        "lower_if": p.lower_if,
        "metrics": [
            {
                "id": m.id,
                "label": m.label,
                "unit": m.unit,
                "value": m.value,
                "score": m.score,
                "basis": m.basis,
                "percentile": m.percentile,
                "n": m.n,
                "source": m.source,
                "note": m.note,
                "reason": m.reason,
            }
            for m in p.metrics
        ],
    }


def quality_scores(ctx: ReportContext) -> dict:
    fin = ctx.fin
    a = fin.annual
    out: dict[str, Any] = {}
    financial = ctx.sector.is_financial
    if len(a) >= 1 and not financial:
        manufacturer = ctx.sector.sic is not None and 2000 <= ctx.sector.sic <= 3999
        latest = a[-1]
        mcap = ctx.market_cap
        z = q.altman_z(latest, mcap, manufacturer)
        out["altman"] = {**z.__dict__, "period": latest.label}
    if len(a) >= 2:
        f = q.piotroski_f(a[-1], a[-2], a[-3] if len(a) >= 3 else None)
        out["piotroski"] = {**f.__dict__, "period": a[-1].label}
        if not financial:
            m = q.beneish_m(a[-1], a[-2])
            out["beneish"] = {**m.__dict__, "period": a[-1].label}
        no_accruals = ctx.sector.profile in ("bank", "insurer", "financial_other")
        out["accruals_ratio"] = None if no_accruals else q.accruals_ratio(a[-1], a[-2])
    out["interest_coverage"] = ttm_ratios(fin).get("interest_coverage")
    return out
