"""Fundamentals: statements (annual/quarterly, up to 10 years), ratios, growth, quality metrics and
sector-specific KPIs."""

from __future__ import annotations

from engine.fundamentals.concepts import LINE_ITEMS
from engine.fundamentals.ratios import (
    RATIO_KEYS,
    growth_metrics,
    ratio_history,
    series_cagr,
    ttm_ratios,
    yoy,
)
from engine.report.context import ReportContext
from engine.report.metric import metric, missing, section

DERIVED_LABELS = {
    "ebit": "EBIT",
    "ebitda": "EBITDA",
    "fcf": "Free cash flow",
    "fcf_after_sbc": "FCF after stock comp",
    "total_debt": "Total debt",
    "net_debt": "Net debt",
    "tangible_equity": "Tangible equity",
    "working_capital": "Working capital",
    "invested_capital": "Invested capital",
    "cash_and_st": "Cash & short-term investments",
}

ROWS = {
    "general": {
        "income": [
            "revenue",
            "cost_of_revenue",
            "gross_profit",
            "rnd",
            "sga",
            "operating_income",
            "ebitda",
            "interest_expense",
            "pretax_income",
            "income_tax",
            "net_income",
            "eps_diluted",
            "shares_diluted",
        ],
        "balance": [
            "cash",
            "st_investments",
            "receivables",
            "inventory",
            "current_assets",
            "ppe",
            "goodwill",
            "intangibles",
            "total_assets",
            "accounts_payable",
            "current_liabilities",
            "total_debt",
            "total_liabilities",
            "equity",
            "retained_earnings",
        ],
        "cashflow": [
            "cfo",
            "capex",
            "fcf",
            "sbc",
            "fcf_after_sbc",
            "dna",
            "dividends_paid",
            "buybacks",
            "stock_issued",
            "acquisitions",
        ],
    },
    "bank": {
        "income": [
            "revenue",
            "interest_income",
            "interest_expense",
            "net_interest_income",
            "provision",
            "noninterest_income",
            "noninterest_expense",
            "pretax_income",
            "income_tax",
            "net_income",
            "eps_diluted",
            "shares_diluted",
        ],
        "balance": [
            "cash",
            "loans",
            "total_assets",
            "deposits",
            "total_debt",
            "total_liabilities",
            "equity",
            "goodwill",
            "intangibles",
            "tangible_equity",
        ],
        "cashflow": ["cfo", "capex", "dividends_paid", "buybacks"],
    },
    "reit": {
        "income": [
            "revenue",
            "operating_income",
            "dna",
            "interest_expense",
            "gain_on_sale_re",
            "net_income",
            "eps_diluted",
            "shares_diluted",
        ],
        "balance": ["cash", "ppe", "total_assets", "total_debt", "total_liabilities", "equity"],
        "cashflow": ["cfo", "capex", "re_acquisitions", "stock_issued", "dividends_paid"],
    },
    "insurer": {
        "income": [
            "revenue",
            "premiums_earned",
            "losses_incurred",
            "underwriting_expense",
            "pretax_income",
            "net_income",
            "eps_diluted",
            "shares_diluted",
        ],
        "balance": ["cash", "total_assets", "total_debt", "total_liabilities", "equity"],
        "cashflow": ["cfo", "capex", "dividends_paid", "buybacks"],
    },
}

UNITS = {
    "eps_diluted": "usd_per_share",
    "eps_basic": "usd_per_share",
    "dps": "usd_per_share",
    "shares_diluted": "shares",
    "shares_basic": "shares",
    "shares_outstanding": "shares",
}

