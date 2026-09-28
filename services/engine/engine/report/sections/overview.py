"""Company overview: description in the app's own words, revenue mix, company facts, share structure,
market position."""

from __future__ import annotations

from datetime import timedelta

from engine.fundamentals.ratios import div, yoy
from engine.report.context import ReportContext
from engine.report.metric import metric, missing, section
from engine.report.sections import peers as peers_section


def _money(x: float) -> str:
    a = abs(x)
    for unit, f in (("trillion", 1e12), ("billion", 1e9), ("million", 1e6)):
        if a >= f:
            return f"${x / f:.1f} {unit}"
    return f"${x:,.0f}"


def describe(ctx: ReportContext) -> tuple[str, list[str]]:
    """A factual description built only from computed facts (no provider marketing text)."""
    m = ctx.meta
    fin = ctx.fin
    name = m.name if m else ctx.ticker
    sec = ctx.sector
    parts = [f"{name} is a {sec.sector_label.lower()} company"]
    if sec.sic_description:
        parts[0] += f" classified by the SEC under “{sec.sic_description.title()}” (SIC {sec.sic})"
    if m and m.hq_city:
        parts[0] += f", with its business address in {m.hq_city.title()}, {m.hq_state}"
    sentences = [parts[0] + "."]
    fact_ids = []
    rev = fin.ttm.get("revenue")
    if rev:
        q = fin.quarterly
        growth = (
            yoy(
                sum(p.values.get("revenue", 0) for p in q[-4:]),
                sum(p.values.get("revenue", 0) for p in q[-8:-4]),
            )
            if len(q) >= 8
            else None
        )
        s = f"Over the twelve months to {fin.ttm_end:%B %Y} it reported {_money(rev)} of revenue"
        if growth is not None:
            s += f", {abs(growth) * 100:.0f}% {'more' if growth >= 0 else 'less'} than a year earlier"
        oi = fin.ttm.get("operating_income")
        if oi is not None:
            s += f", and an operating {'profit' if oi >= 0 else 'loss'} of {_money(abs(oi))}"
        sentences.append(s + ".")
        fact_ids += ["revenue_ttm", "revenue_growth_ttm", "operating_income_ttm"]
    if sec.profile != sec.base_profile and sec.overlay_reason:
        sentences.append(
            f"The app analyzes it with the {sec.profile_label.lower()} profile because {sec.overlay_reason}."
        )
    elif sec.base_profile not in ("general",):
        sentences.append(
            f"The app analyzes it with the {sec.profile_label.lower()} profile, which switches to sector-appropriate metrics and valuation models."
        )
    return " ".join(sentences), fact_ids


