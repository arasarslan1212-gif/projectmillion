"use client";

import { X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo } from "react";
import { axisStyle, baseOption, EChart } from "@/components/charts/echart";
import { TickerSearch } from "@/components/ticker-search";
import { Badge } from "@/components/ui/badge";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { MetricTip } from "@/components/ui/metric";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { useHealth, useJSON } from "@/lib/api";
import { cn } from "@/lib/cn";
import { direction, formatDate, formatMetric, formatValue, gradeColor } from "@/lib/format";
import { DISCLAIMER_SHORT } from "@/lib/legal";
import type { ThemeColors } from "@/lib/theme";
import type { AnySection, Metric } from "@/lib/types";

type Range = "6m" | "1y" | "3y" | "5y";
const RANGES: { value: Range; label: string }[] = [
  { value: "6m", label: "6M" },
  { value: "1y", label: "1Y" },
  { value: "3y", label: "3Y" },
  { value: "5y", label: "5Y" },
];

function PriceChart({ chart, tickers }: { chart: AnySection; tickers: string[] }) {
  const build = useCallback(
    (c: ThemeColors) => {
      const series = tickers
        .filter((t) => chart.series[t])
        .map((t, i) => ({
          name: t,
          type: "line",
          showSymbol: false,
          data: chart.series[t],
          lineStyle: { width: 2, color: c.series[i % c.series.length] },
          itemStyle: { color: c.series[i % c.series.length] },
          endLabel: { show: true, formatter: t, color: c.ink2, fontSize: 11 },
        }));
      if (chart.benchmark)
        series.push({
          name: chart.benchmark.label,
          type: "line",
          showSymbol: false,
          data: chart.benchmark.values,
          lineStyle: { width: 1.5, color: c.axis, type: "dashed" } as never,
          itemStyle: { color: c.axis },
          endLabel: { show: false, formatter: "", color: c.muted, fontSize: 11 },
        });
      return {
        ...baseOption(c),
        grid: { left: 8, right: 56, top: 32, bottom: 8, containLabel: true },
        tooltip: {
          ...(baseOption(c).tooltip as object),
          valueFormatter: (v: number) => (v == null ? "—" : v.toFixed(1)),
        },
        xAxis: {
          type: "category",
          data: chart.dates,
          boundaryGap: false,
          ...axisStyle(c),
          splitLine: { show: false },
          axisLabel: { color: c.muted, formatter: (d: string) => formatDate(d) },
        },
        yAxis: {
          type: "value",
          scale: true,
          ...axisStyle(c),
        },
        series,
      };
    },
    [chart, tickers],
  );
  return (
    <EChart
      build={build}
      height={300}
      ariaLabel={`Price performance indexed to 100: ${tickers.join(", ")}`}
      table={{
        caption: "Indexed price performance",
        columns: ["Date", ...tickers],
        rows: chart.dates
          .map((d: string, i: number) => [
            formatDate(d),
            ...tickers.map((t) => chart.series[t]?.[i]?.toFixed(1) ?? null),
          ])
          .filter((_: unknown, i: number) => i % 5 === 0 || i === chart.dates.length - 1),
      }}
    />
  );
}

