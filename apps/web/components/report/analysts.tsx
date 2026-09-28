"use client";

import * as Collapsible from "@radix-ui/react-collapsible";
import { ChevronDown, ExternalLink } from "lucide-react";
import { Fragment, useCallback, useMemo, useState } from "react";
import { axisStyle, baseOption, EChart } from "@/components/charts/echart";
import { ScoreBar } from "@/components/report/trust";
import { Badge } from "@/components/ui/badge";
import { MetricTip } from "@/components/ui/metric";
import { cn } from "@/lib/cn";
import { formatDate, formatValue } from "@/lib/format";
import type { ThemeColors } from "@/lib/theme";
import { withAlpha } from "@/lib/theme";
import type { AnySection, Metric } from "@/lib/types";

const ACTION_LABEL: Record<string, string> = {
  initiation: "Initiation",
  upgrade: "Upgrade",
  downgrade: "Downgrade",
  reiteration: "Reiteration",
  termination: "Coverage dropped",
};

function ratingColor(c: ThemeColors, norm: number | null | undefined): string {
  return norm === 1 ? c.divergePos : norm === -1 ? c.divergeNeg : c.muted;
}

/** Shape carries the rating as well as color: ▲ Buy, ● Hold, ▼ Sell. */
function RatingGlyph({ norm }: { norm: number | null | undefined }) {
  const cls =
    norm === 1 ? "text-[var(--diverge-pos)]" : norm === -1 ? "text-[var(--diverge-neg)]" : "text-muted";
  return (
    <span className={cn("inline-block w-3 text-center text-[10px]", cls)} aria-hidden>
      {norm === 1 ? "▲" : norm === -1 ? "▼" : "●"}
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
        {m.unit === "ratio" && m.note ? m.note : formatValue(m.value, m.unit)}
      </div>
      {sub && <div className="mt-0.5 text-xs text-ink-2">{sub}</div>}
    </div>
  );
}

function DotPlot({ a, appTarget }: { a: AnySection; appTarget?: number | null }) {
  const rows: AnySection[] = useMemo(
    () =>
      a.rows.filter((r: AnySection) => r.target).sort((x: AnySection, y: AnySection) => x.target - y.target),
    [a.rows],
  );
  const build = useCallback(
    (c: ThemeColors) => {
      const names = rows.map((r) => `${r.analyst ? r.analyst.replace(" (Synthetic)", "") : r.firm}`);
      const lines = [
        { name: "Today", value: a.price, color: c.ink, type: "solid" },
        { name: "All", value: a.consensus_all, color: c.muted, type: "dashed" },
        { name: "Trusted", value: a.consensus_trusted, color: c.series[2], type: "dashed" },
        { name: "App P50", value: appTarget, color: c.series[0], type: "dotted" },
      ].filter((l) => typeof l.value === "number");
      return {
        ...baseOption(c),
        legend: { show: false },
        grid: { left: 8, right: 24, top: 30, bottom: 8, containLabel: true },
        tooltip: {
          ...(baseOption(c).tooltip as object),
          trigger: "item",
          formatter: (p: { dataIndex: number }) => {
            const r = rows[p.dataIndex];
            return `<b>${r.analyst ?? r.firm}</b><br/>${r.firm}<br/>${r.rating ?? "No rating"} · ${formatValue(r.target, "usd_per_share")} (${formatValue(r.upside, "pct", { signed: true })})<br/>${formatDate(r.date)}${r.stale ? " · stale, excluded" : ""}<br/>Trust Score ${r.trust_score !== null ? Math.round(r.trust_score) : "n/a"}`;
          },
        },
        xAxis: {
          type: "value",
          scale: true,
          ...axisStyle(c),
          axisLabel: {
            color: c.muted,
            formatter: (x: number) => formatValue(x, "usd_per_share", { digits: 0 }),
          },
        },
        yAxis: {
          type: "category",
          data: names,
          ...axisStyle(c),
          splitLine: { show: false },
          axisLabel: { color: c.ink2, width: 150, overflow: "truncate" },
        },
        series: [
          {
            type: "scatter",
            data: rows.map((r) => ({
              value: [r.target, names[rows.indexOf(r)]],
              symbol: r.rating_norm === 0 || r.rating_norm === null ? "circle" : "triangle",
              symbolRotate: r.rating_norm === -1 ? 180 : 0,
              symbolSize: 8 + ((r.trust_score ?? 40) / 100) * 10,
              itemStyle: r.stale
                ? { color: "transparent", borderColor: c.muted, borderWidth: 1.5 }
                : { color: ratingColor(c, r.rating_norm), borderColor: c.surface, borderWidth: 2 },
            })),
            markLine: {
              symbol: "none",
              silent: true,
              data: lines.map((l) => ({
                xAxis: l.value,
                lineStyle: { color: l.color, type: l.type, width: l.name === "Today" ? 1.5 : 1.25 },
                label: {
                  show: l.name === "Today",
                  formatter: l.name,
                  color: c.ink2,
                  fontSize: 10,
                  position: "end",
                },
              })),
            },
          },
        ],
      };
    },
    [rows, a.price, a.consensus_all, a.consensus_trusted, appTarget],
  );
  if (!rows.length) return <p className="text-xs text-muted">No price targets to plot.</p>;
  return (
    <EChart
      height={Math.max(160, 30 + rows.length * 26)}
      ariaLabel="Dot plot of analyst price targets with today's price and both consensus figures"
      build={build}
      table={{
        caption: "Analyst targets",
        columns: ["Analyst", "Firm", "Rating", "Target", "Date", "Stale", "Trust Score"],
        rows: [...rows]
          .reverse()
          .map((r) => [
            r.analyst ?? "—",
            r.firm,
            r.rating ?? "—",
            formatValue(r.target, "usd_per_share"),
            r.date,
            r.stale ? "yes" : "no",
            r.trust_score !== null ? Math.round(r.trust_score) : "n/a",
          ]),
      }}
      footer={
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted">
          <span>
            ▲ Buy-equivalent · ● Hold · ▼ Sell-equivalent · size = Trust Score · hollow = stale (excluded)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-3 w-0.5 bg-ink" aria-hidden /> Today{" "}
            {formatValue(a.price, "usd_per_share")}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-3 border-l border-dashed border-muted" aria-hidden /> All{" "}
            {formatValue(a.consensus_all, "usd_per_share")}
          </span>
          {a.consensus_trusted && (
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-3 border-l-2 border-dashed border-[var(--s3)]" aria-hidden />{" "}
              Trusted {formatValue(a.consensus_trusted, "usd_per_share")}
            </span>
          )}
          {appTarget && (
            <span className="flex items-center gap-1.5">
              <span className="inline-block h-3 border-l-2 border-dotted border-[var(--s1)]" aria-hidden />{" "}
              App P50 {formatValue(appTarget, "usd_per_share")}
            </span>
          )}
        </div>
      }
    />
  );
}

