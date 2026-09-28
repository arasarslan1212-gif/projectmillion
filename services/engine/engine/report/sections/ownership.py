"""Ownership: insider trades (Form 4), institutional holders (13F), short interest and buybacks.

Insider trades are split by what they signal. Open-market purchases (code P) are the strong signal: insiders spend
their own money. Open-market sales (S) are weaker, especially under a pre-arranged 10b5-1 plan. Option exercises
(M/X), tax withholding (F), grants (A) and gifts (G) are mechanical and not treated as signals.
"""

from __future__ import annotations

from datetime import timedelta

import pandas as pd

from engine.fundamentals.ratios import div
from engine.report.context import ReportContext
from engine.report.metric import metric, section

CODE_CLASS = {
    "P": ("purchase", "Open-market purchase"),
    "S": ("sale", "Open-market sale"),
    "M": ("exercise", "Option exercise"),
    "X": ("exercise", "Option exercise"),
    "F": ("tax", "Shares withheld for tax"),
    "A": ("grant", "Grant or award"),
    "G": ("gift", "Gift"),
}


def insider_summary(txs, as_of, cfg) -> dict:
    since = as_of - timedelta(days=int(cfg["insider_lookback_months"]) * 30)
    rows = []
    for t in sorted(
        (t for t in txs if t.tx_date >= since and not t.derivative), key=lambda t: t.tx_date, reverse=True
    ):
        cls, label = CODE_CLASS.get(t.code, ("other", f"Other ({t.code})"))
        value = t.shares * t.price if t.price else None
        rows.append({
            "date": t.tx_date.isoformat(), "filed": t.filed_at.isoformat(), "name": t.filer_name, "role": t.role,
            "code": t.code, "class": cls, "label": label, "shares": t.shares, "price": t.price, "value": value,
            "plan_10b5_1": t.plan_10b5_1, "url": t.url,
        })  # fmt: skip

    def total(cls: str, days: int, plan: bool | None = None) -> float:
        lo = as_of - timedelta(days=days)
        return sum(
            r["value"] or 0.0
            for r in rows
            if r["class"] == cls
            and r["date"] >= lo.isoformat()
            and (plan is None or bool(r["plan_10b5_1"]) == plan)
        )

    # cluster buying: >= N distinct insiders with open-market purchases inside a rolling window
    buys = sorted((r for r in rows if r["class"] == "purchase"), key=lambda r: r["date"])
    window = int(cfg["cluster_window_days"])
    need = int(cfg["cluster_min_insiders"])
    clusters, used = [], set()
    for i, r in enumerate(buys):
        start = pd.Timestamp(r["date"])
        grp = [b for b in buys[i:] if pd.Timestamp(b["date"]) - start <= pd.Timedelta(days=window)]
        names = {b["name"] for b in grp}
        key = frozenset(id(b) for b in grp)
        if len(names) >= need and not (key & used):
            used |= key
            clusters.append({"start": grp[0]["date"], "end": grp[-1]["date"], "insiders": sorted(names),
                             "value": sum(b["value"] or 0.0 for b in grp)})  # fmt: skip
    return {
        "rows": rows,
        "clusters": clusters,
        "buy_6m": total("purchase", 182),
        "sell_6m": total("sale", 182),
        "sell_6m_plan": total("sale", 182, True),
        "buy_12m": total("purchase", 365),
        "sell_12m": total("sale", 365),
        "counts": {c: sum(1 for r in rows if r["class"] == c) for c in {r["class"] for r in rows}},
    }


def buyback_track(ctx: ReportContext) -> dict:
    """Share count trend, buyback yield and whether past buybacks were made at good prices.

    For each fiscal year, the cash spent on repurchases is converted to shares at that year's average close; the
    shares' value today versus the cash spent shows whether the buybacks created or destroyed value so far.
    """
    fin = ctx.fin
    closes = ctx.prices["close"] if not ctx.prices.empty else pd.Series(dtype=float)
    years = []
    for p in fin.annual[-6:]:
        bb = p.get("buybacks")
        if not bb or bb <= 0 or closes.empty:
            continue
        sl = closes[
            (closes.index > pd.Timestamp(p.end) - pd.Timedelta(days=365))
            & (closes.index <= pd.Timestamp(p.end))
        ]
        if len(sl) < 60:
            continue
        avg = float(sl.mean())
        years.append(
            {"fiscal_year_end": p.end.isoformat(), "spent": bb, "avg_price": avg, "shares": bb / avg}
        )
    p0 = ctx.last_price
    spent = sum(y["spent"] for y in years)
    value_now = sum(y["shares"] for y in years) * p0 if p0 else None
    sh = [v for _, v in fin.annual_series("shares_diluted")]
    chg = {}
    for n in (1, 3, 5):
        if len(sh) > n and sh[-1 - n] > 0:
            chg[f"{n}y"] = (sh[-1] / sh[-1 - n]) ** (1 / n) - 1
    ttm_bb = fin.ttm.get("buybacks")
    return {
        "years": years,
        "spent": spent,
        "value_now": value_now,
        "return_on_buybacks": (value_now / spent - 1) if (value_now and spent) else None,
        "share_change_cagr": chg,
        "buyback_yield": div(ttm_bb, ctx.market_cap) if ttm_bb else None,
        "sbc_to_mcap": div(fin.ttm.get("sbc"), ctx.market_cap),
        "share_counts": [
            {"date": d.isoformat(), "shares": v} for d, v in fin.annual_series("shares_diluted")[-10:]
        ],
    }


