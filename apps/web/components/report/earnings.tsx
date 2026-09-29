"use client";

import { useCallback } from "react";
import { axisStyle, baseOption, EChart } from "@/components/charts/echart";
import { MetricCell } from "@/components/ui/metric";
import { cn } from "@/lib/cn";
import { formatDate, formatValue } from "@/lib/format";
import type { ThemeColors } from "@/lib/theme";
import type { AnySection } from "@/lib/types";

export function Tiles({ children }: { children: React.ReactNode }) {
  return <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">{children}</div>;
}

export function TileBox({ children, sub }: { children: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div className="min-w-0 rounded-lg border border-line p-3">
      {children}
      {sub && <div className="mt-0.5 text-xs text-ink-2">{sub}</div>}
    </div>
  );
}

function SurpriseChart({ rows }: { rows: AnySection[] }) {
  const data = [...rows].reverse();
  const build = useCallback(
    (c: ThemeColors) => ({
      ...baseOption(c),
      legend: { show: false },
      tooltip: {
        ...(baseOption(c).tooltip as object),
        axisPointer: { type: "shadow" },
        formatter: (ps: { dataIndex: number }[]) => {
          const r = data[ps[0].dataIndex];
          return `<b>${formatDate(r.date)}</b><br/>EPS ${formatValue(r.eps_actual, "usd_per_share")} vs. estimate ${formatValue(r.eps_estimate, "usd_per_share")} (${formatValue(r.eps_surprise, "pct", { signed: true })})<br/>Next-session move ${formatValue(r.reaction_1d, "pct", { signed: true })}`;
        },
      },
      grid: { left: 8, right: 8, top: 16, bottom: 8, containLabel: true },
      xAxis: {
        type: "category",
        data: data.map((r) => r.date.slice(0, 7)),
        ...axisStyle(c),
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        ...axisStyle(c),
        axisLabel: { color: c.muted, formatter: (x: number) => formatValue(x, "pct", { digits: 0 }) },
      },
      series: [
        {
          name: "EPS surprise",
          type: "bar",
          barCategoryGap: "30%",
          data: data.map((r) => ({
            value: r.eps_surprise,
            itemStyle: {
              color: (r.eps_surprise ?? 0) >= 0 ? c.divergePos : c.divergeNeg,
              borderRadius: (r.eps_surprise ?? 0) >= 0 ? [3, 3, 0, 0] : [0, 0, 3, 3],
            },
          })),
        },
      ],
    }),
    [data],
  );
  return (
    <EChart
      height={200}
      ariaLabel="EPS surprise versus consensus for each of the last 12 quarters"
      build={build}
      footer={<span className="text-xs text-muted">Bars above zero are beats, below zero misses.</span>}
    />
  );
}

