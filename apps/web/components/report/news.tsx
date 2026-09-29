"use client";

import { AlertTriangle, ExternalLink } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { axisStyle, baseOption, EChart } from "@/components/charts/echart";
import { Badge } from "@/components/ui/badge";
import { MetricTip } from "@/components/ui/metric";
import { Segmented } from "@/components/ui/segmented";
import { cn } from "@/lib/cn";
import { formatDate, formatValue } from "@/lib/format";
import type { ThemeColors } from "@/lib/theme";
import type { AnySection, Metric } from "@/lib/types";

const EVENT_LABELS: Record<string, string> = {
  earnings: "Earnings",
  guidance: "Guidance",
  "m&a": "M&A",
  legal_regulatory: "Legal / regulatory",
  product: "Product",
  management: "Management",
  macro: "Macro",
  analyst_action: "Analyst action",
  capital_return: "Capital return",
  other: "Other",
};

function sentimentWord(s: number | null | undefined): string {
  if (s === null || s === undefined) return "—";
  if (s >= 0.35) return "Positive";
  if (s >= 0.1) return "Slightly positive";
  if (s > -0.1) return "Neutral";
  if (s > -0.35) return "Slightly negative";
  return "Negative";
}

/** Sentiment carries a glyph as well as color: ▲ positive, ● neutral, ▼ negative. */
function SentimentChip({ s }: { s: number }) {
  const pos = s >= 0.1;
  const neg = s <= -0.1;
  return (
    <span
      className={cn(
        "tabular inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-xs font-medium",
        pos && "bg-[var(--diverge-pos)]/12 text-accent-ink",
        neg && "bg-[var(--diverge-neg)]/12 text-critical-ink",
        !pos && !neg && "bg-surface-2 text-ink-2",
      )}
      title={`Sentiment ${s.toFixed(2)} on a −1 to +1 scale`}
    >
      <span aria-hidden className="text-[9px]">
        {pos ? "▲" : neg ? "▼" : "●"}
      </span>
      {formatValue(s, "ratio", { signed: true })}
    </span>
  );
}

function Tile({ m, sub }: { m: Metric; sub?: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-line p-3">
      <MetricTip m={m}>
        <button
          type="button"
          className="text-left text-xs text-muted underline decoration-muted/50 decoration-dotted underline-offset-2"
        >
          {m.label}
        </button>
      </MetricTip>
      <div className="mt-0.5 text-xl font-semibold">
        {m.unit === "ratio"
          ? typeof m.value === "number"
            ? sentimentWord(m.value)
            : "—"
          : formatValue(m.value, m.unit)}
      </div>
      {sub && <div className="mt-0.5 text-xs text-ink-2">{sub}</div>}
    </div>
  );
}

/** Price (top) and the weighted sentiment index (bottom) on one shared time axis: two panels, never two y-scales. */
function SentimentVsPrice({ series }: { series: AnySection }) {
  const build = useCallback(
    (c: ThemeColors) => {
      const dates: string[] = series.dates;
      return {
        ...baseOption(c),
        legend: { show: false },
        axisPointer: { link: [{ xAxisIndex: "all" }] },
        tooltip: {
          ...(baseOption(c).tooltip as object),
          formatter: (ps: { dataIndex: number }[]) => {
            const i = ps[0].dataIndex;
            const s = series.sentiment[i];
            return `<b>${formatDate(dates[i])}</b><br/>Price ${formatValue(series.price[i], "usd_per_share")}<br/>Sentiment index ${
              s === null
                ? "— (too little news)"
                : `${s >= 0 ? "+" : ""}${s.toFixed(2)} (${sentimentWord(s).toLowerCase()})`
            }<br/>New stories that day: ${series.stories[i]}`;
          },
        },
        grid: [
          { left: 8, right: 16, top: 8, height: "52%", containLabel: true },
          { left: 8, right: 16, top: "64%", bottom: 8, containLabel: true },
        ],
        xAxis: [
          {
            type: "category",
            data: dates,
            gridIndex: 0,
            ...axisStyle(c),
            axisLabel: { show: false },
            splitLine: { show: false },
          },
          {
            type: "category",
            data: dates,
            gridIndex: 1,
            ...axisStyle(c),
            splitLine: { show: false },
            axisLabel: {
              color: c.muted,
              // one label per month, on its first trading day
              interval: (i: number, d: string) => i > 0 && d.slice(0, 7) !== dates[i - 1].slice(0, 7),
              formatter: (d: string) => d.slice(0, 7),
            },
          },
        ],
        yAxis: [
          {
            type: "value",
            gridIndex: 0,
            scale: true,
            ...axisStyle(c),
            axisLabel: {
              color: c.muted,
              formatter: (x: number) => formatValue(x, "usd_per_share", { digits: 0 }),
            },
          },
          { type: "value", gridIndex: 1, min: -1, max: 1, interval: 0.5, ...axisStyle(c) },
        ],
        series: [
          {
            name: "Price",
            type: "line",
            xAxisIndex: 0,
            yAxisIndex: 0,
            data: series.price,
            symbol: "none",
            lineStyle: { width: 2, color: c.ink2 },
            itemStyle: { color: c.ink2 },
          },
          ...(
            [
              ["Positive", c.divergePos, (v: number | null) => (v === null ? null : Math.max(v, 0))],
              ["Negative", c.divergeNeg, (v: number | null) => (v === null ? null : Math.min(v, 0))],
            ] as const
          ).map(([name, color, part], k) => ({
            name,
            type: "line",
            xAxisIndex: 1,
            yAxisIndex: 1,
            data: (series.sentiment as (number | null)[]).map(part),
            symbol: "none",
            connectNulls: false,
            lineStyle: { width: 1.5, color },
            itemStyle: { color },
            areaStyle: { origin: 0, color, opacity: 0.22 },
            markLine:
              k === 0
                ? {
                    symbol: "none",
                    silent: true,
                    lineStyle: { color: c.axis, type: "solid", width: 1 },
                    label: { show: false },
                    data: [{ yAxis: 0 }],
                  }
                : undefined,
          })),
        ],
      };
    },
    [series],
  );
  return (
    <EChart
      height={300}
      ariaLabel="Share price and the weighted news sentiment index over the last year, in two stacked panels"
      build={build}
      table={{
        caption: "News sentiment and price",
        columns: ["Date", "Price", "Sentiment index", "New stories"],
        rows: series.dates
          .map((d: string, i: number) => [
            d,
            formatValue(series.price[i], "usd_per_share"),
            series.sentiment[i] === null ? "—" : series.sentiment[i].toFixed(2),
            series.stories[i],
          ])
          .filter((r: (string | number)[]) => r[3] !== 0),
      }}
      footer={
        <span className="text-xs text-muted">
          Top: share price. Bottom: sentiment index (−1 to +1), decaying with a 7-day half-life; blank where
          there was too little news.
        </span>
      }
    />
  );
}

