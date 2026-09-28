"""Wall Street analysts: who covers the stock, how good their record is, and what the trusted consensus says."""

from __future__ import annotations

from datetime import timedelta

import numpy as np

from engine.analysts.calls import Call
from engine.analysts.consensus import consensus
from engine.analysts.ratings import rating_label
from engine.analysts.service import active_targets, compute, month_ends
from engine.report.context import ReportContext
from engine.report.metric import metric, section

GRANULARITY_LABELS = {
    "analyst": "Per-analyst targets and ratings",
    "firm": "Firm-level ratings only (no analyst names on this data tier)",
    "consensus": "Consensus only: analyst-level track records are unavailable on this data tier",
    "none": "No analyst data on this data tier",
}


def _rating_word(x: float | None) -> str | None:
    if x is None:
        return None
    if x >= 0.5:
        return "Buy"
    if x >= 0.15:
        return "Moderate buy"
    if x > -0.15:
        return "Hold"
    if x > -0.5:
        return "Moderate sell"
    return "Sell"


def _action_sentence(c: Call, prev_rating: str | None) -> str:
    """The app's own one-line description of a firm's latest call, built from structured data only."""
    parts = []
    if c.action == "initiation":
        parts.append(f"Started coverage with {_a(c.rating)}" if c.rating else "Started coverage")
    elif c.action in ("upgrade", "downgrade"):
        verb = "Upgraded" if c.action == "upgrade" else "Downgraded"
        parts.append(f"{verb} the stock to {c.rating}" + (f" from {prev_rating}" if prev_rating else ""))
    elif c.rating:
        parts.append(f"Kept {_a(c.rating)}")
    if c.target is not None:
        ch = c.target_change
        if ch is None or c.action == "initiation":
            parts.append(f"a ${c.target:,.2f} target")
        elif abs(ch) < 0.005:
            parts.append(f"left its target at ${c.target:,.2f}")
        else:
            parts.append(
                f"{'raised' if ch > 0 else 'cut'} its target to ${c.target:,.2f} from ${c.target_prior:,.2f} ({ch:+.0%})"
            )
    s = " and ".join(parts) if parts else "Published a note"
    return s[0].upper() + s[1:] + "."


def _a(rating: str | None) -> str:
    if not rating:
        return "a rating"
    return ("an " if rating[0].lower() in "aeiou" else "a ") + f"{rating} rating"


