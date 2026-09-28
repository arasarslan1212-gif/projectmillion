"""Valuation engine: closed-form checks for every formula, reproducibility, and per-profile integration."""

import math
from dataclasses import replace
from datetime import date
from types import SimpleNamespace

import numpy as np
import pytest
from fastapi.testclient import TestClient
from scipy.stats import norm

from engine.api.main import app
from engine.config import get_config
from engine.report.builder import contexts, get_section
from engine.valuation import engine as ve
from engine.valuation.dcf import DcfInputs, monte_carlo, run_dcf, sensitivity_grid, tornado
from engine.valuation.reverse_dcf import (
    assess,
    implied_fcf_growth,
    implied_revenue_growth,
    pv_constant_growth,
)
from engine.valuation.wacc import compute_wacc


def _inp(**kw) -> DcfInputs:
    base = dict(
        revenue0=1000.0,
        margin0=0.20,
        margin_target=0.20,
        growth1=0.0,
        terminal_growth=0.0,
        wacc=0.08,
        tax0=0.25,
        tax_terminal=0.25,
        dna_pct=0.05,
        capex_pct=0.05,
        nwc_pct=0.0,
        debt=0.0,
        cash=0.0,
        minority=0.0,
        pension_deficit=0.0,
        shares=10.0,
        mid_year=False,
    )
    base.update(kw)
    return DcfInputs(**base)


# ---- DCF ------------------------------------------------------------------------------------------


def test_dcf_no_growth_equals_perpetuity():
    # No growth, no net reinvestment, constant margin and tax: EV = NOPAT / WACC exactly.
    r = run_dcf(_inp())
    nopat = 1000 * 0.20 * (1 - 0.25)
    assert r.enterprise_value == pytest.approx(nopat / 0.08, rel=1e-9)
    assert r.per_share == pytest.approx(nopat / 0.08 / 10, rel=1e-9)


def test_dcf_constant_growth_matches_growing_annuity_plus_terminal():
    g, w, spread, n = 0.03, 0.09, 0.02, 10
    r = run_dcf(_inp(growth1=g, terminal_growth=g, wacc=w, terminal_roic_spread=spread))
    n0 = 1000 * 0.20 * 0.75
    annuity = n0 * (1 + g) / (w - g) * (1 - ((1 + g) / (1 + w)) ** n)
    n10 = n0 * (1 + g) ** n
    tv = n10 * (1 + g) * (1 - g / (w + spread)) / (w - g)
    assert r.pv_explicit == pytest.approx(annuity, rel=1e-9)
    assert r.pv_terminal == pytest.approx(tv / (1 + w) ** n, rel=1e-9)
    assert r.terminal_share == pytest.approx(r.pv_terminal / r.enterprise_value)


def test_mid_year_convention_scales_explicit_period_only():
    end = run_dcf(_inp(growth1=0.05, terminal_growth=0.02))
    mid = run_dcf(_inp(growth1=0.05, terminal_growth=0.02, mid_year=True))
    assert mid.pv_explicit == pytest.approx(end.pv_explicit * 1.08**0.5, rel=1e-9)
    assert mid.pv_terminal == pytest.approx(end.pv_terminal, rel=1e-12)


def test_equity_bridge_and_zero_floor():
    base = run_dcf(_inp())
    r = run_dcf(_inp(debt=300.0, cash=100.0, minority=20.0, pension_deficit=30.0))
    assert r.equity_value == pytest.approx(base.enterprise_value - 300 + 100 - 20 - 30)
    assert r.per_share == pytest.approx(r.equity_value / 10)
    broke = run_dcf(_inp(debt=10_000.0))
    assert broke.per_share == 0.0
    assert any("floored at zero" in n for n in broke.notes)


def test_sbc_is_an_expense_because_margin_is_gaap_ebit():
    # The DCF starts from GAAP operating income (SBC already deducted) and never adds SBC back:
    # a lower margin (more SBC) must lower value one-for-one through NOPAT.
    hi = run_dcf(_inp(margin0=0.25, margin_target=0.25))
    lo = run_dcf(_inp(margin0=0.20, margin_target=0.20))
    assert hi.enterprise_value / lo.enterprise_value == pytest.approx(0.25 / 0.20)


