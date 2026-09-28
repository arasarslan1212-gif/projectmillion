"""Red flags: each check reports whether it fired, a severity, a plain explanation and its source.

Checks that could not run (missing data) are listed separately, so "no flags" is never confused
with "not checked".
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from engine.fundamentals.ratios import series_cagr, yoy

if TYPE_CHECKING:
    from engine.report.context import ReportContext

GOING_CONCERN_RE = re.compile(
    r"substantial doubt[^.]{0,200}going concern|going concern[^.]{0,200}substantial doubt", re.I | re.S
)
CUSTOMER_RE = re.compile(
    r"(?:one|a single|our largest|two|three)\s+customers?[^.]{0,160}?(?:accounted for|represented|comprised)\s+(?:approximately\s+|about\s+)?(\d{1,2}(?:\.\d)?)\s?%",
    re.I | re.S,
)


@dataclass
class Flag:
    id: str
    title: str
    triggered: bool
    severity: str  # high | medium | low | info
    explanation: str
    source: str | None = None
    url: str | None = None
    value: float | None = None


def _years_back(ctx: ReportContext, years: int):
    return ctx.as_of - timedelta(days=365 * years)


def latest_10k_text(ctx: ReportContext) -> tuple[str | None, str | None, str | None]:
    tenks = [f for f in ctx.filings if f.form in ("10-K", "10-K405", "20-F")]
    if not tenks:
        return None, None, "no 10-K filed"
    f = tenks[-1]
    fx = ctx.data.document_text(f)
    if fx.value is None:
        return None, f.url, fx.reason
    return fx.value, f.url, None


def run_red_flags(ctx: ReportContext, quality: dict, cfg: dict) -> dict:
    flags: list[Flag] = []
    not_checked: list[dict] = []
    fin = ctx.fin
    th = cfg
    since3 = _years_back(ctx, 3)
    edgar = ctx.sources.get("filings", {}).get("source") or "SEC EDGAR"
    financial = ctx.sector.is_financial

    # --- accounting scores -------------------------------------------------------------
    z = quality.get("altman")
    if financial:
        not_checked.append(
            {"id": "altman_z", "title": "Altman Z", "reason": "not applicable to banks, insurers and REITs"}
        )
    elif z and z.get("value") is not None:
        zone = z["zone"]
        flags.append(
            Flag(
                "altman_z",
                "Altman Z distress zone",
                zone == "distress",
                "high" if zone == "distress" else "low",
                f"{z['variant']} is {z['value']:.2f} ({zone} zone).",
                "SEC EDGAR financials",
                value=z["value"],
            )
        )
    else:
        not_checked.append(
            {"id": "altman_z", "title": "Altman Z", "reason": (z or {}).get("reason", "insufficient data")}
        )
    f_ = quality.get("piotroski")
    if f_ and f_.get("value") is not None:
        low = f_["value"] <= th["piotroski_low"]
        flags.append(
            Flag(
                "piotroski",
                "Weak Piotroski F-score",
                low,
                "medium",
                f"Piotroski F-score is {f_['value']:.0f} of 9 (≤ {th['piotroski_low']} is weak).",
                "SEC EDGAR financials",
                value=f_["value"],
            )
        )
    m = quality.get("beneish")
    if financial:
        not_checked.append(
            {"id": "beneish_m", "title": "Beneish M", "reason": "not applicable to financial companies"}
        )
    elif m and m.get("value") is not None:
        hi = m["value"] > th["beneish_threshold"]
        flags.append(
            Flag(
                "beneish_m",
                "Beneish M-score above threshold",
                hi,
                "high",
                f"Beneish M-score is {m['value']:.2f}; above {th['beneish_threshold']} is associated with a higher likelihood of earnings manipulation.",
                "SEC EDGAR financials",
                value=m["value"],
            )
        )
    else:
        not_checked.append(
            {"id": "beneish_m", "title": "Beneish M", "reason": (m or {}).get("reason", "insufficient data")}
        )
    acc = quality.get("accruals_ratio")
    if acc is not None:
        flags.append(
            Flag(
                "accruals",
                "High accruals",
                acc > th["accruals_high"],
                "medium",
                f"Net income exceeds operating cash flow by {acc * 100:.1f}% of average assets (above {th['accruals_high'] * 100:.0f}% is a warning sign).",
                "SEC EDGAR financials",
                value=acc,
            )
        )

    # --- filings ------------------------------------------------------------------------
    recent = [f for f in ctx.filings if f.filed_at >= since3]
    nonreliance = [f for f in recent if f.form.startswith("8-K") and "4.02" in f.items]
    amendments = [f for f in recent if f.form in ("10-K/A", "10-Q/A")]
    flags.append(
        Flag(
            "restatement",
            "Restatement / non-reliance (8-K Item 4.02)",
            bool(nonreliance),
            "high",
            f"{len(nonreliance)} Item 4.02 filing(s) in the last 3 years: prior financial statements should no longer be relied upon."
            if nonreliance
            else "No Item 4.02 non-reliance filings in the last 3 years.",
            edgar,
            nonreliance[-1].url if nonreliance else None,
        )
    )
    if amendments:
        flags.append(
            Flag(
                "amended_reports",
                "Amended periodic reports",
                True,
                "low",
                f"{len(amendments)} amended 10-K/10-Q filing(s) in the last 3 years.",
                edgar,
                amendments[-1].url,
            )
        )
    auditor = [f for f in recent if f.form.startswith("8-K") and "4.01" in f.items]
    flags.append(
        Flag(
            "auditor_change",
            "Auditor change (8-K Item 4.01)",
            bool(auditor),
            "medium",
            f"Changed auditor on {auditor[-1].filed_at.isoformat()}."
            if auditor
            else "No auditor changes in the last 3 years.",
            edgar,
            auditor[-1].url if auditor else None,
        )
    )
    late = [f for f in recent if f.form.startswith("NT ")]
    flags.append(
        Flag(
            "late_filing",
            "Late filing notice (NT 10-K / NT 10-Q)",
            bool(late),
            "medium",
            f"{len(late)} late-filing notice(s) in the last 3 years, most recently {late[-1].filed_at.isoformat()}."
            if late
            else "No late-filing notices in the last 3 years.",
            edgar,
            late[-1].url if late else None,
        )
    )

    # --- 10-K text ------------------------------------------------------------------------
    text, url, reason = latest_10k_text(ctx)
    if text is None:
        not_checked.append(
            {
                "id": "going_concern",
                "title": "Going-concern language",
                "reason": reason or "10-K text unavailable",
            }
        )
        not_checked.append(
            {
                "id": "customer_concentration",
                "title": "Customer concentration",
                "reason": reason or "10-K text unavailable",
            }
        )
    else:
        gc = GOING_CONCERN_RE.search(text)
        flags.append(
            Flag(
                "going_concern",
                "Going-concern doubt in the 10-K",
                bool(gc),
                "high",
                "The latest 10-K says there is substantial doubt about the company's ability to continue as a going concern."
                if gc
                else "No going-concern language found in the latest 10-K.",
                "Latest 10-K text",
                url,
            )
        )
        pcts = [float(x) for x in CUSTOMER_RE.findall(text)]
        top = max(pcts) if pcts else None
        if top is not None and top >= th["customer_concentration_pct"]:
            flags.append(
                Flag(
                    "customer_concentration",
                    "Customer concentration",
                    True,
                    "medium" if top >= th["customer_concentration_high_pct"] else "low",
                    f"The 10-K discloses a customer accounting for about {top:.0f}% of revenue.",
                    "Latest 10-K text",
                    url,
                    top / 100,
                )
            )
        else:
            flags.append(
                Flag(
                    "customer_concentration",
                    "Customer concentration",
                    False,
                    "low",
                    "No customer at or above 10% of revenue is disclosed in the latest 10-K.",
                    "Latest 10-K text",
                    url,
                )
            )

    # --- trends -----------------------------------------------------------------------------
    sh = fin.annual_series("shares_diluted")
    dil = series_cagr(sh, 3) if len(sh) >= 4 else None
    if dil is not None:
        heavy = dil > th["dilution_medium"]
        flags.append(
            Flag(
                "dilution",
                "Heavy dilution",
                heavy,
                "high" if dil > th["dilution_high"] else "medium",
                f"Diluted share count grew {dil * 100:.1f}% a year over 3 years.",
                "SEC EDGAR financials",
                value=dil,
            )
        )
    a = fin.annual
    if len(a) >= 2 and not financial:
        rg = yoy(a[-1].get("revenue"), a[-2].get("revenue"))
        for key, fid, title in (
            ("receivables", "receivables_outpacing", "Receivables growing faster than revenue"),
            ("inventory", "inventory_outpacing", "Inventory growing faster than revenue"),
        ):
            g = yoy(a[-1].get(key), a[-2].get(key))
            if g is None or rg is None:
                continue
            gap = g - rg
            flags.append(
                Flag(
                    fid,
                    title,
                    gap > th["working_capital_gap"],
                    "medium",
                    f"{key.title()} grew {g * 100:.0f}% vs. revenue {rg * 100:.0f}% in the latest fiscal year.",
                    "SEC EDGAR financials",
                    value=gap,
                )
            )
    if not financial:
        ic = quality.get("interest_coverage")
        if ic is not None:
            flags.append(
                Flag(
                    "interest_coverage",
                    "Weak interest coverage",
                    ic < th["interest_coverage_low"],
                    "high",
                    f"Operating profit covers interest {ic:.1f}×.",
                    "SEC EDGAR financials",
                    value=ic,
                )
            )
        ladder = [p.values for p in a[-1:]]
        if ladder:
            v = ladder[0]
            due2 = (v.get("debt_maturity_y1") or 0.0) + (v.get("debt_maturity_y2") or 0.0)
            total = fin.ttm.get("total_debt") or sum(
                (v.get(k) or 0.0) for k in v if k.startswith("debt_maturity_")
            )
            if due2 > 0 and total:
                cash = fin.ttm.get("cash_and_st") or fin.ttm.get("cash") or 0.0
                fcf = max(fin.ttm.get("fcf") or 0.0, 0.0)
                cover = (cash + 2 * fcf) / due2
                share = due2 / total
                hit = cover < 1.0 and share > th["debt_wall_share"]
                flags.append(
                    Flag(
                        "debt_wall",
                        "Large debt maturities within 2 years",
                        hit,
                        "high" if share > th["debt_wall_share_high"] else "medium",
                        f"{share * 100:.0f}% of debt (${due2 / 1e6:,.0f}M) is due within 2 years; cash plus two years of "
                        f"free cash flow covers {cover:.1f}× of it, so it likely needs refinancing.",
                        "10-K debt footnote (XBRL)",
                        value=cover,
                    )
                )
        fcf = fin.ttm.get("fcf")
        cash = fin.ttm.get("cash_and_st") or fin.ttm.get("cash")
        if fcf is not None and fcf < 0 and cash is not None:
            runway = cash / -fcf
            flags.append(
                Flag(
                    "cash_runway",
                    "Short cash runway",
                    runway < th["runway_years"],
                    "high",
                    f"At the trailing cash burn of ${-fcf / 1e6:,.0f}M a year, cash lasts about {runway:.1f} years.",
                    "SEC EDGAR financials",
                    value=runway,
                )
            )
    eq = fin.ttm.get("equity")
    if eq is not None and eq < 0:
        flags.append(
            Flag(
                "negative_equity",
                "Negative shareholders' equity",
                True,
                "info",
                "Book equity is negative; this can reflect large buybacks rather than distress, so read it with the cash-flow data.",
                "SEC EDGAR financials",
                value=eq,
            )
        )
    triggered = [asdict(f) for f in flags if f.triggered]
    order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    triggered.sort(key=lambda x: order[x["severity"]])
    return {
        "triggered": triggered,
        "passed": [asdict(f) for f in flags if not f.triggered],
        "not_checked": not_checked,
        "counts": {
            s: sum(1 for f in triggered if f["severity"] == s) for s in ("high", "medium", "low", "info")
        },
    }