RATIO_META = {
    "gross_margin": ("Gross margin", "pct"),
    "operating_margin": ("Operating margin", "pct"),
    "net_margin": ("Net margin", "pct"),
    "ebitda_margin": ("EBITDA margin", "pct"),
    "fcf_margin": ("FCF margin", "pct"),
    "roe": ("Return on equity", "pct"),
    "roa": ("Return on assets", "pct"),
    "roic": ("Return on invested capital", "pct"),
    "rotce": ("Return on tangible common equity", "pct"),
    "debt_to_equity": ("Debt / equity", "x"),
    "net_debt_to_ebitda": ("Net debt / EBITDA", "x"),
    "interest_coverage": ("Interest coverage", "x"),
    "debt_to_assets": ("Debt / assets", "pct"),
    "equity_to_assets": ("Equity / assets", "pct"),
    "current_ratio": ("Current ratio", "x"),
    "quick_ratio": ("Quick ratio", "x"),
    "asset_turnover": ("Asset turnover", "x"),
    "dso": ("Days sales outstanding", "days"),
    "dio": ("Days inventory outstanding", "days"),
    "dpo": ("Days payables outstanding", "days"),
    "ccc": ("Cash conversion cycle", "days"),
    "fcf_conversion": ("FCF conversion (FCF / net income)", "pct"),
    "sbc_pct_revenue": ("Stock comp % of revenue", "pct"),
    "capex_intensity": ("Capex % of revenue", "pct"),
    "nwc_pct_revenue": ("Working capital % of revenue", "pct"),
    "effective_tax_rate": ("Effective tax rate", "pct"),
    "nim": ("Net interest margin (on assets)", "pct"),
    "efficiency_ratio": ("Efficiency ratio", "pct"),
    "loan_to_deposit": ("Loans / deposits", "pct"),
    "combined_ratio": ("Combined ratio", "pct"),
    "ffo": ("FFO", "usd"),
    "affo": ("AFFO (approx.)", "usd"),
    "ffo_margin": ("FFO margin", "pct"),
}


def growth_label(k: str) -> str:
    names = {
        "revenue": "Revenue",
        "eps": "EPS",
        "fcf": "Free cash flow",
        "net_income": "Net income",
        "dps": "Dividend per share",
        "shares": "Share count",
    }
    if k.endswith("_yoy_q"):
        return f"{names.get(k[:-6], k)} growth (latest quarter vs. a year earlier)"
    base, _, yrs = k.rpartition("_cagr_")
    n = yrs.rstrip("y")
    return f"{names.get(base, base)} growth (1y)" if n == "1" else f"{names.get(base, base)} CAGR ({n}y)"


def _label(key: str) -> str:
    if key in LINE_ITEMS:
        return LINE_ITEMS[key].label
    return DERIVED_LABELS.get(key, key)


def _statements(ctx: ReportContext, kind: str, rows_by_stmt: dict, n: int) -> dict:
    fin = ctx.fin
    periods = (fin.annual if kind == "annual" else fin.quarterly)[-n:]
    cols = [
        {
            "label": p.label,
            "end": p.end.isoformat(),
            "filed": max(p.filed.values()).isoformat() if p.filed else None,
        }
        for p in periods
    ]
    out = {}
    for stmt, keys in rows_by_stmt.items():
        rows = []
        for key in keys:
            vals = [p.values.get(key) for p in periods]
            if all(v is None for v in vals):
                continue
            base_key = "total_assets" if stmt == "balance" else "revenue"
            common = [
                (v / p.values[base_key]) if (v is not None and p.values.get(base_key)) else None
                for v, p in zip(vals, periods, strict=True)
            ]
            prev_offset = 1 if kind == "annual" else 4
            full = fin.annual if kind == "annual" else fin.quarterly
            start = len(full) - len(periods)
            yoys = []
            for i in range(len(periods)):
                j = start + i - prev_offset
                prev = full[j].values.get(key) if j >= 0 else None
                yoys.append(yoy(vals[i], prev))
            concept = next((p.concepts.get(key) for p in reversed(periods) if p.concepts.get(key)), None)
            derived = next((p.derived.get(key) for p in reversed(periods) if p.derived.get(key)), None)
            series = fin.annual_series(key)
            rows.append(
                {
                    "key": key,
                    "label": _label(key),
                    "unit": UNITS.get(key, "usd"),
                    "values": vals,
                    "yoy": yoys,
                    "common_size": common,
                    "concept": concept,
                    "derived": derived,
                    "cagr": {f"{y}y": series_cagr(series, y) for y in (3, 5, 10)}
                    if kind == "annual"
                    else None,
                }
            )
        out[stmt] = rows
    return {"columns": cols, "statements": out}


def _ratio_table(ctx: ReportContext) -> dict:
    ann, qtr = ratio_history(ctx.fin)
    ttm = ttm_ratios(ctx.fin)
    keys = [
        k
        for k in RATIO_KEYS
        if any(r["ratios"].get(k) is not None for r in ann[-10:]) or ttm.get(k) is not None
    ]
    return {
        "columns": [r["label"] for r in ann[-10:]],
        "rows": [
            {
                "key": k,
                "label": RATIO_META.get(k, (k, "ratio"))[0],
                "unit": RATIO_META.get(k, (k, "ratio"))[1],
                "ttm": ttm.get(k),
                "values": [r["ratios"].get(k) for r in ann[-10:]],
            }
            for k in keys
        ],
        "quarterly": {
            "columns": [r["label"] for r in qtr[-12:]],
            "rows": {k: [r["ratios"].get(k) for r in qtr[-12:]] for k in keys},
        },
    }