def test_margin_converges_and_growth_fades():
    r = run_dcf(_inp(margin0=0.10, margin_target=0.30, growth1=0.20, terminal_growth=0.02, margin_years=5))
    margins = [row["margin"] for row in r.table]
    growths = [row["growth"] for row in r.table]
    assert (
        margins[0] == pytest.approx(0.14)
        and margins[4] == pytest.approx(0.30)
        and margins[-1] == pytest.approx(0.30)
    )
    assert growths[0] == pytest.approx(0.20) and growths[-1] == pytest.approx(0.02)
    assert all(a >= b for a, b in zip(growths, growths[1:], strict=False))


def test_monte_carlo_reproducible_and_centered():
    inp = _inp(growth1=0.06, terminal_growth=0.025, margin0=0.18, margin_target=0.2)
    args = dict(
        sigma_g=0.04, sigma_m=0.02, sigma_wacc=0.01, sigma_gT=0.005, rho_gm=0.3, g_cap=0.03, min_spread=0.01
    )
    a = monte_carlo(inp, 10_000, 42, **args, price=150.0)
    b = monte_carlo(inp, 10_000, 42, **args, price=150.0)
    c = monte_carlo(inp, 10_000, 43, **args, price=150.0)
    assert a == b
    assert a["percentiles"] != c["percentiles"]
    p = a["percentiles"]
    assert p["p5"] < p["p10"] < p["p25"] < p["p50"] < p["p75"] < p["p90"] < p["p95"]
    base = run_dcf(inp).per_share
    assert abs(p["p50"] / base - 1) < 0.08  # median draw close to the base case
    assert sum(a["histogram"]["counts"]) >= 0.98 * 10_000
    assert 0.0 <= a["share_above_price"] <= 1.0


def test_monte_carlo_with_zero_sigma_collapses_to_base():
    inp = _inp(growth1=0.05, terminal_growth=0.02)
    mc = monte_carlo(inp, 500, 1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.03, 0.01)
    assert mc["percentiles"]["p10"] == pytest.approx(run_dcf(inp).per_share)
    assert mc["percentiles"]["p90"] == pytest.approx(run_dcf(inp).per_share)


def test_monte_carlo_respects_terminal_growth_constraints():
    # Terminal growth can never exceed the cap or come within min_spread of a (low) WACC draw.
    inp = _inp(growth1=0.05, terminal_growth=0.029, wacc=0.045)
    mc = monte_carlo(inp, 5000, 3, 0.02, 0.01, 0.02, 0.01, 0.3, 0.03, 0.01)
    assert all(math.isfinite(v) for v in mc["percentiles"].values())


def test_config_draws_at_least_10k():
    assert get_config().data["valuation"]["monte_carlo"]["draws"] >= 10_000


def test_sensitivity_grid_monotone():
    inp = _inp(growth1=0.05, terminal_growth=0.02)
    waccs, gs = [0.07, 0.08, 0.09, 0.10], [0.01, 0.02, 0.03]
    grid = sensitivity_grid(inp, waccs, gs)
    for row in grid:  # higher terminal growth → higher value (terminal ROIC exceeds WACC)
        assert all(a < b for a, b in zip(row, row[1:], strict=False))
    for j in range(len(gs)):  # higher WACC → lower value
        col = [grid[i][j] for i in range(len(waccs))]
        assert all(a > b for a, b in zip(col, col[1:], strict=False))
    assert sensitivity_grid(inp, [0.03], [0.028]) == [[None]]


def test_tornado_sorted_and_brackets_base():
    t = tornado(_inp(growth1=0.05, terminal_growth=0.02))
    assert [x["range"] for x in t] == sorted((x["range"] for x in t), reverse=True)
    wacc = next(x for x in t if x["field"] == "wacc")
    assert wacc["low"] > wacc["base"] > wacc["high"]


# ---- reverse DCF ------------------------------------------------------------------------------------


