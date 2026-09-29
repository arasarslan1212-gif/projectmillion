"use client";

import { useCallback } from "react";
import { axisStyle, baseOption, EChart } from "@/components/charts/echart";
import { MetricCell, MetricTip } from "@/components/ui/metric";
import { cn } from "@/lib/cn";
import { formatDate, formatValue } from "@/lib/format";
import type { ThemeColors } from "@/lib/theme";
import type { AnySection, Metric } from "@/lib/types";
import { ScoreBar } from "./trust";

function FlowsChart({ flows }: { flows: AnySection[] }) {
  const build = useCallback(
    (c: ThemeColors) => ({
      ...baseOption(c),
      legend: { show: false },
      grid: { left: 8, right: 56, top: 8, bottom: 8, containLabel: true },
      tooltip: {
        ...(baseOption(c).tooltip as object),
        axisPointer: { type: "shadow" },
        formatter: (ps: { dataIndex: number }[]) => {
          const f = flows[ps[0].dataIndex];
          return `${f.label}: <b>${formatValue(f.value, "usd")}</b>${f.share_of_cfo != null ? ` (${formatValue(f.share_of_cfo, "pct", { digits: 0 })} of operating cash)` : ""}`;
        },
      },
      xAxis: {
        type: "value",
        ...axisStyle(c),
        axisLabel: { color: c.muted, formatter: (x: number) => formatValue(x, "usd", { digits: 0 }) },
      },
      yAxis: {
        type: "category",
        inverse: true,
        data: flows.map((f) => f.label),
        ...axisStyle(c),
        splitLine: { show: false },
        axisLabel: { color: c.ink2 },
      },
      series: [
        {
          type: "bar",
          barMaxWidth: 18,
          data: flows.map((f) => ({
            value: f.value,
            itemStyle: {
              color: f.value >= 0 ? c.divergePos : c.divergeNeg,
              borderRadius: f.value >= 0 ? [0, 4, 4, 0] : [4, 0, 0, 4],
            },
          })),
          label: {
            show: true,
            position: "right",
            color: c.ink2,
            fontSize: 10,
            formatter: (p: { value: number }) => formatValue(p.value, "usd", { digits: 1 }),
          },
        },
      ],
    }),
    [flows],
  );
  return (
    <EChart
      build={build}
      height={Math.max(160, 34 * flows.length + 24)}
      ariaLabel="Where the cash came from and went over the window"
      table={{
        caption: "Sources and uses of cash",
        columns: ["Item", "Amount", "Share of operating cash"],
        rows: flows.map((f) => [
          f.label,
          formatValue(f.value, "usd"),
          formatValue(f.share_of_cfo, "pct", { digits: 0 }),
        ]),
      }}
    />
  );
}

export function CapitalSection({ c }: { c: AnySection }) {
  const score = c.score as Metric;
  const comps = c.components as AnySection[];
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
        <div>
          <MetricTip m={score}>
            <button
              type="button"
              className="text-left text-xs text-muted underline decoration-dotted underline-offset-2"
            >
              Capital allocation score
            </button>
          </MetricTip>
          <div className="tabular text-2xl font-semibold">
            {score.value == null ? (
              <span className="text-base text-muted">Not enough to score</span>
            ) : (
              <>
                {formatValue(score.value, "score")}
                <span className="text-base text-muted">/100</span>{" "}
                <span
                  className={cn(
                    "text-base",
                    c.level === "Strong" && "text-good-ink",
                    c.level === "Weak" && "text-critical-ink",
                    c.level === "Mixed" && "text-warning-ink",
                  )}
                >
                  {c.level}
                </span>
              </>
            )}
          </div>
        </div>
        <p className="max-w-xl text-xs text-muted">
          How management used the cash the business produced over fiscal years {formatDate(c.window.start)} to{" "}
          {formatDate(c.window.end)}. The app&apos;s assessment; it is not part of the Trust Rating.
        </p>
      </div>

      <ul className="divide-y divide-[var(--border)] rounded-lg border border-line">
        {comps.map((k) => (
          <li
            key={k.id}
            className="grid gap-2 px-3 py-2.5 sm:grid-cols-[12rem_8rem_minmax(0,1fr)] sm:items-start"
          >
            <div className="text-sm font-medium">{k.label}</div>
            <div className="sm:pt-0.5">
              {k.score == null ? (
                <span className="text-xs text-muted">Not scored</span>
              ) : (
                <ScoreBar score={k.score} label={`${k.label} score`} />
              )}
            </div>
            <div className="min-w-0 text-sm text-ink-2">
              {k.skipped ? (
                <span className="text-xs text-muted">{k.skipped[0].toUpperCase() + k.skipped.slice(1)}.</span>
              ) : (
                k.verdict
              )}
              {k.metrics?.length > 0 && (
                <div className="mt-1.5 grid grid-cols-2 gap-3 sm:grid-cols-3">
                  {k.metrics.map((m: Metric) => (
                    <MetricCell key={m.id} m={m} />
                  ))}
                </div>
              )}
            </div>
          </li>
        ))}
      </ul>

      {c.sources_uses?.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold">Where the cash came from and went</h3>
          <p className="mt-0.5 text-xs text-muted">
            Totals over the window, from the cash-flow statements. Blue brought cash in; red paid it out.
          </p>
          <FlowsChart flows={c.sources_uses} />
        </div>
      )}

      <div className="rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm">
        <div className="font-medium">Acquisitions</div>
        <p className="mt-0.5 text-ink-2">
          {c.mna.acquisitions
            ? `${formatValue(c.mna.acquisitions, "usd")} spent on acquisitions in the window. `
            : ""}
          {c.mna.goodwill_start != null && c.mna.goodwill_end != null
            ? `Goodwill went from ${formatValue(c.mna.goodwill_start, "usd")} to ${formatValue(c.mna.goodwill_end, "usd")}. `
            : ""}
          {c.mna.note[0].toUpperCase() + c.mna.note.slice(1)}
        </p>
        {c.mna.goodwill_to_assets?.value != null && (
          <div className="mt-2 max-w-[14rem]">
            <MetricCell m={c.mna.goodwill_to_assets} />
          </div>
        )}
      </div>
    </div>
  );
}