function RatingHistory({ rh }: { rh: AnySection }) {
  const build = useCallback(
    (c: ThemeColors) => ({
      ...baseOption(c),
      tooltip: { ...(baseOption(c).tooltip as object), axisPointer: { type: "shadow" } },
      legend: { ...(baseOption(c).legend as object), data: ["Buy", "Hold", "Sell"] },
      grid: { left: 8, right: 8, top: 30, bottom: 8, containLabel: true },
      xAxis: {
        type: "category",
        data: rh.dates.map((d: string) => d.slice(0, 7)),
        ...axisStyle(c),
        splitLine: { show: false },
      },
      yAxis: { type: "value", minInterval: 1, ...axisStyle(c) },
      series: [
        { name: "Buy", color: c.divergePos, data: rh.buy },
        { name: "Hold", color: c.muted, data: rh.hold },
        { name: "Sell", color: c.divergeNeg, data: rh.sell },
      ].map((s, i) => ({
        ...s,
        type: "bar",
        stack: "r",
        barCategoryGap: "25%",
        itemStyle: {
          color: s.color,
          borderColor: c.surface,
          borderWidth: 1,
          borderRadius: i === 2 ? [3, 3, 0, 0] : 0,
        },
      })),
    }),
    [rh],
  );
  return (
    <EChart
      height={220}
      ariaLabel="Number of Buy, Hold and Sell ratings at each month end"
      build={build}
      table={{
        caption: "Ratings over time",
        columns: ["Month", "Buy", "Hold", "Sell"],
        rows: rh.dates.map((d: string, i: number) => [d, rh.buy[i], rh.hold[i], rh.sell[i]]),
      }}
    />
  );
}