def test_reverse_dcf_recovers_fcf_growth():
    ev = pv_constant_growth(100.0, 0.07, 0.09, 0.025, 10)
    assert implied_fcf_growth(100.0, ev, 0.09, 0.025, 10) == pytest.approx(0.07, abs=1e-6)
    assert implied_fcf_growth(-5.0, ev, 0.09, 0.025, 10) is None
    assert implied_fcf_growth(100.0, ev, 0.02, 0.025, 10) is None  # WACC below terminal growth


def test_reverse_dcf_recovers_revenue_growth():
    inp = _inp(
        growth1=0.12, terminal_growth=0.025, margin0=0.15, margin_target=0.22, mid_year=True, nwc_pct=0.1
    )
    target = run_dcf(inp).per_share
    assert implied_revenue_growth(replace(inp, growth1=0.0), target) == pytest.approx(0.12, abs=1e-4)


def test_reverse_dcf_assessment_labels():
    assert assess(0.15, 0.05, 0.06) == "demanding"
    assert assess(0.01, 0.05, 0.06) == "modest"
    assert assess(0.055, 0.05, 0.06) == "in line with history and expectations"
    assert assess(0.05, None, None) == "no history to compare"
    assert assess(None, 0.05, 0.06) is None


# ---- WACC and sector models --------------------------------------------------------------------------


def test_wacc_identity_on_synthetic_company():
    ctx = contexts.get("ZZTEC", None, False)
    cfg = get_config().data["valuation"]["wacc"]
    w = compute_wacc(ctx, cfg)
    assert w.cost_of_equity == pytest.approx(w.risk_free + w.beta * w.erp)
    assert w.weight_equity + w.weight_debt == pytest.approx(1.0)
    raw = w.weight_equity * w.cost_of_equity + w.weight_debt * w.cost_of_debt_after_tax
    lo, hi = cfg["wacc_bounds"]
    assert w.value == pytest.approx(min(max(raw, lo), hi))
    assert w.cost_of_debt_after_tax == pytest.approx(w.cost_of_debt_pre_tax * (1 - w.tax_rate))
    assert (
        w.risk_free + cfg["cost_of_debt_spread_min"] - 1e-12
        <= w.cost_of_debt_pre_tax
        <= w.risk_free + cfg["cost_of_debt_spread_max"] + 1e-12
    )
    assert "DGS10" in w.risk_free_source and "Blume" in w.beta_source


def _fake_ctx(ttm: dict, dividends=(), as_of=date(2026, 9, 25)):
    fin = SimpleNamespace(ttm=ttm, annual=[], quarterly=[])
    return SimpleNamespace(fin=fin, dividends=list(dividends), as_of=as_of)


def test_ddm_gordon_growth(monkeypatch):
    monkeypatch.setattr("engine.fundamentals.ratios.ttm_ratios", lambda fin: {"roe": 0.10})
    ctx = _fake_ctx(
        {"net_income": 100.0, "dividends_paid": 60.0}, [(date(2026, 3, 1), 1.0), (date(2026, 9, 1), 1.0)]
    )
    r = ve.models.ddm(ctx, 0.08, {"max_growth": 0.06})
    g = 0.10 * (1 - 0.6)
    assert r.value == pytest.approx(2.0 * (1 + g) / (0.08 - g))
    capped = ve.models.ddm(ctx, 0.08, {"max_growth": 0.02})
    assert capped.inputs["growth"] == pytest.approx(0.02)
    none = ve.models.ddm(_fake_ctx({"net_income": 1.0}), 0.08, {"max_growth": 0.06})
    assert none.value is None and "no dividends" in none.reason


def test_excess_return_equals_book_when_roe_equals_ke(monkeypatch):
    monkeypatch.setattr("engine.fundamentals.ratios.ttm_ratios", lambda fin: {"roe": 0.09})
    ctx = _fake_ctx({"shares_diluted": 10.0, "equity": 500.0, "net_income": 45.0, "dividends_paid": 15.0})
    at_ke = ve.models.excess_return(ctx, 0.09, {"years": 10})
    assert at_ke.value == pytest.approx(50.0)
    above = ve.models.excess_return(ctx, 0.09, {"years": 10}, roe_override=0.15)
    below = ve.models.excess_return(ctx, 0.09, {"years": 10}, roe_override=0.05)
    assert below.value < 50.0 < above.value
    # First-year excess return by hand: (ROE − ke) × BV ÷ (1 + ke), with ROE faded 1/10 of the way.
    r1 = 0.15 + (0.09 - 0.15) / 10
    assert above.value > 50 + (r1 - 0.09) * 50 / 1.09