def build(ctx: ReportContext) -> dict:
    cfg = ctx.cfg["analysts"]
    gran = ctx.data.p.analyst_granularity
    stale_days = int(cfg["stale_months"]) * 30
    rating_days = int(cfg["rating_stale_months"]) * 30
    p0 = ctx.last_price

    if gran == "none":
        return section("analysts", status="missing", reason=GRANULARITY_LABELS["none"], granularity=gran)
    if gran == "consensus":
        return _consensus_only(ctx, gran)

    res = compute(ctx)
    calls: list[Call] = res["calls"]
    if not calls:
        out = _consensus_only(
            ctx, gran, "Consensus only: no analyst-level records for this stock in the data"
        )
        if out.get("status") in ("ok", "partial"):
            return out
        return section(
            "analysts",
            status="missing",
            reason="No analyst price targets or ratings for this stock in the data.",
            granularity=gran,
            granularity_label=GRANULARITY_LABELS[gran],
        )
    scores, firm_scores, herd = res["analysts"], res["firms"], res["herding"]
    pop = scores.get("_population", {})
    prior_score = pop.get("score")

    def score_of(c: Call) -> dict | None:
        if c.analyst_key and c.analyst_key in scores:
            return scores[c.analyst_key]
        return firm_scores.get(c.firm)

    # ---- latest call per analyst (or firm) -------------------------------------------------------
    latest: dict[str, Call] = {}
    for c in sorted(calls, key=lambda c: c.date):
        latest[c.who] = c
    rows = []
    for who, c in latest.items():
        s = score_of(c)
        age = (ctx.as_of - c.date).days
        dropped = c.action == "termination"
        stale = c.target is None or age > stale_days or dropped
        if c.target is None and age > rating_days:
            continue
        rows.append(
            {
                "who": who,
                "analyst": c.analyst_name,
                "firm": c.firm,
                "rating": c.rating,
                "rating_norm": c.rating_norm,
                "rating_class": rating_label(c.rating_norm) if c.rating_norm is not None else None,
                "rating_source": c.rating_source,
                "target": c.target,
                "date": c.date.isoformat(),
                "days_old": age,
                "action": c.action,
                "target_prior": c.target_prior,
                "target_change": c.target_change,
                "upside": (c.target / p0 - 1) if (c.target and p0) else None,
                "stale": stale,
                "rating_only": c.target is None and not dropped,
                "dropped": dropped,
                "outlier": False,
                "trust_score": s["score"] if s else None,
                "score_level": "analyst"
                if (c.analyst_key and c.analyst_key in scores)
                else ("firm" if s else None),
                "score_all": s.get("score_all") if s else None,
                "score_sector": s.get("score_sector") if s else None,
                "n_scored": s.get("n_scored", 0) if s else 0,
                "n_stocks": s.get("n_stocks", 0) if s else 0,
                "n_scored_ticker": s.get("n_scored_ticker", 0) if s else 0,
                "hits_ticker": s.get("hits_ticker", 0) if s else 0,
                "hit_count_ticker": s.get("hit_count_ticker", 0) if s else 0,
                "metrics": s.get("metrics") if s else None,
                "components": s.get("components") if s else None,
                "raw_all": _raw_view(s.get("raw_all")) if s else None,
                "bullish_share": s.get("bullish_share") if s else None,
                "herding": herd.get(c.analyst_key) if c.analyst_key else None,
                "limited": (s.get("n_scored", 0) if s else 0) < int(cfg["min_scored_calls_label"]),
                "url": c.url,
                "headline": c.headline,
                "source": c.source,
            }
        )
    rows.sort(key=lambda r: r["date"], reverse=True)
    rows.sort(key=lambda r: r["stale"])

    # ---- consensus ------------------------------------------------------------------------------
    cs = consensus(rows, p0, cfg, prior_score)
    rows.sort(key=lambda r: r["stale"])
    active = cs["active"]
    cons_all, cons_med, cons_tr, disp = cs["all"], cs["median"], cs["trusted"], cs["dispersion"]
    twr, avg_rating, up_all, up_tr = (
        cs["trust_weighted_rating"],
        cs["average_rating"],
        cs["upside_all"],
        cs["upside_trusted"],
    )
    for r in rows:
        r["weight"] = cs["weights"].get(r["who"])
    n_stale, n_outliers = cs["n_stale"], cs["n_outliers"]
    if cons_all and cons_tr:
        diff = cons_tr / cons_all - 1
        top = sorted(active, key=lambda r: -(r["weight"] or 0))[:3]
        explain = (
            f"All-analyst consensus ${cons_all:,.2f} is the plain average of {len(active)} active targets "
            f"(published in the last {cfg['stale_months']} months; {n_stale} older targets are excluded"
            + (
                f", as {'is' if n_outliers == 1 else 'are'} {n_outliers} more than {cfg['outlier_factor']:g}× away "
                "from the median, a likely data error"
                if n_outliers
                else ""
            )
            + "). "
            f"The trusted consensus ${cons_tr:,.2f} weights each target by the analyst's Trust Score raised to the power "
            f"{cfg['trusted_weight_gamma']:g}, so analysts with better records count more; it is {abs(diff):.1%} "
            f"{'above' if diff >= 0 else 'below'} the plain average. Most weight: "
            + ", ".join(
                f"{r['analyst'] or r['firm']} ({r['weight']:.0%} weight, score "
                + (f"{r['trust_score']:.0f}" if r["trust_score"] is not None else "n/a")
                + f", ${r['target']:,.0f})"
                for r in top
            )
            + "."
        )
    else:
        explain = f"No analyst targets from the last {cfg['stale_months']} months, so there is no consensus."

    src = f"{_source_name(calls)}; Trust Scores computed by the app"
    asof = ctx.as_of
    m = {
        "consensus_all": metric(
            "consensus_all", "All-analyst consensus target", cons_all, "usd_per_share", source=src, as_of=asof
        ),
        "consensus_median": metric(
            "consensus_median", "Median analyst target", cons_med, "usd_per_share", source=src, as_of=asof
        ),
        "consensus_trusted": metric(
            "consensus_trusted", "Trusted consensus target", cons_tr, "usd_per_share", source=src, as_of=asof
        ),
        "upside_all": metric(
            "upside_consensus_all", "Upside to all-analyst consensus", up_all, "pct", source=src, as_of=asof
        ),
        "upside_trusted": metric(
            "upside_trusted_consensus", "Upside to trusted consensus", up_tr, "pct", source=src, as_of=asof
        ),
        "trust_weighted_rating": metric(
            "trust_weighted_rating",
            "Trust-weighted analyst rating",
            twr,
            "ratio",
            source=src,
            as_of=asof,
            note=_rating_word(twr),
        ),
        "average_rating": metric(
            "average_rating",
            "Average analyst rating",
            avg_rating,
            "ratio",
            source=src,
            as_of=asof,
            note=_rating_word(avg_rating),
        ),
        "target_dispersion": metric(
            "target_dispersion", "Target dispersion", disp, "pct", source=src, as_of=asof
        ),
        "n_active": metric(
            "n_active_targets", "Active targets", len(active), "count", source=src, as_of=asof
        ),
        "target_high": metric(
            "target_high", "Highest active target", cs["high"], "usd_per_share", source=src, as_of=asof
        ),
        "target_low": metric(
            "target_low", "Lowest active target", cs["low"], "usd_per_share", source=src, as_of=asof
        ),
    }

    # ---- history: ratings and targets over time ---------------------------------------------------
    ends = month_ends(ctx.as_of, int(cfg["history_months"]))
    rh = {"dates": [], "buy": [], "hold": [], "sell": []}
    th = {"dates": [], "median": [], "high": [], "low": [], "n": [], "price": []}
    closes = ctx.prices["close"] if not ctx.prices.empty else None
    for d in ends:
        lat: dict[str, Call] = {}
        for c in calls:
            if c.date <= d and c.rating_norm is not None:
                lat[c.who] = c
        act = [c for c in lat.values() if (d - c.date).days <= rating_days]
        rh["dates"].append(d.isoformat())
        rh["buy"].append(sum(1 for c in act if c.rating_norm == 1))
        rh["hold"].append(sum(1 for c in act if c.rating_norm == 0))
        rh["sell"].append(sum(1 for c in act if c.rating_norm == -1))
        at = [c.target for c in active_targets(calls, d, stale_days).values()]
        th["dates"].append(d.isoformat())
        th["median"].append(float(np.median(at)) if at else None)
        th["high"].append(float(max(at)) if at else None)
        th["low"].append(float(min(at)) if at else None)
        th["n"].append(len(at))
        px = closes[closes.index <= np.datetime64(d)] if closes is not None else None
        th["price"].append(float(px.iloc[-1]) if px is not None and len(px) else None)
    eps = _eps_revisions(ctx)

    # ---- firm cards -------------------------------------------------------------------------------
    cards = _firm_cards(ctx, calls, firm_scores, cfg, rating_days)

    # ---- chart overlay: targets published in the chart's window --------------------------------------
    since = ctx.as_of - timedelta(days=int(cfg["history_months"]) * 31)
    overlay = [
        {
            "date": c.date.isoformat(),
            "target": c.target,
            "label": f"{c.firm}: ${c.target:,.2f}" + (f" ({c.rating})" if c.rating else ""),
        }
        for c in calls
        if c.target is not None and c.date >= since
    ]

    firms_table = sorted(
        (
            {
                "firm": f,
                "trust_score": s["score"],
                "n_scored": s["n_scored"],
                "n_stocks": s["n_stocks"],
                "metrics": s["metrics"],
                "raw_all": _raw_view(s.get("raw_all")),
            }
            for f, s in firm_scores.items()
            if f != "_population"
        ),
        key=lambda x: -(x["trust_score"] or 0),
    )
    k = cfg["shrinkage_k"]
    methodology = [
        f"Each past call is scored once its horizon has passed, using prices up to {ctx.as_of.isoformat()} only.",
        "Target accuracy: whether the closing price reached the target within 12 months, and the mean absolute "
        "percentage error between the target and the price 12 months later.",
        "Directional skill: the stock's total return minus the market's and the sector fund's at 3, 6 and 12 months, "
        "signed by the call (Buy +1, Sell −1; Holds are not directional). When a record has no rating, the direction "
        f"comes from the target (±{cfg['implied_direction_threshold']:.0%} from the price).",
        f"Recent calls count more (half-life {cfg['recency_half_life_years']:g} years). Small samples are shrunk toward "
        f"a prior worth {k} calls: this stock's record toward the analyst's sector record, that toward their record on "
        "all stocks, and that toward the average analyst.",
        "Always-bullish bias (target-implied return minus realized return) lowers the score; herding (how much of the gap "
        "to the other analysts' consensus a revision closes) is shown but not scored.",
        f"Targets older than {cfg['stale_months']} months are greyed out and excluded from both consensus figures.",
        f"Limitations: the history covers {res['n_tickers']} stocks in the app's database ({res['n_calls_scored']} scored calls), "
        "not every call an analyst ever made. Price targets usually have a 12-month horizon, but some firms use other "
        "horizons. Consecutive calls on one stock overlap in time, so the effective sample is smaller than the count.",
    ]
    return section(
        "analysts",
        status="ok",
        granularity=gran,
        granularity_label=GRANULARITY_LABELS[gran],
        rows=rows,
        metrics=m,
        consensus_all=cons_all,
        consensus_median=cons_med,
        consensus_trusted=cons_tr,
        trusted_upside=up_tr,
        all_upside=up_all,
        trust_weighted_rating=twr,
        trust_weighted_rating_label=_rating_word(twr),
        target_dispersion=disp,
        consensus_explain=explain,
        price=p0,
        rating_history=rh,
        target_history=th,
        eps_revisions=eps,
        firm_cards=cards,
        firms=firms_table,
        chart_targets=overlay,
        population={"score": prior_score, "metrics": pop.get("metrics")},
        coverage={
            "stocks": res["n_tickers"],
            "records": res["n_records"],
            "scored_calls": res["n_calls_scored"],
            "ingest_failures": res["ingest_failures"],
        },
        methodology=methodology,
        sources=[{"name": _source_name(calls), "as_of": ctx.as_of.isoformat()}],
    )


