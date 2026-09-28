"""News and sentiment: deduplicated stories, per-story classification, a weighted sentiment index and a digest."""

from __future__ import annotations

import re
from datetime import timedelta

import pandas as pd

from engine.llm.client import llm_available, report_budget, report_id
from engine.news.aggregate import daily_series, label, story_weight, trend_label, window_score
from engine.news.classify import classify_clusters
from engine.news.clustering import cluster
from engine.news.digest import EVENT_LABELS, build_digest
from engine.report.context import ReportContext
from engine.report.metric import metric, section
from engine.settings import get_settings

_SUFFIX = re.compile(
    r"\b(inc|incorporated|corp|corporation|co|company|ltd|plc|holdings|group|the)\b\.?", re.I
)


def company_names(name: str) -> list[str]:
    base = re.sub(r"\(.*?\)", "", name)
    base = _SUFFIX.sub("", base).replace(",", " ")
    base = " ".join(base.split())
    first = base.split()[0] if base.split() else ""
    return [n for n in {base, first} if len(n) >= 4]


def reliability_fn(ctx: ReportContext):
    rc = ctx.cfg["news"]["reliability"]
    table = {k.lower(): v for k, v in {**rc["sources"], **(rc["synthetic"] if ctx.synthetic else {})}.items()}
    default = float(rc["default"])

    def rel(source: str | None) -> float:
        if not source:
            return default
        s = source.lower()
        if s in table:
            return float(table[s])
        for k, v in table.items():
            if k in s:
                return float(v)
        return default

    return rel