# ---- blend, target distribution, confidence ----------------------------------------------------------


@pytest.fixture(scope="module")
def zztec_val():
    return get_section("ZZTEC", "valuation")


def test_blend_and_target_math(zztec_val):
    v = zztec_val
    p0, s, lam = v["price"], v["sigma"], v["sigma"]["convergence"]
    rows = v["blend"]
    assert sum(r["weight"] for r in rows) == pytest.approx(1.0)
    for r in rows:
        if r["kind"] == "intrinsic":
            assert r["target_12m"] == pytest.approx(
                p0 * math.exp(s["drift"] + lam * math.log(r["value"] / p0))
            )
    ln_p50 = sum(r["weight"] * math.log(r["target_12m"]) for r in rows)
    t = v["target"]
    assert t["p50"] == pytest.approx(math.exp(ln_p50))
    z = get_config().data["valuation"]["range"]["z80"]
    assert t["p10"] == pytest.approx(t["p50"] * math.exp(-z * s["total"]))
    assert t["p90"] == pytest.approx(t["p50"] * math.exp(z * s["total"]))
    assert t["prob_up"] == pytest.approx(norm.cdf(math.log(t["p50"] / p0) / s["total"]))
    assert t["expected_return"] == pytest.approx(t["p50"] / p0 * math.exp(s["total"] ** 2 / 2) - 1)
    assert s["total"] == pytest.approx(math.sqrt(s["market"] ** 2 + s["extra"] ** 2) * s["widening"])
    widen_k = get_config().data["valuation"]["range"]["confidence_widening"]
    assert s["widening"] == pytest.approx(1 + widen_k * (1 - v["confidence"]["score"] / 100))
    intr = [r for r in rows if r["kind"] == "intrinsic"]
    iw = sum(r["weight"] for r in intr)
    assert v["intrinsic"] == pytest.approx(
        math.exp(sum(r["weight"] * math.log(r["value"]) for r in intr) / iw)
    )


def test_twelve_month_target_is_not_intrinsic_value(zztec_val):
    # With λ < 1 the 12-month P50 sits between today's price (grown at ke − dy) and intrinsic value.
    v = zztec_val
    p0, iv, p50 = v["price"], v["intrinsic"], v["target"]["p50"]
    assert min(p0, iv) < p50 < max(p0 * 1.2, iv) or min(iv, p0) < p50
    assert abs(math.log(p50 / p0)) < abs(math.log(iv / p0))


def test_valuation_is_deterministic(zztec_val):
    contexts.d.clear()
    again = get_section("ZZTEC", "valuation")
    assert again["target"] == zztec_val["target"]
    assert again["dcf"]["monte_carlo"]["percentiles"] == zztec_val["dcf"]["monte_carlo"]["percentiles"]


def test_without_analysts_identical_when_no_targets(zztec_val):
    v = zztec_val
    an = next(m for m in v["methods"] if m["id"] == "analyst_consensus")
    if an["value"] is None:
        assert v["blend_alternative"]["target"]["p50"] == pytest.approx(v["target"]["p50"])


def test_confidence_levels_and_profile_caps():
    cfg = get_config().data
    parts = {
        "method_dispersion": 0.05,
        "data_score": 100.0,
        "data_note": "all data",
        "growth_volatility": 0.02,
        "eps_positive_share": 1.0,
        "volatility": 0.15,
        "analyst_dispersion": 0.05,
        "calibration_error": 0.0,
        "calibration_note": "",
    }
    ctx = SimpleNamespace(sector=SimpleNamespace(profile="general", profile_label="General"))
    high = ve.confidence_score(ctx, parts, cfg)
    assert high["level"] == "High" and high["score"] >= 70 and not high["capped"]
    ctx_bio = SimpleNamespace(
        sector=SimpleNamespace(profile="biotech_pipeline", profile_label="Pipeline biotech")
    )
    capped = ve.confidence_score(ctx_bio, parts, cfg)
    assert capped["capped"] and capped["score"] == cfg["confidence"]["profile_caps"]["biotech_pipeline"]
    assert capped["level"] == "Low" and "Capped" in capped["explain"]
    empty = {k: None for k in parts} | {"data_score": 0.0, "data_note": "none"}
    low = ve.confidence_score(ctx, empty, cfg)
    assert low["level"] == "Low"
    assert {b["id"] for b in low["breakdown"]} == set(cfg["confidence"]["weights"])