def build(ctx: ReportContext) -> dict:
    fin = ctx.fin
    src_f = ctx.sources.get("fundamentals", {}).get("source")
    desc, _ = describe(ctx)

    # ---- revenue mix ---------------------------------------------------------------
    seg_fx = None if ctx.pit else ctx.data.segments(ctx.ticker)
    segments = {"product": None, "geography": None}
    seg_reason = seg_fx.reason if seg_fx else "excluded in point-in-time mode"
    if seg_fx and seg_fx.value:
        ctx.sources["segments"] = seg_fx.meta()
        for kind in ("product", "geography"):
            rows = sorted((s for s in seg_fx.value if s.kind == kind), key=lambda s: s.fiscal_year)
            if rows:
                latest = rows[-1]
                total = sum(v for v in latest.values.values() if v > 0)
                items = sorted(latest.values.items(), key=lambda kv: -kv[1])
                segments[kind] = {
                    "fiscal_year": latest.fiscal_year,
                    "items": [
                        {"name": k, "value": v, "share": v / total if total else None} for k, v in items
                    ],
                    "history": [{"fiscal_year": r.fiscal_year, "values": r.values} for r in rows[-5:]],
                    "source": seg_fx.source,
                }
    elif seg_fx and seg_fx.value == []:
        seg_reason = "the provider has no segment breakdown for this company"

    # ---- company facts ---------------------------------------------------------------
    prof = ctx.profile
    execs = ctx.optional("executives", lambda: ctx.data.executives(ctx.ticker)) or []
    ceo = next(
        (e for e in execs if "chief executive" in e.title.lower() or e.title.upper().startswith("CEO")), None
    )
    emp_hist = ctx.optional("employees", lambda: ctx.data.employees(ctx.ticker)) or []
    emp_series = [
        {"period": e.period.isoformat(), "count": e.count} for e in emp_hist if e.period <= ctx.as_of
    ]
    emp_dei = fin.cover.get("employees")
    emp_latest = (
        emp_series[-1]["count"]
        if emp_series
        else (emp_dei[0] if emp_dei else (prof.employees if prof else None))
    )
    emp_growth = yoy(emp_series[-1]["count"], emp_series[-2]["count"]) if len(emp_series) >= 2 else None
    tenure = (ctx.as_of.year - ceo.since) if (ceo and ceo.since) else None
    prof_src = ctx.sources.get("profile", {}).get("source")
    facts = [
        metric(
            "hq",
            "Business address",
            (f"{ctx.meta.hq_city.title()}, {ctx.meta.hq_state}" if ctx.meta and ctx.meta.hq_city else None),
            "text",
            source=ctx.sources.get("filings", {}).get("source"),
            reason="not in SEC submissions",
        ),
        metric(
            "ipo_date",
            "IPO / listing date",
            prof.ipo_date.isoformat() if (prof and prof.ipo_date) else None,
            "date",
            source=prof_src,
            reason=ctx.missing.get("profile", "not provided"),
        ),
        missing(
            "founded", "Founded", "date", "founding dates are not in SEC data or the configured providers"
        ),
        metric(
            "employees",
            "Employees",
            emp_latest,
            "count",
            source=prof_src or src_f,
            reason=ctx.missing.get("employees", "not reported in XBRL or by the configured provider"),
        ),
        metric(
            "employee_growth",
            "Employee growth (latest year)",
            emp_growth,
            "pct",
            source=prof_src,
            reason="needs two years of history",
        ),
        metric(
            "ceo",
            "CEO",
            ceo.name if ceo else (prof.ceo if prof else None),
            "text",
            source=prof_src,
            reason=ctx.missing.get("executives", "not provided"),
        ),
        metric(
            "ceo_tenure", "CEO tenure", tenure, "years", source=prof_src, reason="start year not provided"
        ),
        metric(
            "fiscal_year_end",
            "Fiscal year end",
            (
                f"{ctx.meta.fiscal_year_end[:2]}/{ctx.meta.fiscal_year_end[2:]}"
                if ctx.meta and ctx.meta.fiscal_year_end
                else None
            ),
            "text",
            source=ctx.sources.get("filings", {}).get("source"),
        ),
    ]

    # ---- share structure ----------------------------------------------------------------
    shares, shares_src = ctx.shares_outstanding
    flt = ctx.optional("float", lambda: ctx.data.shares_float(ctx.ticker))
    float_shares = flt.get("floatShares") if isinstance(flt, dict) else None
    float_src = ctx.sources.get("float", {}).get("source")
    if float_shares is None and fin.cover.get("public_float") and ctx.last_price:
        # dei:EntityPublicFloat is a dollar value as of the last Q2 end; convert with today's price (labeled)
        float_shares = None
    insider_pct = None
    insider_note = None
    txs = ctx.insiders
    if txs and shares:
        latest_by_filer: dict[str, tuple] = {}
        for t in sorted(txs, key=lambda x: (x.tx_date, x.filed_at)):
            if t.owned_after is not None and not t.derivative:
                latest_by_filer[t.filer_name] = (t.tx_date, t.owned_after)
        held = sum(v[1] for v in latest_by_filer.values())
        insider_pct = held / shares if held else None
        insider_note = (
            f"Sum of holdings last reported on Form 4 by {len(latest_by_filer)} insiders who traded in the lookback window; "
            "insiders who did not trade are not included, so this understates total insider ownership."
        )
    inst = ctx.institutions
    inst_pct = None
    if inst:
        pcts = [h.pct_of_shares for h in inst if h.pct_of_shares is not None]
        inst_pct = sum(pcts) if pcts else (sum(h.shares for h in inst) / shares if shares else None)
    idx_fx = None if ctx.pit else ctx.data.index_members()
    idx_members = set(idx_fx.value or []) if idx_fx else set()
    index_value = None
    index_reason = (
        idx_fx.reason if (idx_fx and idx_fx.reason) else "no licensed index constituent data configured"
    )
    if idx_fx and idx_fx.value:
        index_value = "S&P 500" if ctx.ticker in idx_members else "Not in the S&P 500"
    share_structure = [
        metric("shares_outstanding", "Shares outstanding", shares, "shares", source=src_f, note=shares_src),
        metric(
            "float_shares",
            "Float",
            float_shares,
            "shares",
            source=float_src,
            reason=ctx.missing.get("float", "not available on this tier"),
        ),
        metric("float_pct", "Float % of shares", div(float_shares, shares), "pct", source=float_src),
        metric(
            "insider_pct",
            "Insider ownership (Form 4 reporters)",
            insider_pct,
            "pct",
            source=ctx.sources.get("insiders", {}).get("source"),
            note=insider_note,
            reason=ctx.missing.get("insiders", "no Form 4 holdings reported in the lookback window"),
        ),
        metric(
            "institutional_pct",
            "Institutional ownership (top holders)",
            inst_pct,
            "pct",
            source=ctx.sources.get("institutions", {}).get("source"),
            reason=ctx.missing.get("institutions", "13F holder data not available on this tier"),
            note="Sum across the largest 13F holders returned by the provider.",
        ),
        metric("index_membership", "Index membership", index_value, "text", reason=index_reason),
    ]

    # ---- market position ------------------------------------------------------------------
    peers = ctx.section("peers", peers_section.build)
    competitors = [
        {"ticker": r["ticker"], "name": r["name"]}
        for r in (peers.get("rows") or [])
        if not r.get("is_subject")
    ][:6]
    products = [i["name"] for i in (segments["product"]["items"] if segments["product"] else [])][:6]
    recent_8k = [
        {"date": f.filed_at.isoformat(), "items": f.items, "url": f.url}
        for f in reversed(ctx.filings)
        if f.form == "8-K" and f.filed_at > ctx.as_of - timedelta(days=120)
    ][:5]
    return section(
        "overview",
        description=desc,
        description_note="Written by the app from reported figures; no provider marketing text is reproduced.",
        segments=segments,
        segments_reason=None if (segments["product"] or segments["geography"]) else seg_reason,
        facts=facts,
        employees_history=emp_series,
        share_structure=share_structure,
        market_position={
            "products": products,
            "products_note": None
            if products
            else "Product segments not available; see the filings for the business description.",
            "competitors": competitors,
            "competitors_note": peers.get("selection_note"),
        },
        recent_filings=recent_8k,
        sources=[
            {"name": k, **v}
            for k, v in ctx.sources.items()
            if k in ("filings", "profile", "segments", "fundamentals", "insiders", "institutions")
        ],
    )