def _raw_view(r: dict | None) -> dict | None:
    if not r:
        return None
    return {k: (v["value"] if isinstance(v, dict) else v) for k, v in r.items()} | {
        f"{k}_count": v["count"] for k, v in r.items() if isinstance(v, dict)
    }


def _source_name(calls: list[Call]) -> str:
    srcs = sorted({c.source for c in calls if c.source})
    return " + ".join(srcs) if srcs else "analyst data"


def _eps_revisions(ctx: ReportContext) -> dict:
    if ctx.pit:
        return {"status": "missing", "reason": "estimate snapshots are not point-in-time"}
    rows = [
        r
        for r in ctx.data.estimate_history(ctx.ticker)
        if r["metric"] == "annual:eps" and r["mean"] is not None
    ]
    periods = sorted({r["period_end"] for r in rows if r["period_end"] > ctx.as_of})
    if not periods:
        return {"status": "missing", "reason": "no EPS estimates for upcoming fiscal years"}
    series = []
    for p in periods[:2]:
        pts = sorted((r["as_of"], r["mean"]) for r in rows if r["period_end"] == p)
        series.append(
            {"period_end": p.isoformat(), "points": [{"date": d.isoformat(), "mean": v} for d, v in pts]}
        )
    n = max(len(s["points"]) for s in series)
    if n < 2:
        first = min(pt["date"] for s in series for pt in s["points"])
        return {
            "status": "partial",
            "series": series,
            "reason": f"The app keeps one consensus snapshot per day; the revision history starts on {first} and builds up from there.",
        }
    return {"status": "ok", "series": series}