function PillarRadar({ rows }: { rows: AnySection[] }) {
  const pillars = useMemo(() => (rows[0]?.pillars ?? []) as AnySection[], [rows]);
  const build = useCallback(
    (c: ThemeColors) => ({
      ...baseOption(c),
      tooltip: {
        trigger: "item",
        backgroundColor: c.surface,
        borderColor: c.grid,
        textStyle: { color: c.ink },
      },
      legend: { ...(baseOption(c).legend as object), data: rows.map((r) => r.ticker) },
      radar: {
        radius: "62%",
        center: ["50%", "56%"],
        indicator: pillars.map((p) => ({ name: p.label, max: 100 })),
        axisName: { color: c.ink2, fontSize: 10 },
        splitLine: { lineStyle: { color: c.grid } },
        splitArea: { show: false },
        axisLine: { lineStyle: { color: c.grid } },
      },
      series: [
        {
          type: "radar",
          data: rows.map((r, i) => ({
            name: r.ticker,
            value: pillars.map((p) => r.pillars.find((x: AnySection) => x.id === p.id)?.score ?? 0),
            lineStyle: { width: 2, color: c.series[i % c.series.length] },
            itemStyle: { color: c.series[i % c.series.length] },
            areaStyle: { opacity: 0.06, color: c.series[i % c.series.length] },
            symbolSize: 4,
          })),
        },
      ],
    }),
    [rows, pillars],
  );
  return <EChart build={build} height={320} ariaLabel="Trust Rating pillar scores for each company" />;
}

function Cell({ children, className }: { children: React.ReactNode; className?: string }) {
  return <td className={cn("tabular px-3 py-2 text-right align-top", className)}>{children}</td>;
}

function RowHead({ children }: { children: React.ReactNode }) {
  return (
    <th
      scope="row"
      className="sticky left-0 z-10 bg-surface px-3 py-2 text-left text-xs font-medium text-ink-2"
    >
      {children}
    </th>
  );
}

function Group({ label, span }: { label: string; span: number }) {
  return (
    <tr>
      <th
        colSpan={span}
        scope="colgroup"
        className="bg-surface-2 px-3 py-1.5 text-left text-[11px] font-semibold uppercase tracking-wide text-muted"
      >
        {label}
      </th>
    </tr>
  );
}