def sector_kpis(ctx: ReportContext) -> list[dict]:
    fin = ctx.fin
    prof = ctx.sector.profile
    ttm = ttm_ratios(fin)
    src = ctx.sources.get("fundamentals", {}).get("source")
    asof = fin.ttm_end
    not_tagged = "not reported in standardized XBRL company facts (company-specific disclosure)"
    k: list[dict] = []

    def m(id_, label, value, unit, reason=None, note=None):
        return metric(
            id_, label, value, unit, source=src, as_of=asof, reason=reason or "insufficient data", note=note
        )

    if prof == "bank":
        k.append(
            m(
                "nim",
                "Net interest margin",
                ttm.get("nim"),
                "pct",
                note="Net interest income ÷ average total assets (earning-asset data is not standardized).",
            )
        )
        k.append(m("efficiency_ratio", "Efficiency ratio", ttm.get("efficiency_ratio"), "pct"))
        k.append(m("rotce", "ROTCE", ttm.get("rotce"), "pct"))
        k.append(m("loan_to_deposit", "Loans / deposits", ttm.get("loan_to_deposit"), "pct"))
        loans = fin.quarterly_series("loans")
        deps = fin.quarterly_series("deposits")
        k.append(
            m(
                "loan_growth",
                "Loan growth (YoY)",
                yoy(loans[-1][1], loans[-5][1]) if len(loans) >= 5 else None,
                "pct",
            )
        )
        k.append(
            m(
                "deposit_growth",
                "Deposit growth (YoY)",
                yoy(deps[-1][1], deps[-5][1]) if len(deps) >= 5 else None,
                "pct",
            )
        )
        k.append(missing("cet1", "CET1 ratio", "pct", not_tagged))
        k.append(missing("npl", "Non-performing loans", "pct", not_tagged))
    elif prof == "insurer":
        k.append(
            m(
                "combined_ratio",
                "Combined ratio",
                ttm.get("combined_ratio"),
                "pct",
                reason="premium and loss items not tagged",
            )
        )
        k.append(m("roe", "Return on equity", ttm.get("roe"), "pct"))
        prem = fin.annual_series("premiums_earned")
        k.append(
            m(
                "premium_growth",
                "Premiums earned growth",
                yoy(prem[-1][1], prem[-2][1]) if len(prem) >= 2 else None,
                "pct",
            )
        )
    elif prof == "reit":
        sh = fin.ttm.get("shares_diluted")
        ffo, affo = ttm.get("ffo"), ttm.get("affo")
        k.append(
            m(
                "ffo",
                "FFO (TTM)",
                ffo,
                "usd",
                note="Net income + real-estate D&A − gains on property sales (NAREIT-style, from tagged items).",
            )
        )
        k.append(
            m(
                "ffo_per_share",
                "FFO per share",
                ffo / sh if (ffo is not None and sh) else None,
                "usd_per_share",
            )
        )
        k.append(
            m(
                "affo",
                "AFFO (approx.)",
                affo,
                "usd",
                note="FFO − capital improvements; straight-line rent and other adjustments are not standardized.",
            )
        )
        k.append(
            m(
                "affo_per_share",
                "AFFO per share",
                affo / sh if (affo is not None and sh) else None,
                "usd_per_share",
            )
        )
        div_paid = fin.ttm.get("dividends_paid")
        k.append(
            m(
                "affo_payout",
                "Dividends / AFFO",
                div_paid / affo if (div_paid and affo and affo > 0) else None,
                "pct",
            )
        )
        k.append(missing("occupancy", "Occupancy", "pct", not_tagged))
    elif prof in ("software", "growth_unprofitable"):
        g = growth_metrics(fin).get("revenue_cagr_1y")
        fm = ttm.get("fcf_margin")
        k.append(
            m(
                "rule_of_40",
                "Rule of 40",
                (g + fm) if (g is not None and fm is not None) else None,
                "pct",
                note="Revenue growth + FCF margin; ≥ 40% is the usual benchmark for software companies.",
            )
        )
        k.append(m("gross_margin", "Gross margin", ttm.get("gross_margin"), "pct"))
        k.append(m("sbc_pct_revenue", "Stock comp % of revenue", ttm.get("sbc_pct_revenue"), "pct"))
        k.append(
            missing(
                "nrr",
                "Net revenue retention",
                "pct",
                "disclosed by some companies in text only; not in XBRL facts",
            )
        )
    elif prof == "retail":
        k.append(m("dio", "Days inventory outstanding", ttm.get("dio"), "days"))
        k.append(m("ccc", "Cash conversion cycle", ttm.get("ccc"), "days"))
        k.append(missing("same_store_sales", "Same-store sales", "pct", not_tagged))
    elif prof == "energy":
        k.append(m("capex_intensity", "Capex % of revenue", ttm.get("capex_intensity"), "pct"))
        k.append(missing("production", "Production volumes", "count", not_tagged))
        k.append(missing("breakeven", "Breakeven price", "usd", not_tagged))
    elif prof == "utility":
        ppe = fin.annual_series("ppe")
        k.append(m("rate_base_growth", "PP&E growth (rate-base proxy)", series_cagr(ppe, 3), "pct"))
        capex, dna = fin.ttm.get("capex"), fin.ttm.get("dna")
        k.append(m("capex_to_dna", "Capex / depreciation", capex / dna if (capex and dna) else None, "x"))
        k.append(m("interest_coverage", "Interest coverage", ttm.get("interest_coverage"), "x"))
    else:
        k.append(m("roic", "Return on invested capital", ttm.get("roic"), "pct"))
        k.append(m("ccc", "Cash conversion cycle", ttm.get("ccc"), "days"))
        k.append(m("gross_margin", "Gross margin", ttm.get("gross_margin"), "pct"))
    return k