function DigestCard({ d }: { d: AnySection }) {
  return (
    <div className="rounded-lg border border-line p-3">
      <div className="flex items-baseline justify-between gap-2">
        <h4 className="text-sm font-semibold">Last {d.days} days</h4>
        <span className="text-xs text-muted">
          {d.written_by === "template"
            ? "Summary generated from the data"
            : `Written by ${d.written_by}, numbers checked`}
        </span>
      </div>
      <p className="mt-1 text-sm text-ink-2">{d.text}</p>
      {d.top?.length > 0 && (
        <ul className="mt-2 space-y-1 text-xs">
          {d.top.map((t: AnySection) => (
            <li key={t.url} className="flex items-start gap-2">
              <SentimentChip s={t.sentiment} />
              <a
                href={t.url}
                target="_blank"
                rel="noopener noreferrer"
                className="min-w-0 text-ink hover:underline"
              >
                {t.headline}
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function StoryRow({ s, showSummary }: { s: AnySection; showSummary: boolean }) {
  const extra = s.n_sources - 1;
  return (
    <li className={cn("border-t border-line py-2.5", s.suspicious && "bg-warning/5")}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted">
        <time dateTime={s.published_at}>{formatDate(s.date)}</time>
        <span>·</span>
        <span>{s.source}</span>
        {extra > 0 && (
          <span title={(s.sources as unknown as { name: string }[]).map((x) => x.name).join(", ")}>
            + {extra} more {extra === 1 ? "outlet" : "outlets"}
          </span>
        )}
        <span className="ml-auto flex flex-wrap items-center gap-1.5">
          <Badge>{EVENT_LABELS[s.event_type] ?? s.event_type}</Badge>
          <Badge tone={s.materiality === "high" ? "accent" : "neutral"}>{s.materiality} materiality</Badge>
          <span title="How much the story is about this company (0–1)">
            relevance {s.relevance.toFixed(1)}
          </span>
          <SentimentChip s={s.sentiment} />
        </span>
      </div>
      <a
        href={s.url}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-1 inline-flex items-start gap-1 text-sm font-medium text-ink hover:underline"
      >
        {s.headline}
        <ExternalLink className="mt-1 size-3 shrink-0 text-muted" aria-hidden />
      </a>
      {showSummary && s.summary && <p className="mt-0.5 text-sm text-ink-2">{s.summary}</p>}
      {s.suspicious && (
        <p className="mt-1 flex items-start gap-1.5 text-xs text-warning-ink">
          <AlertTriangle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          Possible manipulation attempt: {s.suspicious_reason}. Excluded from sentiment.
        </p>
      )}
    </li>
  );
}

export function NewsSection({ n }: { n: AnySection }) {
  const [event, setEvent] = useState<string>("all");
  const [minMat, setMinMat] = useState<"all" | "medium" | "high">("all");
  const [limit, setLimit] = useState(20);
  const stories: AnySection[] = n.stories;
  const eventCounts = useMemo(() => {
    const m = new Map<string, number>();
    for (const s of stories) m.set(s.event_type, (m.get(s.event_type) ?? 0) + 1);
    return [...m.entries()].sort((a, b) => b[1] - a[1]);
  }, [stories]);
  const filtered = stories.filter(
    (s) =>
      (event === "all" || s.event_type === event) &&
      (minMat === "all" || s.materiality === "high" || (minMat === "medium" && s.materiality === "medium")),
  );
  const m = n.metrics;
  const hasSummaries = stories.some((s) => s.summary);
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge tone={n.method === "keyword" ? "warning" : "accent"}>
          {n.method === "keyword"
            ? "Keyword classification"
            : n.method === "llm"
              ? "Model classification"
              : "Model + keyword classification"}
        </Badge>
        <span className="text-muted">{n.method_note}</span>
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile
          m={m.sentiment_30d}
          sub={
            m.sentiment_30d.value !== null ? (
              <>
                {formatValue(m.sentiment_30d.value, "ratio", { signed: true })} on −1…+1 ·{" "}
                {m.stories_30d.value} stories
              </>
            ) : (
              "No weighted news in the last 30 days"
            )
          }
        />
        <Tile
          m={m.sentiment_7d}
          sub={
            <>
              {m.sentiment_7d.value !== null
                ? `${formatValue(m.sentiment_7d.value, "ratio", { signed: true })} · `
                : ""}
              trend: {n.trend}
            </>
          }
        />
        <div className="rounded-lg border border-line p-3">
          <div className="text-xs text-muted">Stories in the last year</div>
          <div className="mt-0.5 text-xl font-semibold">{n.n_stories}</div>
          <div className="mt-0.5 text-xs text-ink-2">from {n.n_items} articles after merging duplicates</div>
        </div>
        <div className="rounded-lg border border-line p-3">
          <div className="text-xs text-muted">Social sentiment</div>
          <div className="mt-0.5 text-xl font-semibold">Not configured</div>
          <div className="mt-0.5 text-xs text-ink-2">{n.social?.note}</div>
        </div>
      </div>

      <div>
        <h3 className="mb-1 text-sm font-semibold">Sentiment against price</h3>
        <SentimentVsPrice series={n.series} />
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold">What changed</h3>
        <div className="grid gap-3 md:grid-cols-2">
          <DigestCard d={n.digest.d7} />
          <DigestCard d={n.digest.d30} />
        </div>
      </div>

      <div>
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold">Stories</h3>
          <label className="flex items-center gap-1 text-xs text-ink-2">
            Event
            <select
              value={event}
              onChange={(e) => {
                setEvent(e.target.value);
                setLimit(20);
              }}
              className="rounded-md border border-line bg-surface px-1.5 py-0.5 text-xs"
            >
              <option value="all">All ({stories.length})</option>
              {eventCounts.map(([k, v]) => (
                <option key={k} value={k}>
                  {EVENT_LABELS[k] ?? k} ({v})
                </option>
              ))}
            </select>
          </label>
          <Segmented
            label="Minimum materiality"
            value={minMat}
            onChange={(x) => {
              setMinMat(x);
              setLimit(20);
            }}
            options={[
              { value: "all", label: "All" },
              { value: "medium", label: "Medium+" },
              { value: "high", label: "High" },
            ]}
          />
        </div>
        {!hasSummaries && (
          <p className="text-xs text-muted">
            Summaries need the LLM, which is not configured; only headlines and links are shown.
          </p>
        )}
        <ul>
          {filtered.slice(0, limit).map((s) => (
            <StoryRow key={s.id} s={s} showSummary={hasSummaries} />
          ))}
        </ul>
        {filtered.length > limit && (
          <button
            type="button"
            className="mt-1 text-xs text-accent-ink underline"
            onClick={() => setLimit((l) => l + 30)}
          >
            Show more ({filtered.length - limit} remaining)
          </button>
        )}
        {filtered.length === 0 && <p className="text-xs text-muted">No stories match these filters.</p>}
      </div>

      <p className="text-xs text-muted">
        Headlines and links only; the app never stores or shows full articles. Summaries, when shown, are
        written by the model in its own words from the headline and the provider&apos;s short teaser. All
        fetched text is treated as untrusted data.
        {n.cost?.calls > 0 && (
          <>
            {" "}
            LLM usage for this section: {n.cost.calls} {n.cost.calls === 1 ? "call" : "calls"},{" "}
            {n.cost.input_tokens + n.cost.output_tokens} tokens, ${n.cost.usd.toFixed(4)}
            {n.cost.cached ? ` (${n.cost.cached} cached)` : ""}.
          </>
        )}
      </p>
    </div>
  );
}