def _is_major(firm: str, majors: list[str]) -> int:
    f = firm.lower()
    for i, mj in enumerate(majors):
        if mj.lower() in f:
            return i
    return len(majors)


def _firm_cards(ctx, calls: list[Call], firm_scores: dict, cfg: dict, rating_days: int) -> list[dict]:
    by_firm: dict[str, list[Call]] = {}
    for c in calls:
        by_firm.setdefault(c.firm, []).append(c)
    cards = []
    for firm, cs in by_firm.items():
        cs.sort(key=lambda c: c.date)
        last = cs[-1]
        age = (ctx.as_of - last.date).days
        if age > rating_days:
            continue
        last_t = next((c for c in reversed(cs) if c.target is not None), None)
        prev_rating = last.rating_prior
        s = firm_scores.get(firm)
        summary = _action_sentence(last, prev_rating)
        cards.append(
            {
                "firm": firm,
                "analyst": last.analyst_name,
                "rating": last.rating,
                "rating_norm": last.rating_norm,
                "rating_prior": prev_rating,
                "action": last.action,
                "target": last_t.target if last_t else None,
                "target_prior": last_t.target_prior if last_t else None,
                "target_change": last_t.target_change if last_t else None,
                "date": last.date.isoformat(),
                "stale": (last_t is None) or (ctx.as_of - last_t.date).days > int(cfg["stale_months"]) * 30,
                "trust_score": s["score"] if s else None,
                "n_scored": s["n_scored"] if s else 0,
                "summary": summary,
                "reasoning": None,
                "reasoning_note": "The data feed does not include this firm's stated reasoning, so only the rating and target are shown.",
                "source_url": last.url or (last_t.url if last_t else None),
                "source_title": last.headline or (last_t.headline if last_t else None),
                "major": _is_major(firm, cfg["major_firms"]) < len(cfg["major_firms"]),
            }
        )
    cards.sort(key=lambda c: (_is_major(c["firm"], cfg["major_firms"]), -int(c["date"].replace("-", ""))))
    return cards


