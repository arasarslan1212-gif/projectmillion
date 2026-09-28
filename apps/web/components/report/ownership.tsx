"use client";

import { ExternalLink } from "lucide-react";
import { useCallback, useState } from "react";
import { axisStyle, baseOption, EChart } from "@/components/charts/echart";
import { Badge } from "@/components/ui/badge";
import { MetricCell } from "@/components/ui/metric";
import { Segmented } from "@/components/ui/segmented";
import { cn } from "@/lib/cn";
import { formatDate, formatValue } from "@/lib/format";
import type { ThemeColors } from "@/lib/theme";
import type { AnySection } from "@/lib/types";
import { TileBox, Tiles } from "./earnings";

function ShortChart({ series }: { series: AnySection[] }) {
  const build = useCallback(
    (c: ThemeColors) => ({
      ...baseOption(c),
      legend: { show: false },
      tooltip: {
        ...(baseOption(c).tooltip as object),
        formatter: (ps: { dataIndex: number }[]) => {
          const s = series[ps[0].dataIndex];
          return `<b>${formatDate(s.date)}</b><br/>${formatValue(s.pct_float, "pct", { digits: 2 })} of float · ${formatValue(s.days_to_cover, "days")} to cover`;
        },
      },
      grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
      xAxis: {
        type: "category",
        data: series.map((s) => s.date),
        ...axisStyle(c),
        splitLine: { show: false },
        axisLabel: { color: c.muted, formatter: (d: string) => d.slice(0, 7) },
      },
      yAxis: {
        type: "value",
        scale: true,
        ...axisStyle(c),
        axisLabel: { color: c.muted, formatter: (x: number) => formatValue(x, "pct", { digits: 1 }) },
      },
      series: [
        {
          name: "Short interest",
          type: "line",
          data: series.map((s) => s.pct_float),
          symbolSize: 5,
          lineStyle: { width: 2, color: c.series[0] },
          itemStyle: { color: c.series[0] },
        },
      ],
    }),
    [series],
  );
  return (
    <EChart
      height={180}
      ariaLabel="Short interest as a share of float at each FINRA settlement date"
      build={build}
    />
  );
}