def quality_metrics(ctx: ReportContext) -> dict:
    fin = ctx.fin
    ttm = ttm_ratios(fin)
    src = ctx.sources.get("fundamentals", {}).get("source")
    asof = fin.ttm_end
    ann, _ = ratio_history(fin)
    sh = fin.annual_series("shares_diluted")
    dilution = series_cagr(sh, 3) if len(sh) >= 4 else None
    fcf_as = fin.ttm.get("fcf_after_sbc")
    ladder = []
    latest_annual = fin.annual[-1] if fin.annual else None
    if latest_annual:
        for key, label in (
            ("debt_maturity_y1", "≤1 yr"),
            ("debt_maturity_y2", "Year 2"),
            ("debt_maturity_y3", "Year 3"),
            ("debt_maturity_y4", "Year 4"),
            ("debt_maturity_y5", "Year 5"),
            ("debt_maturity_after5", "After 5"),
        ):
            ladder.append({"bucket": label, "amount": latest_annual.values.get(key)})
    has_ladder = any(x["amount"] for x in ladder)
    trend = {
        k: [r["ratios"].get(k) for r in ann[-8:]]
        for k in ("fcf_conversion", "sbc_pct_revenue", "capex_intensity", "nwc_pct_revenue", "roic")
    }
    fin_prof = ctx.sector.profile in ("bank", "insurer", "financial_other")
    if fin_prof:
        nm = "not meaningful for banks and insurers: debt and working capital are part of operations"
        for k in ("fcf_conversion", "capex_intensity", "nwc_pct_revenue", "roic", "interest_coverage"):
            ttm[k] = None
        fcf_as = None
    else:
        nm = None
    return {
        "metrics": [
            metric(
                "fcf_conversion",
                "FCF conversion (TTM)",
                ttm.get("fcf_conversion"),
                "pct",
                source=src,
                as_of=asof,
                reason=nm or "net income is negative or unavailable",
            ),
            metric(
                "sbc_pct_revenue",
                "Stock comp % of revenue",
                ttm.get("sbc_pct_revenue"),
                "pct",
                source=src,
                as_of=asof,
            ),
            metric(
                "fcf_after_sbc",
                "FCF after stock comp (TTM)",
                fcf_as,
                "usd",
                source=src,
                as_of=asof,
                reason=nm,
                note="Treats stock-based compensation as a real cost (see DECISIONS D-008).",
            ),
            metric(
                "capex_intensity",
                "Capex % of revenue",
                ttm.get("capex_intensity"),
                "pct",
                source=src,
                as_of=asof,
                reason=nm,
            ),
            metric(
                "nwc_pct_revenue",
                "Working capital % of revenue",
                ttm.get("nwc_pct_revenue"),
                "pct",
                source=src,
                as_of=asof,
                reason=nm,
            ),
            metric(
                "roic",
                "ROIC (TTM)",
                ttm.get("roic"),
                "pct",
                source=src,
                as_of=asof,
                reason=nm or "invested capital not positive",
            ),
            metric(
                "interest_coverage",
                "Interest coverage",
                ttm.get("interest_coverage"),
                "x",
                source=src,
                as_of=asof,
                reason=nm or "no interest expense reported",
            ),
            metric(
                "dilution_3y",
                "Share count change (3y CAGR)",
                dilution,
                "pct",
                source=src,
                as_of=asof,
                note="Positive = dilution; negative = net buybacks.",
            ),
        ],
        "trend_columns": [r["label"] for r in ann[-8:]],
        "trend": trend,
        "debt_ladder": ladder if has_ladder else None,
        "debt_ladder_note": None if has_ladder else "Debt maturity schedule not tagged in the latest 10-K.",
        "debt_ladder_as_of": latest_annual.end.isoformat() if (latest_annual and has_ladder) else None,
    }