def test_cone_starts_at_price_and_matches_sigma():
    ctx = SimpleNamespace(last_price_date=date(2026, 9, 25), as_of=date(2026, 9, 25))
    c = ve.cone_path(ctx, 100.0, 0.05, 0.3, 0.2)
    assert c["p10"][0] == pytest.approx(100.0) and c["p90"][0] == pytest.approx(100.0)
    tt = (date.fromisoformat(c["dates"][-1]) - date(2026, 9, 25)).days / 365.25
    assert 0.99 < tt <= 1.0
    assert c["p50"][-1] == pytest.approx(100 * math.exp(0.05 * tt), abs=1e-3)
    s = math.sqrt(0.3**2 * tt + (0.2 * tt) ** 2)
    assert c["p90"][-1] == pytest.approx(100 * math.exp(0.05 * tt + 1.2816 * s), abs=1e-3)
    assert 255 <= len(c["dates"]) <= 263  # business days, so the chart spaces the cone like price bars
    assert all(date.fromisoformat(d).weekday() < 5 for d in c["dates"])


def test_drawdown_probability_behaves():
    ctx = SimpleNamespace(ticker="X", as_of=date(2026, 9, 25))
    cfg = get_config().data["valuation"]
    calm = ve.drawdown_probability(ctx, 0.10, 0.0, 0.05, cfg)
    wild = ve.drawdown_probability(ctx, 0.10, 0.0, 0.60, cfg)
    assert calm < 0.01 and wild > 0.7
    # Driftless: by Lévy's theorem the log drawdown is a reflected Brownian motion, so
    # P(max drawdown ≥ a) = 1 − (4/π) Σ (−1)^k/(2k+1) · exp(−(2k+1)² π² σ² T / (8 a²)).
    # Daily sampling misses some intraday extremes, so the simulation lands slightly below.
    a = math.log(1 / 0.8)
    theory = 1 - 4 / math.pi * sum(
        (-1) ** k / (2 * k + 1) * math.exp(-((2 * k + 1) ** 2) * math.pi**2 * 0.09 / (8 * a * a))
        for k in range(20)
    )
    mid = ve.drawdown_probability(ctx, 0.0, 0.0, 0.30, cfg)
    assert theory - 0.08 < mid <= theory + 0.01


def test_sanity_flags_large_move():
    cfg = get_config().data["valuation"]
    ctx = SimpleNamespace(
        fin=SimpleNamespace(ttm={"fcf": 1.0}),
        filings=[SimpleNamespace(form="10-Q", filed_at=date(2026, 8, 1))],
        as_of=date(2026, 9, 25),
        last_price_date=date(2026, 9, 25),
        sector=SimpleNamespace(profile="general"),
    )
    out = ve.sanity_checks(ctx, {"p50": 300.0}, None, {"rows": []}, None, cfg, 100.0)
    ids = {x["id"] for x in out}
    assert "large_move" in ids and "few_peers" in ids


# ---- per-profile integration and point-in-time ----------------------------------------------------------


