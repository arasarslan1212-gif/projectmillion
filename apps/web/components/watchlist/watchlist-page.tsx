"use client";

import { AlertTriangle, Columns3, Trash2 } from "lucide-react";
import Link from "next/link";
import { useCallback } from "react";
import { baseOption, EChart } from "@/components/charts/echart";
import { TileBox, Tiles } from "@/components/report/earnings";
import { TickerSearch } from "@/components/ticker-search";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useJSON } from "@/lib/api";
import { cn } from "@/lib/cn";
import { direction, formatMetric, formatValue, gradeColor } from "@/lib/format";
import { DISCLAIMER_SHORT } from "@/lib/legal";
import { toggleWatch, useWatchlist } from "@/lib/recent";
import type { ThemeColors } from "@/lib/theme";
import type { AnySection } from "@/lib/types";

function Correlation({ c }: { c: { tickers: string[]; matrix: number[][] } }) {
  const n = c.tickers.length;
  const build = useCallback(
    (col: ThemeColors) => ({
      ...baseOption(col),
      legend: { show: false },
      grid: { left: 8, right: 8, top: 8, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "item",
        backgroundColor: col.surface,
        borderColor: col.grid,
        textStyle: { color: col.ink, fontSize: 12 },
        formatter: (p: { value: number[] }) =>
          `${c.tickers[p.value[0]]} vs ${c.tickers[p.value[1]]}: <b>${p.value[2].toFixed(2)}</b>`,
      },
      xAxis: {
        type: "category",
        data: c.tickers,
        axisLabel: { color: col.ink2 },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      yAxis: {
        type: "category",
        data: c.tickers,
        inverse: true,
        axisLabel: { color: col.ink2 },
        axisLine: { show: false },
        axisTick: { show: false },
      },
      visualMap: {
        show: false,
        min: -1,
        max: 1,
        inRange: { color: [col.divergeNeg, col.divergeMid, col.divergePos] },
      },
      series: [
        {
          type: "heatmap",
          data: c.matrix.flatMap((row, i) => row.map((v, j) => [j, i, v])),
          label: {
            show: n <= 8,
            color: col.ink,
            fontSize: 10,
            formatter: (p: { value: number[] }) => p.value[2].toFixed(2),
          },
          itemStyle: { borderColor: col.surface, borderWidth: 2 },
        },
      ],
    }),
    [c, n],
  );
  return (
    <EChart
      build={build}
      height={Math.max(180, 36 * n + 40)}
      ariaLabel="Correlation of daily returns between watched stocks"
      table={{
        caption: "Correlation matrix",
        columns: ["", ...c.tickers],
        rows: c.matrix.map((row, i) => [c.tickers[i], ...row.map((v) => v.toFixed(2))]),
      }}
    />
  );
}

export function WatchlistPage() {
  const [list] = useWatchlist();
  const { data, error, loading } = useJSON<AnySection>(
    list.length ? `/watchlist/summary?tickers=${list.map(encodeURIComponent).join(",")}` : null,
  );
  const a = data?.aggregate;
  const holdings = (data?.holdings ?? []) as AnySection[];
  const shown = holdings.filter((h) => list.includes(String(h.ticker)));

  return (
    <div className="mx-auto max-w-7xl px-4 py-6">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-semibold tracking-tight">Watchlist</h1>
          <p className="mt-1 text-sm text-ink-2">
            The stocks you watch, with the app&apos;s scores and an equal-weight view of the group&apos;s
            combined risk. Stored in this browser.
          </p>
        </div>
        <div className="w-full max-w-xs">
          <TickerSearch
            compact
            onPick={(t) => !list.includes(t.toUpperCase()) && toggleWatch(t.toUpperCase())}
          />
        </div>
        {list.length >= 2 && (
          <Link
            href={`/compare?t=${list.slice(0, 4).join(",")}`}
            className="inline-flex h-8 items-center gap-1.5 rounded-md border border-line bg-surface px-2.5 text-xs font-medium text-ink-2 hover:bg-surface-2"
          >
            <Columns3 className="size-3.5" /> Compare {list.length > 4 ? "first 4" : "all"}
          </Link>
        )}
      </div>

      {list.length === 0 && (
        <Card className="mt-6">
          <CardBody className="pt-4 text-sm text-ink-2">
            Your watchlist is empty. Add stocks with the search box above or the Watch button on any report.
          </CardBody>
        </Card>
      )}
      {error && !data && (
        <p className="mt-6 text-sm text-critical-ink">The watchlist could not be loaded: {error}</p>
      )}
      {list.length > 0 && !data && loading && <Skeleton className="mt-6 h-96 w-full" />}

      {data && a && list.length > 0 && (
        <div className={cn("mt-4 space-y-4", loading && "opacity-60")}>
          <Tiles>
            <TileBox sub={a.trust_min != null ? `lowest ${formatValue(a.trust_min, "score")}` : undefined}>
              <div className="text-xs text-muted">Average Trust Rating</div>
              <div className="tabular mt-0.5 text-lg font-semibold">{formatValue(a.trust_mean, "score")}</div>
            </TileBox>
            <TileBox sub="average of the app's 12-month P50s; model estimates">
              <div className="text-xs text-muted">Average implied return</div>
              <div className="tabular mt-0.5 text-lg font-semibold">
                {formatValue(a.implied_return_mean, "pct", { signed: true })}
              </div>
            </TileBox>
            <TileBox
              sub={
                a.vol != null
                  ? `vs ${formatValue(a.vol_avg_holding, "pct", { digits: 0 })} for the average stock; ${a.window_days} trading days`
                  : "needs two stocks with a year of prices"
              }
            >
              <div className="text-xs text-muted">Equal-weight volatility</div>
              <div className="tabular mt-0.5 text-lg font-semibold">
                {formatValue(a.vol, "pct", { digits: 0 })}
              </div>
            </TileBox>
            <TileBox sub={`average beta ${formatValue(a.beta_mean, "ratio")}`}>
              <div className="text-xs text-muted">Average correlation</div>
              <div className="tabular mt-0.5 text-lg font-semibold">
                {formatValue(a.avg_correlation, "ratio")}
              </div>
            </TileBox>
          </Tiles>

          <Card>
            <CardBody className="px-0 pt-2 sm:px-0">
              <div className="overflow-x-auto">
                <table className="w-full min-w-[52rem] text-sm">
                  <caption className="sr-only">Watched stocks with the app&apos;s scores and risk</caption>
                  <thead>
                    <tr className="border-b border-line text-left text-xs text-muted">
                      <th className="px-3 py-2 font-medium">Stock</th>
                      <th className="px-3 py-2 text-right font-medium">Price</th>
                      <th className="px-3 py-2 text-right font-medium">Trust Rating</th>
                      <th className="px-3 py-2 text-right font-medium">Target P50</th>
                      <th className="px-3 py-2 text-right font-medium">Confidence</th>
                      <th className="px-3 py-2 text-right font-medium">Volatility</th>
                      <th className="px-3 py-2 text-right font-medium">Beta</th>
                      <th className="px-3 py-2 text-right font-medium">Red flags</th>
                      <th className="px-3 py-2">
                        <span className="sr-only">Remove</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {shown.map((h) => {
                      const dir = direction(h.change_pct?.value);
                      return (
                        <tr key={h.ticker} className="border-b border-line last:border-b-0">
                          <td className="px-3 py-2">
                            <Link href={`/stock/${h.ticker}`} className="font-semibold hover:underline">
                              {h.ticker}
                            </Link>
                            <div className="max-w-[16rem] truncate text-xs text-muted">
                              {h.name} · {h.sector}
                            </div>
                          </td>
                          <td className="tabular px-3 py-2 text-right">
                            {formatMetric(h.price)}
                            <div
                              className={cn(
                                "text-xs",
                                dir === "up" && "text-good-ink",
                                dir === "down" && "text-critical-ink",
                              )}
                            >
                              {formatMetric(h.change_pct, { signed: true, digits: 2 })}
                            </div>
                          </td>
                          <td className="tabular px-3 py-2 text-right">
                            {h.trust?.score == null ? (
                              "—"
                            ) : (
                              <>
                                {formatValue(h.trust.score, "score")}{" "}
                                <span className={cn("font-semibold", gradeColor(h.trust.grade))}>
                                  {h.trust.grade}
                                </span>
                              </>
                            )}
                          </td>
                          <td className="tabular px-3 py-2 text-right">
                            {formatValue(h.target?.p50 ?? null, "usd_per_share")}
                            <div className="text-xs text-muted">
                              {formatValue(h.target?.implied_return ?? null, "pct", { signed: true })}
                            </div>
                          </td>
                          <td className="tabular px-3 py-2 text-right">
                            {h.confidence?.score == null
                              ? "—"
                              : `${formatValue(h.confidence.score, "score")} · ${h.confidence.level}`}
                          </td>
                          <td className="tabular px-3 py-2 text-right">
                            {formatValue(h.volatility, "pct", { digits: 0 })}
                          </td>
                          <td className="tabular px-3 py-2 text-right">{formatValue(h.beta, "ratio")}</td>
                          <td className="tabular px-3 py-2 text-right">
                            {h.red_flags ? (
                              <span className={cn(h.severe_flags && "text-critical-ink")}>
                                {h.red_flags}
                                {h.severe_flags ? ` (${h.severe_flags} high)` : ""}
                              </span>
                            ) : (
                              <span className="text-muted">0</span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-right">
                            <Button
                              variant="ghost"
                              onClick={() => toggleWatch(String(h.ticker))}
                              aria-label={`Remove ${h.ticker}`}
                            >
                              <Trash2 className="size-3.5" />
                            </Button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
              {data.errors?.length > 0 && (
                <p className="flex items-center gap-1.5 px-4 pt-2 text-xs text-warning-ink sm:px-5">
                  <AlertTriangle className="size-3.5" />{" "}
                  {data.errors.map((e: AnySection) => e.error).join("; ")}
                </p>
              )}
            </CardBody>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Sector mix</CardTitle>
              </CardHeader>
              <CardBody>
                <ul className="space-y-2 text-sm">
                  {a.sectors.map((s: AnySection) => (
                    <li key={s.sector}>
                      <div className="flex justify-between gap-2">
                        <span>{s.sector}</span>
                        <span className="tabular text-ink-2">
                          {s.n} · {formatValue(s.share, "pct", { digits: 0 })}
                        </span>
                      </div>
                      <div className="mt-1 h-1.5 rounded-full bg-surface-2">
                        <div
                          className="h-1.5 rounded-full bg-accent"
                          style={{ width: `${Math.round(s.share * 100)}%` }}
                        />
                      </div>
                    </li>
                  ))}
                </ul>
                {a.sectors[0]?.share > 0.5 && a.n >= 3 && (
                  <p className="mt-3 text-xs text-warning-ink">
                    More than half of the watchlist is in one sector, so these stocks may tend to move
                    together.
                  </p>
                )}
                <p className="mt-3 text-xs text-muted">
                  Diversification ratio {formatValue(a.diversification_ratio, "ratio")}: the average
                  stock&apos;s volatility divided by the equal-weight group&apos;s. Higher means holding them
                  together smooths more of the swings.
                </p>
              </CardBody>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>How the stocks move together</CardTitle>
              </CardHeader>
              <CardBody>
                {a.correlation ? (
                  <>
                    <p className="mb-2 text-xs text-muted">
                      Correlation of daily returns over the last {a.window_days} trading days (−1 opposite, 0
                      unrelated, +1 in lockstep).
                    </p>
                    <Correlation c={a.correlation} />
                  </>
                ) : (
                  <p className="text-sm text-ink-2">
                    Needs at least two stocks with a year of shared price history.
                  </p>
                )}
              </CardBody>
            </Card>
          </div>
          <p className="text-xs text-muted">
            {holdings.some((h) => h.synthetic) && (
              <Badge tone="synthetic" className="mr-2">
                Synthetic data
              </Badge>
            )}
            Equal weights are an illustration, not a suggested allocation. {DISCLAIMER_SHORT}
          </p>
        </div>
      )}
    </div>
  );
}