function TargetHistory({ th }: { th: AnySection }) {
  const build = useCallback(
    (c: ThemeColors) => ({
      ...baseOption(c),
      legend: { ...(baseOption(c).legend as object), data: ["Median target", "Price"] },
      tooltip: {
        ...(baseOption(c).tooltip as object),
        formatter: (ps: { dataIndex: number }[]) => {
          const i = ps[0].dataIndex;
          return `<b>${th.dates[i]}</b><br/>Median target ${formatValue(th.median[i], "usd_per_share")} (${th.n[i]} active)<br/>Range ${formatValue(th.low[i], "usd_per_share")}–${formatValue(th.high[i], "usd_per_share")}<br/>Price ${formatValue(th.price[i], "usd_per_share")}`;
        },
      },
      grid: { left: 8, right: 16, top: 30, bottom: 8, containLabel: true },
      xAxis: {
        type: "category",
        data: th.dates.map((d: string) => d.slice(0, 7)),
        boundaryGap: false,
        ...axisStyle(c),
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        scale: true,
        ...axisStyle(c),
        axisLabel: {
          color: c.muted,
          formatter: (x: number) => formatValue(x, "usd_per_share", { digits: 0 }),
        },
      },
      series: [
        {
          name: "low",
          type: "line",
          data: th.low,
          stack: "band",
          symbol: "none",
          lineStyle: { opacity: 0 },
          tooltip: { show: false },
        },
        {
          name: "range",
          type: "line",
          data: th.high.map((h: number | null, i: number) =>
            h !== null && th.low[i] !== null ? h - th.low[i] : null,
          ),
          stack: "band",
          symbol: "none",
          lineStyle: { opacity: 0 },
          areaStyle: { color: withAlpha(c.series[2], 0.12) },
        },
        {
          name: "Median target",
          type: "line",
          data: th.median,
          symbol: "circle",
          symbolSize: 5,
          lineStyle: { width: 2, color: c.series[2] },
          itemStyle: { color: c.series[2] },
        },
        {
          name: "Price",
          type: "line",
          data: th.price,
          symbol: "none",
          lineStyle: { width: 2, color: c.ink2 },
          itemStyle: { color: c.ink2 },
        },
      ],
    }),
    [th],
  );
  return (
    <EChart
      height={220}
      ariaLabel="Median active analyst target at each month end, with the range of targets and the share price"
      build={build}
      table={{
        caption: "Target revisions",
        columns: ["Month", "Median target", "Low", "High", "Active", "Price"],
        rows: th.dates.map((d: string, i: number) => [
          d,
          formatValue(th.median[i], "usd_per_share"),
          formatValue(th.low[i], "usd_per_share"),
          formatValue(th.high[i], "usd_per_share"),
          th.n[i],
          formatValue(th.price[i], "usd_per_share"),
        ]),
      }}
      footer={<span className="text-xs text-muted">Shaded band: lowest to highest active target.</span>}
    />
  );
}

function EpsRevisions({ e }: { e: AnySection }) {
  const build = useCallback(
    (c: ThemeColors) => ({
      ...baseOption(c),
      xAxis: { type: "time", ...axisStyle(c), splitLine: { show: false } },
      yAxis: { type: "value", scale: true, ...axisStyle(c) },
      series: e.series.map((s: AnySection, i: number) => ({
        name: `FY ending ${s.period_end}`,
        type: "line",
        data: s.points.map((p: AnySection) => [p.date, p.mean]),
        symbol: "circle",
        symbolSize: 5,
        lineStyle: { width: 2, color: c.series[i] },
        itemStyle: { color: c.series[i] },
      })),
    }),
    [e],
  );
  if (e.status === "missing")
    return <p className="text-xs text-muted">EPS estimate revisions: {e.reason}.</p>;
  return (
    <div>
      {e.status === "ok" && (
        <EChart height={200} ariaLabel="Consensus EPS estimate snapshots over time" build={build} />
      )}
      {e.reason && <p className="text-xs text-muted">{e.reason}</p>}
    </div>
  );
}