export function OwnershipSection({ o }: { o: AnySection }) {
  const m = o.metrics;
  const [signalOnly, setSignalOnly] = useState<"signal" | "all">("signal");
  const ins = o.insiders;
  const rows: AnySection[] = (ins?.rows ?? []).filter(
    (r: AnySection) => signalOnly === "all" || r.class === "purchase" || r.class === "sale",
  );
  const bb = o.buybacks;
  const si = o.short_interest;
  return (
    <div className="space-y-5">
      <Tiles>
        <TileBox
          sub={
            ins?.clusters?.length ? `${ins.clusters.length} cluster buy(s) in 24 months` : "no cluster buying"
          }
        >
          <MetricCell m={m.insider_buy_6m} emphasize />
        </TileBox>
        <TileBox sub={m.insider_sell_6m.note ?? undefined}>
          <MetricCell m={m.insider_sell_6m} emphasize />
        </TileBox>
        <TileBox
          sub={
            si ? (
              <>
                {formatValue(m.days_to_cover.value, "days")} to cover · {si.trend ?? "trend n/a"}
              </>
            ) : undefined
          }
        >
          <MetricCell m={m.short_pct} emphasize digits={2} />
        </TileBox>
        <TileBox sub={<>buyback yield {formatValue(m.buyback_yield.value, "pct", { digits: 1 })}</>}>
          <MetricCell m={m.share_change_3y} emphasize signed />
        </TileBox>
      </Tiles>

      {ins?.clusters?.length > 0 && (
        <div className="rounded-lg border border-accent/40 bg-accent-wash/40 p-3 text-sm">
          <span className="font-medium">Cluster buying:</span>{" "}
          {ins.clusters
            .map(
              (c: AnySection) =>
                `${c.insiders.length} insiders bought ${formatValue(c.value, "usd")} between ${formatDate(c.start)} and ${formatDate(c.end)}`,
            )
            .join("; ")}
          . Several insiders buying on the open market at once is the strongest insider signal.
        </div>
      )}

      {ins && (
        <div>
          <div className="mb-1 flex flex-wrap items-center gap-2">
            <h3 className="text-sm font-semibold">Insider transactions (Form 4, 24 months)</h3>
            <Segmented
              label="Transactions shown"
              value={signalOnly}
              onChange={setSignalOnly}
              options={[
                { value: "signal", label: "Open-market only" },
                { value: "all", label: "All" },
              ]}
            />
          </div>
          {rows.length === 0 ? (
            <p className="text-xs text-muted">No transactions of this kind.</p>
          ) : (
            <div className="max-h-80 overflow-auto">
              <table className="tabular w-full min-w-[680px] text-xs">
                <thead className="sticky top-0 bg-surface text-muted">
                  <tr>
                    <th className="py-1 text-left font-medium">Date</th>
                    <th className="py-1 text-left font-medium">Insider</th>
                    <th className="py-1 text-left font-medium">Type</th>
                    <th className="py-1 text-right font-medium">Shares</th>
                    <th className="py-1 text-right font-medium">Price</th>
                    <th className="py-1 text-right font-medium">Value</th>
                    <th className="py-1 pl-2 text-left font-medium">Filing</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(0, 40).map((r, i) => (
                    <tr key={`${r.date}-${r.name}-${i}`} className="border-t border-line">
                      <td className="py-1">{formatDate(r.date)}</td>
                      <td className="py-1">
                        {r.name}
                        {r.role && <span className="block text-muted">{r.role}</span>}
                      </td>
                      <td className="py-1">
                        <span
                          className={cn(r.class === "purchase" && "font-medium text-[var(--diverge-pos)]")}
                        >
                          {r.label}
                        </span>
                        {r.plan_10b5_1 && (
                          <Badge className="ml-1" title="Pre-arranged trading plan: a weak signal">
                            10b5-1
                          </Badge>
                        )}
                      </td>
                      <td className="py-1 text-right">{formatValue(r.shares, "shares", { digits: 0 })}</td>
                      <td className="py-1 text-right">
                        {r.price ? formatValue(r.price, "usd_per_share") : "—"}
                      </td>
                      <td className="py-1 text-right">{formatValue(r.value, "usd")}</td>
                      <td className="py-1 pl-2">
                        {r.url && (
                          <a
                            href={r.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center gap-0.5 text-accent-ink"
                          >
                            SEC <ExternalLink className="size-3" aria-hidden />
                          </a>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <div>
          <h3 className="mb-1 text-sm font-semibold">Largest institutional holders (13F)</h3>
          {o.institutions ? (
            <>
              <table className="tabular w-full text-xs">
                <thead className="text-muted">
                  <tr>
                    <th className="py-1 text-left font-medium">Holder</th>
                    <th className="py-1 text-right font-medium">% of shares</th>
                    <th className="py-1 text-right font-medium">Change (shares)</th>
                  </tr>
                </thead>
                <tbody>
                  {o.institutions.top.map((h: AnySection) => (
                    <tr key={h.holder} className="border-t border-line">
                      <td className="py-1">{h.holder}</td>
                      <td className="py-1 text-right">{formatValue(h.pct, "pct", { digits: 1 })}</td>
                      <td
                        className={cn(
                          "py-1 text-right",
                          (h.change ?? 0) > 0 && "text-[var(--diverge-pos)]",
                          (h.change ?? 0) < 0 && "text-[var(--diverge-neg)]",
                        )}
                      >
                        {formatValue(h.change, "shares", { signed: true })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-1 text-xs text-muted">
                Quarter ending {formatDate(o.institutions.summary?.period)}:{" "}
                {o.institutions.summary?.increased} holders added, {o.institutions.summary?.decreased}{" "}
                reduced; net{" "}
                {formatValue(o.institutions.summary?.net_change_shares, "shares", { signed: true })} shares.
                13F filings arrive up to 45 days after quarter end.
              </p>
            </>
          ) : (
            <p className="text-xs text-muted">{o.missing?.institutions}</p>
          )}
        </div>
        <div>
          <h3 className="mb-1 text-sm font-semibold">Short interest</h3>
          {si ? (
            <>
              <ShortChart series={si.series} />
              <p className="text-xs text-muted">
                As a share of {si.denominator}. FINRA publishes twice a month, about 8 business days after
                settlement.
              </p>
            </>
          ) : (
            <p className="text-xs text-muted">{o.missing?.short_interest}</p>
          )}
        </div>
      </div>

      <div>
        <h3 className="mb-1 text-sm font-semibold">Buybacks and share count</h3>
        <p className="text-xs text-ink-2">
          Diluted shares changed {formatValue(bb.share_change_cagr["1y"], "pct", { signed: true })} over 1
          year, {formatValue(bb.share_change_cagr["3y"], "pct", { signed: true })} a year over 3 years and{" "}
          {formatValue(bb.share_change_cagr["5y"], "pct", { signed: true })} a year over 5 years. Stock-based
          pay equals {formatValue(bb.sbc_to_mcap, "pct", { digits: 2 })} of market cap a year.
        </p>
        {bb.years.length > 0 && (
          <>
            <table className="tabular mt-2 w-full max-w-xl text-xs">
              <thead className="text-muted">
                <tr>
                  <th className="py-1 text-left font-medium">Fiscal year ended</th>
                  <th className="py-1 text-right font-medium">Spent</th>
                  <th className="py-1 text-right font-medium">Average price</th>
                </tr>
              </thead>
              <tbody>
                {bb.years.map((y: AnySection) => (
                  <tr key={y.fiscal_year_end} className="border-t border-line">
                    <td className="py-1">{formatDate(y.fiscal_year_end)}</td>
                    <td className="py-1 text-right">{formatValue(y.spent, "usd")}</td>
                    <td className="py-1 text-right">{formatValue(y.avg_price, "usd_per_share")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-1 text-xs text-ink-2">
              <MetricInlineLabel m={m.buyback_return} />: {formatValue(bb.spent, "usd")} spent, worth about{" "}
              {formatValue(bb.value_now, "usd")} at today&apos;s price (
              {formatValue(m.buyback_return.value, "pct", { signed: true })}). Estimated from each year&apos;s
              average price.
            </p>
          </>
        )}
      </div>
    </div>
  );
}

function MetricInlineLabel({ m }: { m: AnySection }) {
  return <span className="font-medium">{m.label}</span>;
}