function CompareTable({ rows }: { rows: AnySection[] }) {
  const span = rows.length + 1;
  // rows where no company has a value (e.g. bank-only metrics among non-banks) are left out
  const pillars = ((rows[0]?.pillars ?? []) as AnySection[]).filter((p) =>
    rows.some((r) => r.pillars.find((x: AnySection) => x.id === p.id)?.score != null),
  );
  const metricIdx = Array.from({ length: rows[0]?.metrics?.length ?? 0 }, (_, i) => i).filter((i) =>
    rows.some((r) => r.metrics[i]?.value != null),
  );
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[36rem] border-collapse text-sm">
        <caption className="sr-only">Side-by-side comparison of scores, targets and key metrics</caption>
        <thead>
          <tr className="border-b border-line">
            <th className="sticky left-0 z-10 bg-surface px-3 py-2" />
            {rows.map((r) => {
              const dir = direction(r.change_pct?.value);
              return (
                <th key={r.ticker} scope="col" className="px-3 py-2 text-right align-bottom font-normal">
                  <Link
                    href={`/stock/${r.ticker}`}
                    className="text-base font-semibold text-ink hover:underline"
                  >
                    {r.ticker}
                  </Link>
                  <div className="truncate text-xs text-muted">{r.name}</div>
                  <div className="text-xs text-muted">{r.profile}</div>
                  <div className="tabular mt-0.5 text-sm">
                    {formatMetric(r.price)}{" "}
                    <span
                      className={cn(
                        "text-xs",
                        dir === "up" && "text-good-ink",
                        dir === "down" && "text-critical-ink",
                      )}
                    >
                      {formatMetric(r.change_pct, { signed: true, digits: 2 })}
                    </span>
                  </div>
                  {r.synthetic && (
                    <Badge tone="synthetic" className="mt-1">
                      Synthetic
                    </Badge>
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          <Group label="The app's view (model estimates)" span={span} />
          <tr className="border-b border-line">
            <RowHead>Trust Rating</RowHead>
            {rows.map((r) => (
              <Cell key={r.ticker}>
                {r.trust?.score == null ? (
                  <span className="text-muted">Insufficient data</span>
                ) : (
                  <>
                    {formatValue(r.trust.score, "score")}
                    <span className="text-muted">/100</span>{" "}
                    <span className={cn("font-semibold", gradeColor(r.trust.grade))}>{r.trust.grade}</span>
                  </>
                )}
              </Cell>
            ))}
          </tr>
          <tr className="border-b border-line">
            <RowHead>12-month target (P50)</RowHead>
            {rows.map((r) => (
              <Cell key={r.ticker}>
                {r.target?.p50 == null ? (
                  <span className="text-muted">Not available</span>
                ) : (
                  <>
                    <div className="font-medium">{formatValue(r.target.p50, "usd_per_share")}</div>
                    <div className="text-xs text-muted">
                      {formatValue(r.target.p10, "usd_per_share")}–
                      {formatValue(r.target.p90, "usd_per_share")}
                    </div>
                  </>
                )}
              </Cell>
            ))}
          </tr>
          <tr className="border-b border-line">
            <RowHead>Implied return to P50</RowHead>
            {rows.map((r) => (
              <Cell key={r.ticker}>
                {formatValue(r.target?.implied_return ?? null, "pct", { signed: true })}
              </Cell>
            ))}
          </tr>
          <tr className="border-b border-line">
            <RowHead>Confidence</RowHead>
            {rows.map((r) => (
              <Cell key={r.ticker}>
                {r.confidence?.score == null
                  ? "—"
                  : `${formatValue(r.confidence.score, "score")} · ${r.confidence.level}`}
              </Cell>
            ))}
          </tr>
          <tr className="border-b border-line">
            <RowHead>Analyst consensus (all · trusted)</RowHead>
            {rows.map((r) => (
              <Cell key={r.ticker}>
                {r.consensus
                  ? `${formatValue(r.consensus.all ?? null, "usd_per_share")} · ${formatValue(r.consensus.trusted ?? null, "usd_per_share")}`
                  : "—"}
              </Cell>
            ))}
          </tr>
          <Group label="Trust Rating pillars (0–100, vs. sector)" span={span} />
          {pillars.map((p) => (
            <tr key={p.id} className="border-b border-line">
              <RowHead>{p.label}</RowHead>
              {rows.map((r) => {
                const s = r.pillars.find((x: AnySection) => x.id === p.id)?.score;
                return (
                  <Cell key={r.ticker}>
                    {s == null ? <span className="text-muted">—</span> : formatValue(s, "score")}
                  </Cell>
                );
              })}
            </tr>
          ))}
          <Group label="Key metrics" span={span} />
          {metricIdx.map((i) => {
            const first = rows.find((r) => r.metrics[i]?.label)?.metrics[i] as Metric | undefined;
            return (
              <tr key={i} className="border-b border-line last:border-b-0">
                <RowHead>
                  {first ? (
                    <MetricTip m={first}>
                      <button
                        type="button"
                        className="text-left underline decoration-dotted underline-offset-2"
                      >
                        {first.label}
                      </button>
                    </MetricTip>
                  ) : (
                    rows[0].metrics[i].id
                  )}
                </RowHead>
                {rows.map((r) => {
                  const m = r.metrics[i] as Metric;
                  return (
                    <Cell key={r.ticker}>
                      {m?.value == null ? (
                        <span className="text-xs text-muted" title={m?.reason ?? undefined}>
                          n/a
                        </span>
                      ) : (
                        formatMetric(m)
                      )}
                    </Cell>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function ComparePage() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const health = useHealth();
  const tickers = useMemo(
    () =>
      (params.get("t") ?? "")
        .split(",")
        .map((t) => t.trim().toUpperCase())
        .filter(Boolean)
        .slice(0, 4),
    [params],
  );
  const range = (RANGES.find((r) => r.value === params.get("range"))?.value ?? "1y") as Range;
  const setUrl = (ts: string[], rg: Range = range) =>
    router.replace(
      `${pathname}?t=${ts.map(encodeURIComponent).join(",")}${rg !== "1y" ? `&range=${rg}` : ""}`,
      {
        scroll: false,
      },
    );
  const add = (t: string) => {
    const u = t.toUpperCase();
    if (!tickers.includes(u) && tickers.length < 4) setUrl([...tickers, u]);
  };
  const { data, error, loading } = useJSON<AnySection>(
    tickers.length >= 2
      ? `/compare?tickers=${tickers.map(encodeURIComponent).join(",")}&range=${range}`
      : null,
  );
  const examples = health?.synthetic ? ["ZZTEC", "ZZGRO", "ZZSML"] : ["AAPL", "MSFT", "GOOGL"];

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <h1 className="text-2xl font-semibold tracking-tight">Compare</h1>
      <p className="mt-1 text-sm text-ink-2">
        Two to four stocks side by side. Every number is the one each stock&apos;s own report shows, with the
        same definitions and sources.
      </p>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        {tickers.map((t) => (
          <span
            key={t}
            className="inline-flex items-center gap-1 rounded-md border border-line bg-surface px-2 py-1 text-sm font-medium"
          >
            {t}
            <button
              type="button"
              onClick={() => setUrl(tickers.filter((x) => x !== t))}
              aria-label={`Remove ${t}`}
              className="rounded p-0.5 text-muted hover:bg-surface-2 hover:text-ink"
            >
              <X className="size-3.5" />
            </button>
          </span>
        ))}
        {tickers.length < 4 && (
          <div className="w-full max-w-xs">
            <TickerSearch compact onPick={add} />
          </div>
        )}
        {tickers.length >= 2 && (
          <div className="ml-auto">
            <Segmented
              label="Price chart range"
              value={range}
              options={RANGES}
              onChange={(r) => setUrl(tickers, r)}
            />
          </div>
        )}
      </div>

      {tickers.length < 2 && (
        <Card className="mt-6">
          <CardBody className="pt-4 text-sm text-ink-2">
            Add {tickers.length === 0 ? "two to four stocks" : "at least one more stock"} to compare.{" "}
            <button
              type="button"
              className="text-accent-ink underline underline-offset-2"
              onClick={() => setUrl(examples)}
            >
              Try {examples.join(", ")}
            </button>
          </CardBody>
        </Card>
      )}
      {error && !data && (
        <p className="mt-6 text-sm text-critical-ink">The comparison could not be loaded: {error}</p>
      )}
      {tickers.length >= 2 && !data && loading && <Skeleton className="mt-6 h-[36rem] w-full" />}
      {data && tickers.length >= 2 && (
        <div className={cn("mt-4 space-y-4", loading && "opacity-60")}>
          {data.errors?.length > 0 && (
            <p className="text-sm text-warning-ink">
              {data.errors.map((e: AnySection) => e.error).join("; ")}.
            </p>
          )}
          {data.rows.length > 0 && (
            <Card>
              <CardBody className="px-0 pt-2 sm:px-0">
                <CompareTable rows={data.rows} />
              </CardBody>
            </Card>
          )}
          {data.chart.dates.length > 1 && (
            <Card>
              <CardHeader>
                <CardTitle>Price performance, indexed to 100</CardTitle>
              </CardHeader>
              <CardBody>
                <p className="mb-2 text-xs text-muted">
                  Total-return closes (dividends reinvested) on dates all {data.rows.length} stocks traded,
                  rebased to 100 at {formatDate(data.chart.dates[0])}
                  {data.chart.benchmark ? `; dashed: ${data.chart.benchmark.label}` : ""}.
                </p>
                <PriceChart chart={data.chart} tickers={data.tickers} />
              </CardBody>
            </Card>
          )}
          {data.rows.length > 1 && (
            <Card>
              <CardHeader>
                <CardTitle>Trust Rating pillars</CardTitle>
              </CardHeader>
              <CardBody>
                <PillarRadar rows={data.rows} />
              </CardBody>
            </Card>
          )}
          <p className="text-xs text-muted">{DISCLAIMER_SHORT}</p>
        </div>
      )}
    </div>
  );
}