def build(ctx: ReportContext) -> dict:
    cfg = ctx.cfg["ownership"]
    as_of = ctx.as_of
    parts, missing = {}, {}

    txs = ctx.insiders
    if txs is None:
        missing["insiders"] = ctx.missing.get("insiders") or "Form 4 data unavailable"
    else:
        parts["insiders"] = insider_summary(txs, as_of, cfg)

    inst = ctx.institutions
    if not inst:
        missing["institutions"] = (
            ctx.missing.get("institutions") or "13F holdings need the starter data tier (FMP)"
        )
        top, net = [], None
    else:
        period = (
            max(h.period for h in inst if h.period <= as_of) if any(h.period <= as_of for h in inst) else None
        )
        cur = sorted((h for h in inst if h.period == period), key=lambda h: -h.shares)
        top = [{"holder": h.holder, "shares": h.shares, "value": h.value, "pct": h.pct_of_shares, "change": h.change_shares}
               for h in cur[:10]]  # fmt: skip
        chg = [h.change_shares for h in cur if h.change_shares is not None]
        net = {"period": period.isoformat() if period else None, "net_change_shares": float(sum(chg)) if chg else None,
               "increased": sum(1 for c in chg if c > 0), "decreased": sum(1 for c in chg if c < 0),
               "top10_pct": float(sum(h.pct_of_shares or 0 for h in cur[:10])) or None}  # fmt: skip
        parts["institutions"] = {"top": top, "summary": net, "source": inst[0].source}

    si = ctx.data.short_interest(ctx.ticker)
    lag = int(ctx.cfg.get("pit.short_interest_lag_days", 12))
    pts = [p for p in (si.value or []) if p.settlement_date <= as_of - timedelta(days=lag)]
    if not pts:
        missing["short_interest"] = si.reason or "no short interest data"
    else:
        float_sh = None
        if not ctx.pit:
            fl = ctx.data.shares_float(ctx.ticker).value
            float_sh = fl.get("floatShares") if isinstance(fl, dict) else None
        denom = float_sh or ctx.shares_outstanding[0]
        series = [{"date": p.settlement_date.isoformat(), "pct_float": div(p.short_interest, denom),
                   "days_to_cover": p.days_to_cover} for p in pts[-26:]]  # fmt: skip
        last = series[-1]
        prev = next(
            (
                s
                for s in reversed(series)
                if s["date"] <= (pts[-1].settlement_date - timedelta(days=85)).isoformat()
            ),
            None,
        )
        trend = None
        if prev and prev["pct_float"] and last["pct_float"] is not None:
            ch = last["pct_float"] / prev["pct_float"] - 1
            trend = "rising" if ch > 0.15 else "falling" if ch < -0.15 else "stable"
        parts["short_interest"] = {"series": series, "latest": last, "trend": trend,
                                   "denominator": "float" if float_sh else "shares outstanding", "source": si.source}  # fmt: skip

    bb = buyback_track(ctx)
    ins = parts.get("insiders") or {}
    s_i = parts.get("short_interest") or {}
    src_f4 = "SEC Form 4"
    m = {
        "insider_buy_6m": metric("insider_buying_6m", "Insider open-market purchases (6 months)", ins.get("buy_6m"), "usd",
                                 source=src_f4, as_of=as_of),
        "insider_sell_6m": metric("insider_selling_6m", "Insider open-market sales (6 months)", ins.get("sell_6m"), "usd",
                                  source=src_f4, as_of=as_of, note=None if not ins else
                                  f"{(ins.get('sell_6m_plan') or 0) / ins['sell_6m']:.0%} under 10b5-1 plans" if ins.get("sell_6m") else None),
        "clusters": metric("insider_clusters", "Insider cluster buys (24 months)", len(ins.get("clusters", [])) if ins else None,
                           "count", source=src_f4, as_of=as_of),
        "short_pct": metric("short_interest_pct_float", "Short interest (% of float)", (s_i.get("latest") or {}).get("pct_float"),
                            "pct", source="FINRA", as_of=(s_i.get("latest") or {}).get("date")),
        "days_to_cover": metric("days_to_cover", "Days to cover", (s_i.get("latest") or {}).get("days_to_cover"), "days",
                                source="FINRA", as_of=(s_i.get("latest") or {}).get("date")),
        "share_change_3y": metric("share_count_change_3y", "Share count change (3-year CAGR)", bb["share_change_cagr"].get("3y"),
                                  "pct", source="SEC filings", as_of=as_of),
        "buyback_yield": metric("buyback_yield", "Buyback yield (trailing 12 months)", bb["buyback_yield"], "pct",
                                source="SEC filings", as_of=as_of),
        "buyback_return": metric("buyback_return", "Value of past buybacks vs. cash spent", bb["return_on_buybacks"], "pct",
                                 source="SEC filings; prices", as_of=as_of,
                                 reason=None if bb["return_on_buybacks"] is not None else "no buybacks in the last 6 fiscal years"),
    }  # fmt: skip
    status = "ok" if len(parts) == 3 else "partial"
    return section(
        "ownership",
        status=status,
        reason="; ".join(f"{k.replace('_', ' ')}: {v}" for k, v in missing.items()) or None,
        insiders=parts.get("insiders"),
        institutions=parts.get("institutions"),
        short_interest=parts.get("short_interest"),
        buybacks=bb,
        metrics=m,
        missing=missing,
        sources=[
            {"name": n, "as_of": as_of.isoformat()}
            for n in ("SEC Form 4", "FINRA", "FMP (13F)", "SEC filings")
        ],
    )
