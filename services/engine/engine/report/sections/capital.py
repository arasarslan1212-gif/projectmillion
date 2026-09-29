"""Capital allocation scorecard: how management has used the cash the business produced.

Over the last few fiscal years: where the cash went (sources and uses), what return new investment earned, whether
buybacks beat simply owning the market, how much holders were diluted, whether payouts were funded by free cash
flow, and how safe the dividend is. Each component is scored between configured anchors; components that do not
apply are skipped with the reason, and the score averages the rest. The scorecard is its own section and not a Trust
Rating pillar, so nothing is counted twice.
"""

from __future__ import annotations

import pandas as pd

from engine.analysis.trust_rating import _safe_section
from engine.fundamentals.ratios import div
from engine.report.context import ReportContext
from engine.report.metric import metric, section

SRC = "SEC filings"


def _lin(x: float | None, anchors: list[float]) -> float | None:
    if x is None:
        return None
    lo, hi = anchors
    t = (x - lo) / (hi - lo) if hi != lo else 0.0
    return float(min(max(t, 0.0), 1.0) * 100)


def _level(score: float | None, levels: list) -> str | None:
    if score is None:
        return None
    return next(lbl for cut, lbl in levels if score >= cut)


def _pct(x: float, digits: int = 0, signed: bool = False) -> str:
    """Percent text without a negative zero ("-0%")."""
    out = f"{x:+.{digits}%}" if signed else f"{x:.{digits}%}"
    return out[1:] if out[:1] in "+-" and not any(c in "123456789" for c in out) else out


def _nopat(p) -> float | None:
    ebit, tax, pre = p.get("operating_income"), p.get("income_tax"), p.get("pretax_income")
    if ebit is None:
        return None
    rate = min(max(tax / pre, 0.10), 0.30) if (tax is not None and pre and pre > 0) else 0.21
    return ebit * (1 - rate)


def _avg_close(px: pd.Series, end) -> float | None:
    sl = px[(px.index > pd.Timestamp(end) - pd.Timedelta(days=365)) & (px.index <= pd.Timestamp(end))]
    return float(sl.mean()) if len(sl) >= 60 else None