def estimates_block(ctx: ReportContext) -> dict:
    """Consensus for the next fiscal years, for the revenue/EPS bar charts (not point-in-time)."""
    if ctx.pit:
        return {"rows": [], "reason": "excluded in point-in-time mode"}
    fx = ctx.data.estimates(ctx.ticker)
    ctx.sources["estimates"] = fx.meta()
    if not fx.value:
        return {
            "rows": [],
            "reason": fx.reason or "no analyst estimates for this company",
            "source": fx.source,
        }
    last_fy = ctx.fin.annual[-1].end if ctx.fin.annual else ctx.as_of
    rows = {}
    for e in fx.value:
        if e.period_type != "annual" or e.period_end <= last_fy:
            continue
        r = rows.setdefault(
            e.period_end, {"period_end": e.period_end.isoformat(), "label": f"FY{e.period_end.year}E"}
        )
        r[e.metric] = {"mean": e.mean, "low": e.low, "high": e.high, "n": e.n_analysts}
    ordered = [rows[k] for k in sorted(rows)][:2]
    return {
        "rows": ordered,
        "source": fx.source,
        "as_of": fx.fetched_at.isoformat() if fx.fetched_at else None,
        "note": "Analyst consensus (mean, with low–high range). Free-cash-flow estimates are not provided by the configured source.",
        "eps_basis": "Consensus EPS is usually on an adjusted basis, which can differ from GAAP diluted EPS.",
    }


def build(ctx: ReportContext) -> dict:
    fin = ctx.fin
    if not fin.annual and not fin.quarterly:
        return section(
            "fundamentals",
            status="missing",
            reason=ctx.missing.get("fundamentals", "no XBRL financial statements available"),
        )
    prof = ctx.sector.profile
    rows = ROWS.get(prof if prof in ROWS else "general")
    growth = growth_metrics(fin)
    src = ctx.sources.get("fundamentals", {}).get("source")
    asof = fin.ttm_end
    growth_metrics_out = [
        metric(
            k,
            growth_label(k),
            v,
            "pct",
            source=src,
            as_of=asof,
            def_id="cagr" if "cagr" in k else "yoy_growth",
            reason="needs positive values at both ends of the period",
        )
        for k, v in growth.items()
    ]
    return section(
        "fundamentals",
        profile=prof,
        annual=_statements(ctx, "annual", rows, 10),
        quarterly=_statements(ctx, "quarterly", rows, 12),
        ratios=_ratio_table(ctx),
        growth=growth_metrics_out,
        quality=quality_metrics(ctx),
        sector_kpis=sector_kpis(ctx),
        estimates=estimates_block(ctx),
        ttm_note=fin.ttm_note,
        years_of_history=fin.years_of_history,
        notes=[
            "Point-in-time: each value is the latest filing visible on the report date; restatements appear once filed.",
            "Quarterly cash-flow items are derived from year-to-date filings (10-Q cash-flow statements are cumulative).",
            "Share counts and per-share values are shown in current share units (adjusted for later splits).",
        ],
        sources=[{"name": k, **ctx.sources[k]} for k in ("fundamentals", "estimates") if k in ctx.sources],
    )