def build(ctx: ReportContext) -> dict:
    cfg = ctx.cfg["news"]
    fx = ctx.data.news(ctx.ticker)
    ctx.sources["news"] = fx.meta()
    if fx.value is None:
        return section("news", status="missing", reason=fx.reason or "no news provider configured")
    lookback = int(ctx.cfg.get("data.news_lookback_days", 365))
    start = ctx.as_of - timedelta(days=lookback)
    items = [i for i in fx.value if start < i.published_at.date() <= ctx.as_of]
    if not items:
        return section(
            "news", status="missing", reason=f"no news about this company in the last {lookback} days"
        )
    rel = reliability_fn(ctx)
    clusters = cluster(items, float(cfg["cluster_window_hours"]), float(cfg["cluster_similarity"]), rel)
    name = ctx.symbol.name
    names = company_names(name)
    use_llm = llm_available()
    budget = report_budget(ctx)
    rid = report_id(ctx)
    judg, calls = classify_clusters(clusters, name, ctx.ticker, names, report_id=rid, budget=budget)
    mat_w = cfg["materiality_weights"]
    stories = []
    for c in clusters:
        j = judg[c.id]
        rep = c.items[0]
        r = rel(rep.source_name)
        outlets = sorted({(i.source_name or i.provider) for i in c.items})
        stories.append(
            {
                "id": c.id,
                "headline": rep.headline,
                "url": rep.url,
                "source": rep.source_name or rep.provider,
                "provider": rep.provider,
                "sources": [
                    {"name": i.source_name or i.provider, "url": i.url, "provider": i.provider}
                    for i in c.items
                ],
                "n_sources": len(outlets),
                "published_at": c.first_seen.isoformat(),
                "date": c.first_seen.date(),
                "summary": j.get("summary"),
                "sentiment": float(j["sentiment"]),
                "relevance": float(j["relevance"]),
                "materiality": j["materiality"],
                "event_type": j["event_type"],
                "event_label": EVENT_LABELS[j["event_type"]],
                "suspicious": bool(j.get("suspicious")),
                "suspicious_reason": j.get("suspicious_reason"),
                "classified_by": j["classified_by"],
                "reliability": r,
                "weight": story_weight(j, r, len(outlets), mat_w),
            }
        )
    stories.sort(key=lambda s: s["published_at"], reverse=True)

    as_of = ctx.as_of
    s30, w30, n30 = window_score(stories, as_of - timedelta(days=30), as_of)
    s7, _, n7 = window_score(stories, as_of - timedelta(days=7), as_of)
    prior, _, _ = window_score(stories, as_of - timedelta(days=30), as_of - timedelta(days=7))
    series = daily_series(
        stories, start, as_of, float(cfg["sentiment_half_life_days"]), float(cfg["min_series_weight"])
    )
    closes = ctx.prices["close"] if not ctx.prices.empty else None
    if closes is not None:
        px = closes.reindex(pd.to_datetime(series["dates"]), method="ffill")
        series["price"] = [None if pd.isna(v) else round(float(v), 4) for v in px]
    else:
        series["price"] = [None] * len(series["dates"])

    digest, dcalls = build_digest(
        stories,
        as_of,
        ctx.ticker,
        name,
        use_llm=use_llm,
        model=get_settings().fast_model,
        report_id=rid,
        budget=budget,
    )
    calls += dcalls
    # Chart markers: the most material company-specific story per week, so the chart stays readable.
    weekly: dict[tuple[int, int], dict] = {}
    for s in stories:
        if s["suspicious"] or s["materiality"] != "high" or s["relevance"] < 0.8:
            continue
        wk = tuple(s["date"].isocalendar()[:2])
        cur = weekly.get(wk)
        if cur is None or s["weight"] * (0.2 + abs(s["sentiment"])) > cur["weight"] * (
            0.2 + abs(cur["sentiment"])
        ):
            weekly[wk] = s
    markers = [
        {
            "date": s["date"].isoformat(),
            "kind": "news",
            "label": s["headline"][:90],
            "detail": f"{s['event_label']} · {s['materiality']} materiality · sentiment {s['sentiment']:+.2f}",
            "url": s["url"],
            "tone": "good" if s["sentiment"] >= 0.2 else "bad" if s["sentiment"] <= -0.2 else "neutral",
        }
        for s in sorted(weekly.values(), key=lambda s: s["date"])
    ]
    by = {s["classified_by"].split(" (")[0] for s in stories}
    method = "llm" if by == {get_settings().fast_model} else "keyword" if by == {"keyword rules"} else "mixed"
    method_note = {
        "llm": f"Stories classified by {get_settings().fast_model}; summaries are the model's own words, checked in code.",
        "mixed": f"Recent stories classified by {get_settings().fast_model}; older ones (or ones the model could not handle) by keyword rules.",
        "keyword": "The LLM is not configured, so stories are classified by keyword rules on the headline: sentiment and "
        "event types are approximate and there are no summaries. Set ANTHROPIC_API_KEY to enable model summaries.",
    }[method]
    paid = [c for c in calls if not c.cached and (c.input_tokens or c.output_tokens)]
    cost = {
        "calls": len(paid),
        "cached": sum(1 for c in calls if c.cached),
        "input_tokens": sum(c.input_tokens for c in paid),
        "output_tokens": sum(c.output_tokens for c in paid),
        "usd": round(sum(c.cost_usd for c in paid), 6),
        "budget_tokens": budget.total,
        "budget_used": budget.used,
        "errors": sorted({c.error for c in calls if c.error}),
    }
    src = f"{fx.source}; classification: {'model' if method != 'keyword' else 'keyword rules'}"
    for s in stories:
        s["date"] = s["date"].isoformat()
    return section(
        "news",
        status="ok",
        method=method,
        method_note=method_note,
        stories=stories,
        n_items=len(items),
        n_stories=len(stories),
        series=series,
        sentiment_30d=s30,
        sentiment_7d=s7,
        sentiment_prior=prior,
        trend=trend_label(s7, prior),
        markers=markers,
        digest=digest,
        cost=cost,
        metrics={
            "sentiment_30d": metric(
                "news_sentiment_30d",
                "News sentiment (30 days)",
                s30,
                "ratio",
                source=src,
                as_of=as_of,
                note=label(s30),
                extra={"stories": n30, "weight": w30},
            ),
            "sentiment_7d": metric(
                "news_sentiment_7d",
                "News sentiment (7 days)",
                s7,
                "ratio",
                source=src,
                as_of=as_of,
                note=label(s7),
                extra={"stories": n7},
            ),
            "stories_30d": metric(
                "news_stories_30d", "Stories (30 days)", n30, "count", source=src, as_of=as_of
            ),
        },
        social={
            "status": "not_configured",
            "note": "Social-media sentiment is not configured. It is noisy, and the app only uses official APIs within their terms.",
        },
        sources=[{"name": fx.source, "as_of": as_of.isoformat()}],
    )