export function EarningsSection({ e }: { e: AnySection }) {
  const m = e.metrics;
  const rows: AnySection[] = e.quarters ?? [];
  const nextDays: number | null = e.next_in_days ?? null;
  return (
    <div className="space-y-5">
      <Tiles>
        <TileBox sub={<>{m.beat_rate.n} quarters</>}>
          <MetricCell m={m.beat_rate} emphasize digits={0} />
        </TileBox>
        <TileBox sub={<>typical surprise {formatValue(m.avg_eps_surprise.value, "pct", { signed: true })}</>}>
          <MetricCell m={m.revenue_beat_rate} emphasize digits={0} />
        </TileBox>
        <TileBox
          sub={e.implied_move?.status === "not_available" ? "options-implied move not configured" : undefined}
        >
          <MetricCell m={m.avg_move} emphasize />
        </TileBox>
        <TileBox
          sub={
            e.next_date
              ? `${e.next_timing === "amc" ? "after close" : e.next_timing === "bmo" ? "before open" : "timing not announced"}${nextDays !== null && nextDays >= 0 ? ` · in ${nextDays} days` : ""}`
              : undefined
          }
        >
          <MetricCell m={m.next_date} emphasize />
        </TileBox>
      </Tiles>
      {rows.length > 0 && <SurpriseChart rows={rows} />}
      {rows.length > 0 && (
        <div className="overflow-x-auto">
          <table className="tabular w-full min-w-[720px] text-xs">
            <caption className="sr-only">
              Last 12 quarters: EPS and revenue versus estimates, and the stock&apos;s reaction
            </caption>
            <thead className="text-muted">
              <tr>
                <th className="py-1 text-left font-medium">Reported</th>
                <th className="py-1 text-right font-medium">EPS</th>
                <th className="py-1 text-right font-medium">Estimate</th>
                <th className="py-1 text-right font-medium">Surprise</th>
                <th className="py-1 text-right font-medium">Revenue</th>
                <th className="py-1 text-right font-medium">Surprise</th>
                <th className="py-1 text-right font-medium">1-day move</th>
                <th className="py-1 text-right font-medium">5-day move</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.date} className="border-t border-line">
                  <td className="py-1.5">
                    {formatDate(r.date)}
                    <span className="block text-muted">{r.timing}</span>
                  </td>
                  <td className="py-1.5 text-right">{formatValue(r.eps_actual, "usd_per_share")}</td>
                  <td className="py-1.5 text-right text-ink-2">
                    {formatValue(r.eps_estimate, "usd_per_share")}
                  </td>
                  <td
                    className={cn(
                      "py-1.5 text-right font-medium",
                      (r.eps_surprise ?? 0) >= 0 ? "text-accent-ink" : "text-critical-ink",
                    )}
                  >
                    {formatValue(r.eps_surprise, "pct", { signed: true })}
                  </td>
                  <td className="py-1.5 text-right">{formatValue(r.revenue_actual, "usd")}</td>
                  <td className="py-1.5 text-right">
                    {formatValue(r.revenue_surprise, "pct", { signed: true })}
                  </td>
                  <td className="py-1.5 text-right">{formatValue(r.reaction_1d, "pct", { signed: true })}</td>
                  <td className="py-1.5 text-right">{formatValue(r.reaction_5d, "pct", { signed: true })}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <div className="grid gap-4 md:grid-cols-2">
        <div>
          <h3 className="mb-1 text-sm font-semibold">Post-earnings drift</h3>
          <p className="text-xs text-ink-2">
            Over the 20 sessions after a report, versus the market: after beats{" "}
            {formatValue(m.drift_beats.value, "pct", { signed: true })} on average ({m.drift_beats.n}{" "}
            reports), after misses {formatValue(m.drift_misses.value, "pct", { signed: true })} (
            {m.drift_misses.n} reports). Small samples; a description of the past, not a forecast.
          </p>
        </div>
        <div>
          <h3 className="mb-1 text-sm font-semibold">Estimate revisions</h3>
          {e.revisions?.rows?.length ? (
            <table className="tabular w-full text-xs">
              <thead className="text-muted">
                <tr>
                  <th className="py-1 text-left font-medium">EPS consensus</th>
                  {e.revisions.windows.map((w: number) => (
                    <th key={w} className="py-1 text-right font-medium">
                      {w}d
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {e.revisions.rows.map((r: AnySection) => (
                  <tr key={r.period_end} className="border-t border-line">
                    <td className="py-1">
                      {r.label} ({formatValue(r.current, "usd_per_share")})
                    </td>
                    {e.revisions.windows.map((w: number) => (
                      <td key={w} className="py-1 text-right">
                        {formatValue(r[`d${w}`], "pct", { signed: true })}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {e.revisions?.note && <p className="mt-1 text-xs text-muted">{e.revisions.note}</p>}
        </div>
      </div>
      <p className="text-xs text-muted">
        {e.guidance?.note} Earnings-call transcripts are not used (no licensed source is configured).
      </p>
    </div>
  );
}