def build(ctx: ReportContext) -> dict:
    cfg = ctx.cfg["capital"]
    anch = cfg["anchors"]
    years = int(cfg["years"])
    annual = ctx.fin.annual
    if len(annual) < 3:
        return section("capital", status="missing", reason="fewer than three fiscal years of filings")
    win = annual[-years:]
    start, end = annual[-years - 1] if len(annual) > years else annual[0], annual[-1]
    as_of = end.end.isoformat()
    total = lambda k: sum(p.get(k) or 0.0 for p in win)  # noqa: E731

    # ---- sources and uses over the window ------------------------------------------------------------
    cfo, capex, acq = total("cfo"), total("capex"), total("acquisitions")
    divs, bbs, issued = total("dividends_paid"), total("buybacks"), total("stock_issued")
    d_debt = (end.get("total_debt") or 0.0) - (start.get("total_debt") or 0.0)
    flows = [
        ("cfo", "Cash from operations", cfo, "source"),
        ("capex", "Capital expenditure", -capex, "use"),
        ("acquisitions", "Acquisitions", -acq if acq else None, "use"),
        ("dividends", "Dividends", -divs, "use"),
        ("buybacks", "Buybacks", -bbs, "use"),
        ("stock_issued", "Shares issued", issued if issued else None, "source"),
        ("debt", "Net debt raised (repaid)", d_debt, "source" if d_debt >= 0 else "use"),
    ]
    sources_uses = [
        {
            "id": k,
            "label": lbl,
            "value": v,
            "kind": kind,
            "share_of_cfo": div(abs(v), cfo) if cfo > 0 else None,
        }
        for k, lbl, v, kind in flows
        if v is not None and abs(v) > 1e-6 * max(abs(cfo), 1.0)
    ]

    comps: dict[str, dict] = {}

    def comp(
        cid: str, label: str, score: float | None, verdict: str, metrics: list[dict], skip: str | None = None
    ):
        comps[cid] = {"id": cid, "label": label, "score": None if skip else score, "verdict": verdict,
                      "metrics": metrics, "skipped": skip}  # fmt: skip

    # ---- 1. reinvestment: return on new capital vs. WACC --------------------------------------------------
    v = _safe_section(ctx, "valuation")
    wacc = ((v or {}).get("wacc") or {}).get("value")
    if ctx.sector.is_financial:
        comp("reinvestment", "Return on new investment", None, "", [],
             f"invested capital is not a meaningful measure for the {ctx.sector.profile_label} profile")  # fmt: skip
    else:
        n0, n1 = _nopat(start), _nopat(end)
        ic0, ic1 = start.get("invested_capital"), end.get("invested_capital")
        if None in (n0, n1, ic0, ic1) or not ic0:
            comp(
                "reinvestment",
                "Return on new investment",
                None,
                "",
                [],
                "operating profit or invested capital missing",
            )
        elif abs(ic1 - ic0) < float(cfg["min_capital_change"]) * abs(ic0):
            comp("reinvestment", "Return on new investment", None, "", [],
                 "invested capital barely changed, so a return on new capital is not meaningful")  # fmt: skip
        elif ic1 < ic0:
            comp("reinvestment", "Return on new investment", None, "", [],
                 "invested capital shrank over the window (the business returned more capital than it added)")  # fmt: skip
        else:
            inc = (n1 - n0) / (ic1 - ic0)
            spread = inc - wacc if wacc is not None else None
            m_inc = metric(
                "incremental_roic", "Return on new capital (5 years)", inc, "pct", source=SRC, as_of=as_of
            )
            ms = [m_inc]
            if wacc is not None:
                ms.append(metric("wacc", "WACC", wacc, "pct", source="app valuation engine", as_of=as_of))
            verdict = (
                f"Each extra dollar invested earned about {_pct(inc)} in added operating profit after tax"
                + (
                    f", {'above' if spread >= 0 else 'below'} the {wacc:.1%} cost of capital."
                    if spread is not None
                    else "."
                )
            )
            comp(
                "reinvestment",
                "Return on new investment",
                _lin(spread, anch["incremental_roic_spread"]),
                verdict,
                ms,
            )

    # ---- 2. buybacks vs. the market ----------------------------------------------------------------------
    closes = ctx.prices["close"] if not ctx.prices.empty else pd.Series(dtype=float)
    mkt = ctx.market_prices["close"] if not ctx.market_prices.empty else pd.Series(dtype=float)
    mcap = ctx.market_cap
    if not bbs or (mcap and bbs < float(cfg["min_buybacks_pct_mcap"]) * mcap):
        comp("buybacks", "Buyback timing", None, "", [], "no meaningful buybacks in the window")
    elif closes.empty or mkt.empty or ctx.last_price is None:
        comp("buybacks", "Buyback timing", None, "", [], "price history unavailable")
    else:
        own_now = mkt_now = 0.0
        spent = 0.0
        for p in win:
            bb = p.get("buybacks") or 0.0
            a, m = _avg_close(closes, p.end), _avg_close(mkt, p.end)
            if bb <= 0 or not a or not m:
                continue
            spent += bb
            own_now += bb * ctx.last_price / a
            mkt_now += bb * float(mkt.iloc[-1]) / m
        if spent <= 0:
            comp(
                "buybacks",
                "Buyback timing",
                None,
                "",
                [],
                "not enough price history around the buyback years",
            )
        else:
            rel = own_now / mkt_now - 1
            ms = [
                metric("buyback_vs_market", "Buybacks vs. the market", rel, "pct", source="SEC filings; prices", as_of=ctx.as_of),
                metric("buyback_return", "Value of past buybacks vs. cash spent", own_now / spent - 1, "pct",
                       source="SEC filings; prices", as_of=ctx.as_of),
            ]  # fmt: skip
            verdict = (
                f"The shares bought back are worth {_pct(own_now / spent - 1, signed=True)} versus the cash spent; the same "
                f"cash in the market index would be worth {_pct(mkt_now / spent - 1, signed=True)}."
            )
            comp("buybacks", "Buyback timing", _lin(rel, anch["buyback_vs_market"]), verdict, ms)

    # ---- 3. dilution ----------------------------------------------------------------------------------------
    sh = [v for _, v in ctx.fin.annual_series("shares_diluted")]
    chg3 = (sh[-1] / sh[-4]) ** (1 / 3) - 1 if len(sh) >= 4 and sh[-4] > 0 else None
    sbc_rev = div(ctx.fin.ttm.get("sbc"), ctx.fin.ttm.get("revenue"))
    parts = [
        x
        for x in (_lin(chg3, anch["share_change_3y"]), _lin(sbc_rev, anch["sbc_pct_revenue"]))
        if x is not None
    ]
    if parts:
        ms = []
        if chg3 is not None:
            ms.append(
                metric(
                    "share_count_change_3y",
                    "Share count change (3-year CAGR)",
                    chg3,
                    "pct",
                    source=SRC,
                    as_of=as_of,
                )
            )
        if sbc_rev is not None:
            ms.append(
                metric("sbc_pct_revenue", "Stock comp % of revenue", sbc_rev, "pct", source=SRC, as_of=as_of)
            )
        verdict = (
            (
                f"The share count changed {_pct(chg3, 1, True)} a year over three years"
                if chg3 is not None
                else ""
            )
            + ("; " if chg3 is not None and sbc_rev is not None else "")
            + (f"stock-based pay is {sbc_rev:.1%} of revenue" if sbc_rev is not None else "")
            + "."
        )
        comp("dilution", "Dilution", sum(parts) / len(parts), verdict[0].upper() + verdict[1:], ms)
    else:
        comp("dilution", "Dilution", None, "", [], "share counts and stock compensation unavailable")

    # ---- 4. payouts funded by free cash flow ---------------------------------------------------------------
    fcf = total("fcf")
    payouts = divs + bbs
    if payouts <= 0:
        comp(
            "payouts",
            "Payouts covered by free cash flow",
            None,
            "",
            [],
            "no dividends or buybacks in the window",
        )
    elif fcf <= 0:
        comp("payouts", "Payouts covered by free cash flow", 0.0,
             "Dividends and buybacks were paid while free cash flow over the window was negative, so they were funded "
             "by debt, cash on hand or share issuance.", [])  # fmt: skip
    else:
        cov = payouts / fcf
        comp("payouts", "Payouts covered by free cash flow", _lin(cov, anch["payout_coverage"]),
             f"Dividends and buybacks took {cov:.0%} of the free cash flow the business generated"
             + (" (more than it produced)." if cov > 1 else "."),
             [metric("payout_coverage", "Payouts ÷ free cash flow (5 years)", cov, "pct", source=SRC, as_of=as_of)])  # fmt: skip

    # ---- 5. dividends -----------------------------------------------------------------------------------------
    d = _safe_section(ctx, "dividends")
    safety = ((d or {}).get("metrics") or {}).get("safety") if d else None
    if safety and safety.get("value") is not None:
        comp("dividends", "Dividend safety", float(safety["value"]),
             f"The dividend safety score is {safety['value']:.0f}/100 ({safety.get('note') or 'see Dividends'}).", [safety])  # fmt: skip
    else:
        comp(
            "dividends",
            "Dividend safety",
            None,
            "",
            [],
            "the company pays no dividend (not a negative by itself)",
        )

    # ---- M&A (information only: acquisitions are judged later, through impairments) ------------------------
    gw0, gw1, ta = start.get("goodwill"), end.get("goodwill"), end.get("total_assets")
    mna = {
        "acquisitions": acq or None,
        "goodwill_start": gw0,
        "goodwill_end": gw1,
        "goodwill_to_assets": metric("goodwill_to_assets", "Goodwill ÷ total assets", div(gw1, ta), "pct", source=SRC, as_of=as_of),
        "note": (
            "Acquisition spending is not tagged in these filings; " if not acq else ""
        ) + "goodwill changes show deals made, but whether they paid off only shows later, through impairments.",
    }  # fmt: skip

    w = cfg["weights"]
    scored = [(w[k], c["score"]) for k, c in comps.items() if c["score"] is not None]
    score = sum(a * b for a, b in scored) / sum(a for a, _ in scored) if scored else None
    return section(
        "capital",
        status="ok" if len(scored) >= 2 else "partial",
        reason=None if len(scored) >= 2 else "fewer than two scorecard components apply to this company",
        window={"start": start.end.isoformat(), "end": end.end.isoformat(), "years": len(win)},
        score=metric(
            "capital_allocation_score",
            "Capital allocation score",
            score,
            "score",
            source="app (see Methodology)",
            as_of=as_of,
            note=_level(score, cfg["levels"]),
        ),  # fmt: skip
        level=_level(score, cfg["levels"]),
        components=list(comps.values()),
        sources_uses=sources_uses,
        mna=mna,
        sources=[{"name": "SEC EDGAR filings", "source": "SEC EDGAR", "as_of": as_of}],
    )
