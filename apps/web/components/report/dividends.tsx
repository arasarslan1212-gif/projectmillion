"use client";

import { useCallback } from "react";
import { axisStyle, baseOption, EChart } from "@/components/charts/echart";
import { ScoreBar } from "@/components/report/trust";
import { MetricCell } from "@/components/ui/metric";
import { formatDate, formatValue } from "@/lib/format";
import type { ThemeColors } from "@/lib/theme";
import type { AnySection } from "@/lib/types";
import { TileBox, Tiles } from "./earnings";

const COMPONENT_LABELS: Record<string, string> = {
  earnings_payout: "Earnings payout",
  fcf_payout: "Free-cash-flow payout",
  leverage: "Leverage (net debt ÷ EBITDA)",
  stability: "Earnings stability",
  streak: "Growth streak",
};

function YieldHistory({ h }: { h: AnySection }) {
  const build = useCallback(
    (c: ThemeColors) => ({
      ...baseOption(c),
      legend: { show: false },
      tooltip: {
        ...(baseOption(c).tooltip as object),
        valueFormatter: (x: number) => formatValue(x, "pct", { digits: 2 }),
      },
      grid: { left: 8, right: 56, top: 16, bottom: 8, containLabel: true },
      xAxis: {
        type: "category",
        data: h.dates,
        boundaryGap: false,
        ...axisStyle(c),
        splitLine: { show: false },
        axisLabel: { color: c.muted, formatter: (d: string) => d.slice(0, 4) },
      },
      yAxis: {
        type: "value",
        scale: true,
        ...axisStyle(c),
        axisLabel: { color: c.muted, formatter: (x: number) => formatValue(x, "pct", { digits: 1 }) },
      },
      series: [
        {
          name: "Yield",
          type: "line",
          data: h.yield,
          symbol: "none",
          lineStyle: { width: 2, color: c.series[0] },
          itemStyle: { color: c.series[0] },
          markLine: {
            symbol: "none",
            silent: true,
            data: [
              ...(h.avg_5y !== null
                ? [
                    {
                      yAxis: h.avg_5y,
                      lineStyle: { color: c.muted, type: "dashed", width: 1 },
                      label: { formatter: "5y avg", color: c.ink2, fontSize: 10 },
                    },
                  ]
                : []),
              ...(h.sector !== null
                ? [
                    {
                      yAxis: h.sector,
                      lineStyle: { color: c.series[2], type: "dashed", width: 1 },
                      label: { formatter: "Peers", color: c.ink2, fontSize: 10 },
                    },
                  ]
                : []),
            ],
          },
        },
      ],
    }),
    [h],
  );
  return (
    <EChart
      height={200}
      ariaLabel="Trailing twelve-month dividend yield at each month end, with its five-year average and the peer median"
      build={build}
    />
  );
}

export function DividendsSection({ d }: { d: AnySection }) {
  const m = d.metrics;
  return (
    <div className="space-y-5">
      <Tiles>
        <TileBox
          sub={
            <>
              5-year average {formatValue(m.yield_5y_avg.value, "pct", { digits: 2 })} · peers{" "}
              {formatValue(m.sector_yield.value, "pct", { digits: 2 })}
            </>
          }
        >
          <MetricCell m={m.yield} emphasize digits={2} />
        </TileBox>
        <TileBox sub={<>free cash flow {formatValue(m.payout_fcf.value, "pct", { digits: 0 })}</>}>
          <MetricCell m={m.payout_earnings} emphasize digits={0} />
        </TileBox>
        <TileBox
          sub={
            <>
              5y CAGR {formatValue(m.cagr_5y.value, "pct", { signed: true })} · 10y{" "}
              {formatValue(m.cagr_10y.value, "pct", { signed: true })}
            </>
          }
        >
          <MetricCell m={m.streak} emphasize digits={0} />
        </TileBox>
        <TileBox sub={d.safety_level ?? undefined}>
          <MetricCell m={m.safety} emphasize />
        </TileBox>
      </Tiles>
      <div className="grid gap-5 lg:grid-cols-2">
        <div>
          <h3 className="mb-1 text-sm font-semibold">Yield against its own history</h3>
          <YieldHistory h={d.yield_history} />
          <p className="text-xs text-muted">
            Today&apos;s yield is higher than in {formatValue(m.yield_percentile.value, "pct", { digits: 0 })}{" "}
            of the last 60 month-ends.
          </p>
        </div>
        <div>
          <h3 className="mb-2 text-sm font-semibold">
            Why the safety score is {d.safety_level?.toLowerCase()}
          </h3>
          <ul className="space-y-1.5">
            {d.safety_components.map((c: AnySection) => (
              <li key={c.id} className="flex items-center gap-3 text-xs">
                <span className="w-44 shrink-0 text-ink-2">{COMPONENT_LABELS[c.id] ?? c.id}</span>
                {c.skipped ? (
                  <span className="text-muted">not used for this profile</span>
                ) : (
                  <ScoreBar score={c.score} label={COMPONENT_LABELS[c.id]} />
                )}
                <span className="text-muted">weight {formatValue(c.weight, "pct", { digits: 0 })}</span>
              </li>
            ))}
          </ul>
          <h3 className="mt-4 mb-1 text-sm font-semibold">Recent ex-dividend dates</h3>
          <table className="tabular w-full text-xs">
            <tbody>
              {d.events.slice(0, 6).map((e: AnySection) => (
                <tr key={e.ex_date} className="border-t border-line">
                  <td className="py-1">{formatDate(e.ex_date)}</td>
                  <td className="py-1 text-right">{formatValue(e.amount, "usd_per_share", { digits: 4 })}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-1 text-xs text-muted">{d.pay_dates_note}</p>
        </div>
      </div>
    </div>
  );
}