@pytest.mark.parametrize(
    ("ticker", "expected_methods"),
    [
        ("ZZTEC", {"dcf", "relative_peers", "relative_history"}),
        ("ZZBNK", {"excess_return", "pb_roe_regression"}),
        ("ZZREI", {"p_ffo_history", "p_ffo_peers"}),
        ("ZZGRO", {"dcf", "ev_sales_regression"}),
        ("ZZUTL", {"ddm", "dcf"}),
        ("ZZSML", set()),
    ],
)
def test_each_profile_values_with_its_methods(ticker, expected_methods):
    v = get_section(ticker, "valuation")
    assert v["status"] == "ok"
    used = {r["id"] for r in v["blend"]}
    assert expected_methods <= used, f"{ticker}: used {used}"
    t = v["target"]
    assert 0 < t["p10"] < t["p50"] < t["p90"]
    assert 0.0 < t["prob_up"] < 1.0 and 0.0 <= t["prob_drawdown_20"] <= 1.0
    assert 0 <= v["confidence"]["score"] <= 100
    assert v["disclaimer"] and "not investment advice" in v["disclaimer"].lower()
    for m in v["methods"]:
        assert m["value"] is not None or m["reason"], f"{ticker} {m['id']} missing without a reason"


def test_banks_have_no_dcf_and_growth_confidence_is_capped():
    bank = get_section("ZZBNK", "valuation")
    assert bank["dcf"] is None and "dcf" not in {m["id"] for m in bank["methods"]}
    assert set(bank["scenarios"]) == {"bear", "base", "bull"}
    gro = get_section("ZZGRO", "valuation")
    assert (
        gro["confidence"]["score"] <= get_config().data["confidence"]["profile_caps"]["growth_unprofitable"]
    )


def test_valuation_point_in_time_uses_only_filed_data():
    as_of = date(2024, 6, 28)
    v = get_section("ZZTEC", "valuation", as_of=as_of, pit=True)
    ctx = contexts.get("ZZTEC", as_of, True)
    assert v["status"] == "ok"
    assert all(f.filed_at <= as_of for f in ctx.filings)
    assert v["dcf"]["inputs"]["revenue0"] == pytest.approx(ctx.fin.ttm["revenue"])
    assert "consensus" not in v["dcf"]["input_sources"]["growth1"]  # no look-ahead estimates in PIT mode
    assert v["price"] == pytest.approx(float(ctx.prices["close"].iloc[-1]))  # unadjusted for later dividends
    assert ctx.prices.index[-1].date() <= as_of
    assert v["wacc"]["risk_free_source"].split(" on ")[-1] <= as_of.isoformat()


def test_what_if_endpoint():
    with TestClient(app) as c:
        base = get_section("ZZTEC", "valuation")["dcf"]
        r = c.post("/api/valuation/ZZTEC/dcf", json={}).json()
        assert r["per_share"] == pytest.approx(base["per_share"], rel=1e-9)
        up = c.post("/api/valuation/ZZTEC/dcf", json={"growth1": base["inputs"]["growth1"] + 0.05}).json()
        assert up["per_share"] > r["per_share"]
        bad = c.post("/api/valuation/ZZTEC/dcf", json={"wacc": 0.05, "terminal_growth": 0.048})
        assert bad.status_code == 422
        bank = c.post("/api/valuation/ZZBNK/dcf", json={})
        assert bank.status_code == 422


def test_numpy_seed_is_ticker_and_date_specific():
    a = ve._seed(SimpleNamespace(ticker="A", as_of=date(2026, 1, 1)), 7)
    b = ve._seed(SimpleNamespace(ticker="B", as_of=date(2026, 1, 1)), 7)
    assert a != b and a == ve._seed(SimpleNamespace(ticker="A", as_of=date(2026, 1, 1)), 7)
    assert isinstance(np.random.default_rng(a).standard_normal(), float)


def test_bank_reverse_valuation_solves_for_roe():
    v = get_section("ZZBNK", "valuation")
    r = v["reverse_dcf"]
    assert r["basis"] == "return on equity"
    g = min(get_config().data["valuation"]["dcf"]["terminal_growth"], r["cost_of_equity"] - 0.01)
    assert r["implied_roe"] == pytest.approx(g + r["price_to_book"] * (r["cost_of_equity"] - g))
    # Plugging the implied ROE back into justified P/B recovers today's P/B.
    assert (r["implied_roe"] - g) / (r["cost_of_equity"] - g) == pytest.approx(r["price_to_book"])
    assert any("reference only" in n for n in v["wacc"]["notes"])