def _consensus_only(ctx: ReportContext, gran: str, label: str | None = None) -> dict:
    """Fallback when there is no per-analyst history: rating counts and the provider's target consensus."""
    trends = ctx.data.recommendation_trends(ctx.ticker)
    tc = ctx.data.target_consensus(ctx.ticker)
    rh = {"dates": [], "buy": [], "hold": [], "sell": []}
    for t in sorted(trends.value or [], key=lambda t: t.period):
        if t.period > ctx.as_of:
            continue
        rh["dates"].append(t.period.isoformat())
        rh["buy"].append(t.strong_buy + t.buy)
        rh["hold"].append(t.hold)
        rh["sell"].append(t.sell + t.strong_sell)
    has_counts = any(b + h + s for b, h, s in zip(rh["buy"], rh["hold"], rh["sell"], strict=True))
    tcv = tc.value if (tc.value and not ctx.pit) else None
    if not has_counts and not (tcv and tcv.mean):
        return section(
            "analysts",
            status="missing",
            reason="No analyst coverage in the data.",
            granularity=gran,
            granularity_label=GRANULARITY_LABELS[gran],
        )
    p0 = ctx.last_price
    mean = tcv.mean if tcv else None
    avg = None
    if has_counts:
        b, h, s = rh["buy"][-1], rh["hold"][-1], rh["sell"][-1]
        tot = b + h + s
        avg = (b - s) / tot if tot else None
    disp = ((tcv.high - tcv.low) / tcv.mean) if (tcv and tcv.high and tcv.low and tcv.mean) else None
    src = ", ".join(x for x in (trends.source if trends.value else None, tc.source if tcv else None) if x)
    return section(
        "analysts",
        status="partial",
        granularity="consensus",
        granularity_label=label or GRANULARITY_LABELS["consensus"],
        rows=[],
        metrics={
            "consensus_all": metric(
                "consensus_all", "Consensus target", mean, "usd_per_share", source=src, as_of=ctx.as_of
            ),
            "upside_all": metric(
                "upside_consensus_all",
                "Upside to consensus",
                (mean / p0 - 1) if (mean and p0) else None,
                "pct",
                source=src,
            ),
            "average_rating": metric(
                "average_rating", "Average analyst rating", avg, "ratio", source=src, note=_rating_word(avg)
            ),
            "target_dispersion": metric("target_dispersion", "Target dispersion", disp, "pct", source=src),
        },
        consensus_all=mean,
        consensus_trusted=None,
        trusted_upside=None,
        all_upside=(mean / p0 - 1) if (mean and p0) else None,
        trust_weighted_rating=None,
        target_dispersion=disp,
        consensus_explain="Analyst-level track records are unavailable on this data tier, so there is no trusted consensus; "
        "the figure shown is the provider's plain consensus.",
        rating_history=rh,
        target_history=None,
        eps_revisions=_eps_revisions(ctx),
        firm_cards=[],
        firms=[],
        chart_targets=[],
        methodology=[],
        sources=[{"name": src, "as_of": ctx.as_of.isoformat()}],
    )