function AnalystTable({ rows }: { rows: AnySection[] }) {
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="overflow-x-auto">
      <table className="tabular w-full min-w-[860px] text-xs">
        <caption className="sr-only">Analysts covering the stock, their latest call and Trust Score</caption>
        <thead className="text-muted">
          <tr className="text-left">
            <th className="py-1 font-medium">Analyst</th>
            <th className="py-1 font-medium">Rating</th>
            <th className="py-1 text-right font-medium">Target</th>
            <th className="py-1 pl-3 text-right font-medium">Prior</th>
            <th className="py-1 pl-3 font-medium">Date</th>
            <th className="py-1 pl-3 font-medium">Trust Score</th>
            <th className="py-1 pl-2 text-right font-medium">Calls scored</th>
            <th className="py-1 pl-3 text-right font-medium">On this stock</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const isOpen = open === r.who;
            return (
              <Fragment key={r.who}>
                <tr className={cn("border-t border-line align-top", r.stale && "text-muted")}>
                  <td className="py-1.5 pr-2">
                    <button
                      type="button"
                      onClick={() => setOpen(isOpen ? null : r.who)}
                      aria-expanded={isOpen}
                      className="flex items-start gap-1 text-left"
                    >
                      <ChevronDown
                        className={cn("mt-0.5 size-3 shrink-0 transition-transform", isOpen && "rotate-180")}
                        aria-hidden
                      />
                      <span>
                        <span className="font-medium">{r.analyst ?? r.firm}</span>
                        {r.analyst && <span className="block text-muted">{r.firm}</span>}
                      </span>
                    </button>
                  </td>
                  <td className="py-1.5 pr-2">
                    <span className="flex items-center gap-1">
                      <RatingGlyph norm={r.rating_norm} />
                      {r.rating ?? "—"}
                    </span>
                    <span className="block pl-4 text-muted">
                      {ACTION_LABEL[r.action] ?? r.action}
                      {r.rating_source === "carried" ? " · rating carried from prior note" : ""}
                    </span>
                  </td>
                  <td className="py-1.5 text-right font-medium">
                    {formatValue(r.target, "usd_per_share")}
                    <span className="block font-normal text-muted">
                      {formatValue(r.upside, "pct", { signed: true, digits: 0 })}
                    </span>
                  </td>
                  <td className="py-1.5 pl-3 text-right">
                    {formatValue(r.target_prior, "usd_per_share")}
                    {r.target_change !== null && r.target_change !== undefined && (
                      <span className="block text-muted">
                        {formatValue(r.target_change, "pct", { signed: true, digits: 0 })}
                      </span>
                    )}
                  </td>
                  <td className="whitespace-nowrap py-1.5 pl-3">
                    {formatDate(r.date)}
                    {r.stale && (
                      <span className="block text-muted">
                        {r.dropped
                          ? "coverage dropped · excluded"
                          : r.rating_only
                            ? "rating only, no target"
                            : r.outlier
                              ? "likely data error · excluded"
                              : "stale · excluded"}
                      </span>
                    )}
                  </td>
                  <td className="py-1.5 pl-3">
                    <ScoreBar score={r.trust_score} label={`Trust Score for ${r.analyst ?? r.firm}`} />
                    {r.score_level === "firm" && <span className="text-muted">firm score</span>}
                    {r.limited && <span className="text-muted">limited history</span>}
                  </td>
                  <td className="py-1.5 pl-2 text-right">
                    {r.n_scored}
                    <span className="block text-muted">{r.n_stocks} stocks</span>
                  </td>
                  <td className="py-1.5 pl-3 text-right">
                    {r.hit_count_ticker ? `${r.hits_ticker}/${r.hit_count_ticker} hit` : "—"}
                    <span className="block text-muted">{r.n_scored_ticker} scored</span>
                  </td>
                </tr>
                {isOpen && (
                  <tr className="bg-surface-2/50">
                    <td colSpan={8} className="px-3 py-2">
                      <AnalystDetail r={r} />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function AnalystDetail({ r }: { r: AnySection }) {
  const m = r.metrics ?? {};
  const raw = r.raw_all ?? {};
  const comps = r.components ?? {};
  const items: [string, string, string, number | null][] = [
    [
      "Targets reached within 12 months",
      formatValue(m.hit_rate, "pct", { digits: 0 }),
      `raw ${formatValue(raw.hit_rate, "pct", { digits: 0 })} over ${raw.hit_rate_count ?? 0} matured targets`,
      comps.hit_rate ?? null,
    ],
    [
      "Mean absolute error at 12 months",
      formatValue(m.mape, "pct", { digits: 0 }),
      `raw ${formatValue(raw.mape, "pct", { digits: 0 })}`,
      comps.accuracy ?? null,
    ],
    [
      "Excess return of Buy/Sell calls",
      formatValue(m.directional, "pct", { signed: true }),
      `vs. market and sector fund, 3/6/12 months; raw ${formatValue(raw.directional, "pct", { signed: true })} over ${raw.directional_count ?? 0} calls`,
      comps.directional ?? null,
    ],
    [
      "Optimism bias",
      formatValue(m.optimism_bias, "pct", { signed: true }),
      "target-implied return minus realized return (lower is better)",
      comps.bias ?? null,
    ],
  ];
  return (
    <div className="grid gap-3 md:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <ul className="space-y-1.5">
        {items.map(([k, v, note, score]) => (
          <li key={k} className="flex flex-wrap items-center gap-x-3">
            <span className="w-52 text-ink-2">{k}</span>
            <span className="w-14 font-medium">{v}</span>
            <ScoreBar score={score} label={k} />
            <span className="text-muted">{note}</span>
          </li>
        ))}
      </ul>
      <div className="space-y-1 text-ink-2">
        <div>
          Score on all stocks {r.score_all !== null ? Math.round(r.score_all) : "n/a"} · in this sector{" "}
          {r.score_sector !== null ? Math.round(r.score_sector) : "n/a"} · for this stock{" "}
          {r.trust_score !== null ? Math.round(r.trust_score) : "n/a"} (shrunk toward the broader records)
        </div>
        <div>
          Buy-equivalent share of ratings: {formatValue(r.bullish_share, "pct", { digits: 0 })}
          {r.herding && (
            <>
              {" "}
              · herding: revisions close {formatValue(r.herding.value, "pct", { digits: 0 })} of the gap to
              the consensus (n={r.herding.n})
            </>
          )}
        </div>
        {r.url && (
          <a
            href={r.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-accent-ink underline"
          >
            Source{r.headline ? `: ${r.headline}` : ""} <ExternalLink className="size-3" aria-hidden />
          </a>
        )}
      </div>
    </div>
  );
}

function FirmCard({ f }: { f: AnySection }) {
  return (
    <div className={cn("flex min-w-0 flex-col rounded-lg border border-line p-3", f.stale && "opacity-80")}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold" title={f.firm}>
            {f.firm}
          </div>
          {f.analyst && <div className="truncate text-xs text-muted">{f.analyst}</div>}
        </div>
        <div className="shrink-0 text-right">
          <div className="text-[10px] uppercase tracking-wide text-muted">Firm Trust Score</div>
          <ScoreBar score={f.trust_score} label={`Firm Trust Score for ${f.firm}`} />
        </div>
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="flex items-center gap-1 text-sm font-medium">
          <RatingGlyph norm={f.rating_norm} />
          {f.rating ?? "No rating"}
        </span>
        <span className="text-sm">{formatValue(f.target, "usd_per_share")}</span>
        {f.target_change !== null && f.target_change !== undefined && (
          <span className="text-xs text-muted">
            {formatValue(f.target_change, "pct", { signed: true, digits: 0 })}
          </span>
        )}
        <span className="ml-auto text-xs text-muted">{formatDate(f.date)}</span>
      </div>
      <p className="mt-1.5 text-xs text-ink-2">{f.summary}</p>
      <p className="mt-1 text-xs text-muted">{f.reasoning ?? f.reasoning_note}</p>
      {f.source_url && (
        <a
          href={f.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-auto inline-flex min-w-0 max-w-full items-center gap-1 pt-1.5 text-xs text-accent-ink underline"
        >
          <span className="truncate">{f.source_title ?? "Source"}</span>
          <ExternalLink className="size-3 shrink-0" aria-hidden />
        </a>
      )}
    </div>
  );
}

export function AnalystsSection({ a, appTarget }: { a: AnySection; appTarget?: number | null }) {
  const m = a.metrics;
  const [showStale, setShowStale] = useState(false);
  const rows: AnySection[] = a.rows ?? [];
  const shown = showStale ? rows : rows.filter((r) => !r.stale);
  const nStale = rows.length - rows.filter((r) => !r.stale).length;
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Badge tone={a.granularity === "analyst" ? "accent" : "warning"}>{a.granularity_label}</Badge>
        {a.coverage && (
          <span className="text-muted">
            Track records from {a.coverage.scored_calls} scored calls on {a.coverage.stocks} stocks in the
            app&apos;s history.
          </span>
        )}
      </div>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile
          m={m.consensus_all}
          sub={
            <>
              {formatValue(m.upside_all.value, "pct", { signed: true })} vs. price · {m.n_active?.value ?? 0}{" "}
              active
            </>
          }
        />
        {m.consensus_trusted ? (
          <Tile
            m={m.consensus_trusted}
            sub={
              <>
                {formatValue(m.upside_trusted.value, "pct", { signed: true })} vs. price · weighted by Trust
                Score
              </>
            }
          />
        ) : (
          <div className="rounded-lg border border-line p-3 text-xs text-muted">
            Trusted consensus unavailable: no analyst-level track records on this data tier.
          </div>
        )}
        <Tile
          m={m.trust_weighted_rating ?? m.average_rating}
          sub={
            m.trust_weighted_rating ? (
              <>
                {formatValue(m.trust_weighted_rating.value, "ratio", { signed: true })} on −1…+1 · plain
                average {m.average_rating.note ?? "—"}
              </>
            ) : (
              <>{formatValue(m.average_rating.value, "ratio", { signed: true })} on −1…+1</>
            )
          }
        />
        <Tile
          m={m.target_dispersion}
          sub={
            m.target_low && m.target_high ? (
              <>
                {formatValue(m.target_low.value, "usd_per_share")}–
                {formatValue(m.target_high.value, "usd_per_share")}
              </>
            ) : undefined
          }
        />
      </div>
      <p className="text-xs text-ink-2">
        {a.consensus_explain} These are analysts&apos; views, not the app&apos;s.
      </p>

      {rows.length > 0 && (
        <div>
          <h3 className="mb-1 text-sm font-semibold">All targets</h3>
          <DotPlot a={a} appTarget={appTarget} />
        </div>
      )}

      {rows.length > 0 && (
        <div>
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold">Analysts and their records</h3>
            {nStale > 0 && (
              <button
                type="button"
                className="text-xs text-accent-ink underline"
                onClick={() => setShowStale((x) => !x)}
              >
                {showStale ? "Hide" : "Show"} {nStale} stale {nStale === 1 ? "call" : "calls"}
              </button>
            )}
          </div>
          <AnalystTable rows={shown} />
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {a.rating_history?.dates?.length > 0 && (
          <div>
            <h3 className="mb-1 text-sm font-semibold">Ratings over time</h3>
            <RatingHistory rh={a.rating_history} />
          </div>
        )}
        {a.target_history && (
          <div>
            <h3 className="mb-1 text-sm font-semibold">Target revisions</h3>
            <TargetHistory th={a.target_history} />
          </div>
        )}
      </div>
      {a.eps_revisions && (
        <div>
          <h3 className="mb-1 text-sm font-semibold">EPS estimate revisions</h3>
          <EpsRevisions e={a.eps_revisions} />
        </div>
      )}

      {a.firm_cards?.length > 0 && (
        <div>
          <h3 className="mb-2 text-sm font-semibold">Bank and broker views</h3>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {a.firm_cards.map((f: AnySection) => (
              <FirmCard key={f.firm} f={f} />
            ))}
          </div>
          <p className="mt-1 text-xs text-muted">
            Summaries are the app&apos;s own description of each firm&apos;s latest published rating and
            target, with a link to the public headline. The app never reproduces research reports.
          </p>
        </div>
      )}

      {a.methodology?.length > 0 && (
        <Collapsible.Root>
          <Collapsible.Trigger className="group flex items-center gap-1 text-xs font-medium text-accent-ink">
            <ChevronDown
              className="size-3 transition-transform group-data-[state=open]:rotate-180"
              aria-hidden
            />
            How Trust Scores work, and their limits
          </Collapsible.Trigger>
          <Collapsible.Content>
            <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-ink-2">
              {a.methodology.map((x: string) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
            {a.firms?.length > 0 && (
              <div className="mt-3 overflow-x-auto">
                <table className="tabular w-full min-w-[520px] text-xs">
                  <caption className="mb-1 text-left text-xs font-medium text-ink">Firm-level scores</caption>
                  <thead className="text-muted">
                    <tr className="text-left">
                      <th className="py-1 font-medium">Firm</th>
                      <th className="py-1 font-medium">Trust Score</th>
                      <th className="py-1 text-right font-medium">Calls scored</th>
                      <th className="py-1 text-right font-medium">Target hit rate</th>
                      <th className="py-1 text-right font-medium">Excess return</th>
                    </tr>
                  </thead>
                  <tbody>
                    {a.firms.map((f: AnySection) => (
                      <tr key={f.firm} className="border-t border-line">
                        <td className="py-1">{f.firm}</td>
                        <td className="py-1">
                          <ScoreBar score={f.trust_score} label={`Firm Trust Score for ${f.firm}`} />
                        </td>
                        <td className="py-1 text-right">{f.n_scored}</td>
                        <td className="py-1 text-right">
                          {formatValue(f.metrics?.hit_rate, "pct", { digits: 0 })}
                        </td>
                        <td className="py-1 text-right">
                          {formatValue(f.metrics?.directional, "pct", { signed: true })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Collapsible.Content>
        </Collapsible.Root>
      )}
    </div>
  );
}
