"use client";

import {
  AlertTriangle,
  CheckCircle2,
  CircleSlash,
  FlaskConical,
  History,
  Search,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";
import { axisStyle, baseOption, EChart } from "@/components/charts/echart";
import { TileBox, Tiles } from "@/components/report/earnings";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { Segmented } from "@/components/ui/segmented";
import { Skeleton } from "@/components/ui/skeleton";
import { useJSON } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDate, formatValue } from "@/lib/format";
import { DISCLAIMER_SHORT } from "@/lib/legal";
import type { ThemeColors } from "@/lib/theme";
import type { AnySection } from "@/lib/types";

type Kind = "backtest" | "live" | "all";
type CI = [number, number] | null;

const pct = (v: number | null | undefined, digits = 0) => formatValue(v ?? null, "pct", { digits });
const ci = (c: CI | undefined, digits = 0) => (c ? `95% CI ${pct(c[0], digits)}–${pct(c[1], digits)}` : "");
const label = (s: string) => s.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());

function Stat({ title, value, sub, tone }: { title: string; value: string; sub?: string; tone?: string }) {
  return (
    <TileBox sub={sub}>
      <div className="text-xs text-muted">{title}</div>
      <div className={cn("tabular mt-0.5 text-lg font-semibold", tone)}>{value}</div>
    </TileBox>
  );
}

function CoverageChart({ rows }: { rows: AnySection[] }) {
  const build = useCallback(
    (c: ThemeColors) => ({
      ...baseOption(c),
      grid: { left: 8, right: 16, top: 28, bottom: 24, containLabel: true },
      tooltip: {
        ...(baseOption(c).tooltip as object),
        formatter: (ps: { dataIndex: number; seriesName: string }[]) => {
          const r = rows[ps[0].dataIndex];
          return `Nominal ${pct(r.nominal)} interval<br/>Actual coverage <b>${pct(r.actual, 1)}</b> (n=${r.n})<br/>${ci(r.ci, 1)}`;
        },
      },
      xAxis: {
        type: "value",
        min: 0,
        max: 1,
        name: "Nominal coverage",
        nameLocation: "middle",
        nameGap: 22,
        nameTextStyle: { color: c.muted },
        ...axisStyle(c),
        axisLabel: { color: c.muted, formatter: (x: number) => pct(x) },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 1,
        ...axisStyle(c),
        axisLabel: { color: c.muted, formatter: (x: number) => pct(x) },
      },
      series: [
        {
          name: "Perfect calibration",
          type: "line",
          data: [
            [0, 0],
            [1, 1],
          ],
          symbol: "none",
          lineStyle: { color: c.axis, type: "dashed", width: 1 },
          tooltip: { show: false },
        },
        {
          name: "Actual coverage",
          type: "line",
          data: rows.map((r) => [r.nominal, r.actual]),
          symbolSize: 8,
          lineStyle: { color: c.accent, width: 2 },
          itemStyle: { color: c.accent, borderColor: c.surface, borderWidth: 2 },
        },
      ],
    }),
    [rows],
  );
  return (
    <EChart
      build={build}
      height={260}
      ariaLabel="Nominal versus actual coverage of the app's forecast intervals"
      table={{
        caption: "Interval coverage",
        columns: ["Nominal", "Actual", "n", "95% CI"],
        rows: rows.map((r) => [
          pct(r.nominal),
          pct(r.actual, 1),
          r.n,
          r.ci ? `${pct(r.ci[0], 1)}–${pct(r.ci[1], 1)}` : null,
        ]),
      }}
    />
  );
}

function ReliabilityChart({ bins, curve }: { bins: AnySection[]; curve: AnySection[] }) {
  const maxN = Math.max(1, ...bins.map((b) => b.n));
  const build = useCallback(
    (c: ThemeColors) => ({
      ...baseOption(c),
      grid: { left: 8, right: 16, top: 28, bottom: 24, containLabel: true },
      tooltip: { ...(baseOption(c).tooltip as object), trigger: "item" },
      xAxis: {
        type: "value",
        min: 0,
        max: 1,
        name: "Forecast probability the price is higher",
        nameLocation: "middle",
        nameGap: 22,
        nameTextStyle: { color: c.muted },
        ...axisStyle(c),
        axisLabel: { color: c.muted, formatter: (x: number) => pct(x) },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 1,
        ...axisStyle(c),
        axisLabel: { color: c.muted, formatter: (x: number) => pct(x) },
      },
      series: [
        {
          name: "Perfect calibration",
          type: "line",
          data: [
            [0, 0],
            [1, 1],
          ],
          symbol: "none",
          lineStyle: { color: c.axis, type: "dashed", width: 1 },
          tooltip: { show: false },
        },
        {
          name: "Observed frequency",
          type: "scatter",
          data: bins.map((b) => ({ value: [b.forecast, b.observed], n: b.n, ci: b.ci })),
          symbolSize: (_: unknown, p: { data: { n: number } }) => 8 + 16 * Math.sqrt(p.data.n / maxN),
          itemStyle: { color: c.accent, borderColor: c.surface, borderWidth: 2 },
          tooltip: {
            formatter: (p: { data: { value: number[]; n: number; ci: CI } }) =>
              `Forecast ${pct(p.data.value[0])}<br/>Observed <b>${pct(p.data.value[1])}</b> (n=${p.data.n})<br/>${ci(p.data.ci)}`,
          },
        },
        ...(curve.length
          ? [
              {
                name: "Recalibration map",
                type: "line",
                data: curve.map((p) => [p.raw, p.calibrated]),
                symbol: "none",
                lineStyle: { color: c.series[2], width: 2 },
                tooltip: { show: false },
              },
            ]
          : []),
      ],
    }),
    [bins, curve, maxN],
  );
  return (
    <EChart
      build={build}
      height={260}
      ariaLabel="Calibration curve: forecast probability of a higher price versus how often it happened"
      table={{
        caption: "Probability calibration",
        columns: ["Bin", "Mean forecast", "Observed", "n"],
        rows: bins.map((b) => [`${pct(b.lo)}–${pct(b.hi)}`, pct(b.forecast, 1), pct(b.observed, 1), b.n]),
      }}
    />
  );
}

function TrustChart({ t }: { t: AnySection }) {
  const rows = t.buckets as AnySection[];
  const build = useCallback(
    (c: ThemeColors) => ({
      ...baseOption(c),
      legend: { show: false },
      grid: { left: 8, right: 16, top: 16, bottom: 8, containLabel: true },
      tooltip: {
        ...(baseOption(c).tooltip as object),
        axisPointer: { type: "shadow" },
        formatter: (ps: { dataIndex: number }[]) => {
          const r = rows[ps[0].dataIndex];
          return `Trust Rating ${r.trust_lo.toFixed(0)}–${r.trust_hi.toFixed(0)} (n=${r.n})<br/>Mean 12-month return <b>${pct(r.mean_return, 1)}</b><br/>Median ${pct(r.median_return, 1)} · positive ${pct(r.positive_share)}`;
        },
      },
      xAxis: {
        type: "category",
        data: rows.map((r) => `Q${r.bucket} (${r.trust_lo.toFixed(0)}–${r.trust_hi.toFixed(0)})`),
        ...axisStyle(c),
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        ...axisStyle(c),
        axisLabel: { color: c.muted, formatter: (x: number) => pct(x) },
      },
      series: [
        {
          name: "Mean 12-month return",
          type: "bar",
          barMaxWidth: 36,
          data: rows.map((r) => ({
            value: r.mean_return,
            itemStyle: {
              color: r.mean_return >= 0 ? c.divergePos : c.divergeNeg,
              borderRadius: r.mean_return >= 0 ? [4, 4, 0, 0] : [0, 0, 4, 4],
            },
          })),
          label: {
            show: true,
            position: "top",
            color: c.ink2,
            fontSize: 10,
            formatter: (p: { dataIndex: number }) => `n=${rows[p.dataIndex].n}`,
          },
        },
      ],
    }),
    [rows],
  );
  return (
    <EChart
      build={build}
      height={240}
      ariaLabel="Average 12-month return by Trust Rating quintile"
      table={{
        caption: "Returns by Trust Rating bucket",
        columns: ["Bucket", "Trust range", "Mean return", "Median", "Positive", "n"],
        rows: rows.map((r) => [
          `Q${r.bucket}`,
          `${r.trust_lo.toFixed(0)}–${r.trust_hi.toFixed(0)}`,
          pct(r.mean_return, 1),
          pct(r.median_return, 1),
          pct(r.positive_share),
          r.n,
        ]),
      }}
    />
  );
}

function PitChart({ rows }: { rows: AnySection[] }) {
  const build = useCallback(
    (c: ThemeColors) => ({
      ...baseOption(c),
      legend: { show: false },
      grid: { left: 8, right: 16, top: 16, bottom: 24, containLabel: true },
      tooltip: {
        ...(baseOption(c).tooltip as object),
        axisPointer: { type: "shadow" },
        formatter: (ps: { dataIndex: number }[]) => {
          const r = rows[ps[0].dataIndex];
          return `Realized price between the forecast's ${pct(r.lo)} and ${pct(r.hi)} quantiles<br/><b>${pct(r.share, 1)}</b> of outcomes (10% if calibrated)`;
        },
      },
      xAxis: {
        type: "category",
        data: rows.map((r) => pct(r.lo)),
        name: "Where the realized price fell in the forecast distribution",
        nameLocation: "middle",
        nameGap: 22,
        nameTextStyle: { color: c.muted },
        ...axisStyle(c),
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        ...axisStyle(c),
        axisLabel: { color: c.muted, formatter: (x: number) => pct(x) },
      },
      series: [
        {
          type: "bar",
          barCategoryGap: "8%",
          data: rows.map((r) => ({
            value: r.share,
            itemStyle: { color: c.series[0], borderRadius: [3, 3, 0, 0] },
          })),
          markLine: {
            silent: true,
            symbol: "none",
            lineStyle: { color: c.axis, type: "dashed" },
            label: { formatter: "calibrated", position: "insideEndTop", color: c.muted, fontSize: 10 },
            data: [{ yAxis: 0.1 }],
          },
        },
      ],
    }),
    [rows],
  );
  return (
    <EChart
      build={build}
      height={220}
      ariaLabel="Histogram of where realized prices fell in the forecast distributions"
    />
  );
}

const GROUPS = [
  { value: "by_profile", label: "Profile" },
  { value: "by_vol", label: "Volatility" },
  { value: "by_size", label: "Size" },
  { value: "by_year", label: "Year" },
] as const;

function GroupTable({ r }: { r: AnySection }) {
  const [g, setG] = useState<(typeof GROUPS)[number]["value"]>("by_profile");
  const rows = (r[g] ?? []) as AnySection[];
  return (
    <div>
      <Segmented label="Group results by" value={g} options={[...GROUPS]} onChange={setG} />
      <div className="mt-2 overflow-x-auto">
        <table className="w-full min-w-[34rem] text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs text-muted">
              <th className="py-1.5 pr-2 font-medium">Group</th>
              <th className="py-1.5 pr-2 text-right font-medium">Estimates</th>
              <th className="py-1.5 pr-2 text-right font-medium">P10–P90 coverage</th>
              <th className="py-1.5 pr-2 text-right font-medium">Median error</th>
              <th className="py-1.5 pr-2 text-right font-medium">Direction right</th>
              <th className="py-1.5 text-right font-medium">Brier skill</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((x) => (
              <tr key={x.group} className="border-b border-line last:border-b-0">
                <td className="py-1.5 pr-2">{label(x.group)}</td>
                <td className="tabular py-1.5 pr-2 text-right">{x.n}</td>
                <td className="tabular py-1.5 pr-2 text-right" title={ci(x.coverage_ci)}>
                  {pct(x.coverage)}
                </td>
                <td className="tabular py-1.5 pr-2 text-right">{pct(x.median_abs_err, 1)}</td>
                <td className="tabular py-1.5 pr-2 text-right">{pct(x.direction_hit_rate)}</td>
                <td className="tabular py-1.5 text-right">{formatValue(x.brier_skill ?? null, "ratio")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Changes({ cal }: { cal: AnySection }) {
  const rows = (cal.changes ?? []) as AnySection[];
  if (!rows.length)
    return (
      <p className="text-sm text-ink-2">
        No recalibration has been fitted yet. One is considered once at least{" "}
        {cal.min_outcomes?.recalibration} estimates have been graded.
      </p>
    );
  return (
    <ol className="space-y-2">
      {rows.map((c) => (
        <li key={c.id} className="rounded-lg border border-line px-3 py-2 text-sm">
          <div className="flex flex-wrap items-center gap-2">
            {c.applied ? (
              <Badge tone="accent">
                <CheckCircle2 className="size-3" /> Applied
              </Badge>
            ) : (
              <Badge>
                <CircleSlash className="size-3" /> Not applied
              </Badge>
            )}
            <span className="font-medium">{formatDate(c.fitted_on)}</span>
            <span className="text-xs text-muted">
              {c.n} graded estimates to {formatDate(c.data_cutoff)} · engine {c.engine_version} · config{" "}
              {c.config_hash}
            </span>
          </div>
          <p className="mt-1 text-ink-2">{c.reason}.</p>
        </li>
      ))}
    </ol>
  );
}

function TickerLookup() {
  const [q, setQ] = useState("");
  const [t, setT] = useState<string | null>(null);
  const { data, error, loading } = useJSON<AnySection>(t ? `/track-record/${encodeURIComponent(t)}` : null);
  const rows = (data?.snapshots ?? []) as AnySection[];
  return (
    <div>
      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (q.trim()) setT(q.trim().toUpperCase());
        }}
      >
        <label htmlFor="tr-ticker" className="sr-only">
          Ticker
        </label>
        <input
          id="tr-ticker"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Ticker, e.g. ZZTEC"
          className="h-8 w-44 rounded-md border border-line bg-surface px-2 text-sm"
        />
        <Button type="submit">
          <Search className="size-3.5" /> Show estimates
        </Button>
      </form>
      {loading && <Skeleton className="mt-3 h-24 w-full" />}
      {error && <p className="mt-2 text-sm text-critical-ink">{error}</p>}
      {data && !loading && (
        <div className="mt-3 overflow-x-auto">
          {rows.length === 0 ? (
            <p className="text-sm text-ink-2">No stored estimates for {data.ticker} yet.</p>
          ) : (
            <table className="w-full min-w-[40rem] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs text-muted">
                  <th className="py-1.5 pr-2 font-medium">Date</th>
                  <th className="py-1.5 pr-2 font-medium">Kind</th>
                  <th className="py-1.5 pr-2 text-right font-medium">Price</th>
                  <th className="py-1.5 pr-2 text-right font-medium">P10 · P50 · P90</th>
                  <th className="py-1.5 pr-2 text-right font-medium">12 months later</th>
                  <th className="py-1.5 text-right font-medium">In range</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={`${r.as_of}-${r.is_backtest}`} className="border-b border-line last:border-b-0">
                    <td className="py-1.5 pr-2">{formatDate(r.as_of)}</td>
                    <td className="py-1.5 pr-2 text-xs text-muted">{r.is_backtest ? "backtest" : "live"}</td>
                    <td className="tabular py-1.5 pr-2 text-right">
                      {formatValue(r.price, "usd_per_share")}
                    </td>
                    <td className="tabular py-1.5 pr-2 text-right text-ink-2">
                      {formatValue(r.p10, "usd_per_share")} ·{" "}
                      <b className="text-ink">{formatValue(r.p50, "usd_per_share")}</b> ·{" "}
                      {formatValue(r.p90, "usd_per_share")}
                    </td>
                    <td className="tabular py-1.5 pr-2 text-right">
                      {r.outcome ? (
                        formatValue(r.outcome.realized_price, "usd_per_share")
                      ) : (
                        <span className="text-xs text-muted">due {formatDate(r.due)}</span>
                      )}
                    </td>
                    <td className="py-1.5 text-right">
                      {r.outcome &&
                        (r.outcome.in_band ? (
                          <CheckCircle2
                            className="ml-auto size-4 text-good-ink"
                            aria-label="inside the range"
                          />
                        ) : (
                          <XCircle
                            className="ml-auto size-4 text-critical-ink"
                            aria-label="outside the range"
                          />
                        ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}

export function TrackRecordPage() {
  const [kind, setKind] = useState<Kind>("backtest");
  const [profile, setProfile] = useState<string>("");
  const path = `/track-record?kind=${kind}${profile ? `&profile=${encodeURIComponent(profile)}` : ""}`;
  const { data, error, loading } = useJSON<AnySection>(path);
  const r = data?.results;
  const s = r?.summary ?? {};
  const counts = data?.counts;
  const live = counts?.live;

  return (
    <div className="mx-auto max-w-6xl px-4 py-6">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-0 flex-1">
          <h1 className="text-2xl font-semibold tracking-tight">Track record</h1>
          <p className="mt-1 text-sm text-ink-2">
            Every report the app produces is stored and graded{" "}
            {data ? Math.round(data.horizon_days / 30.4) : 12} months later against what the stock actually
            did. This page shows how those estimates held up, including where they failed.
          </p>
        </div>
        <Segmented
          label="Which estimates"
          value={kind}
          options={[
            { value: "backtest", label: "Backtest" },
            { value: "live", label: "Live" },
            { value: "all", label: "All" },
          ]}
          onChange={(k) => setKind(k)}
        />
        {!!data?.profiles?.length && (
          <select
            aria-label="Filter by profile"
            value={profile}
            onChange={(e) => setProfile(e.target.value)}
            className="h-8 rounded-md border border-line bg-surface px-2 text-sm"
          >
            <option value="">All profiles</option>
            {data.profiles.map((p: string) => (
              <option key={p} value={p}>
                {label(p)}
              </option>
            ))}
          </select>
        )}
      </div>

      {data && (
        <div className="mt-4 rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-sm">
          <div className="flex items-center gap-2 font-semibold text-warning-ink">
            {kind === "live" ? <History className="size-4" /> : <FlaskConical className="size-4" />}
            {kind === "backtest" ? "BACKTEST" : kind === "live" ? "LIVE" : "BACKTEST + LIVE"}
            {data.synthetic && <Badge tone="synthetic">Synthetic data</Badge>}
          </div>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-ink-2">
            {data.caveats.map((c: string) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      )}

      {live && (
        <p className="mt-3 text-sm text-ink-2">
          <span className="font-medium text-ink">Live record:</span>{" "}
          {live.snapshots
            ? `${live.snapshots} estimates stored since ${formatDate(live.first)}; ${live.scored} graded so far.`
            : "no live estimates stored yet; they are recorded as reports are viewed."}{" "}
          {live.snapshots > 0 && live.scored === 0 && live.days_until_first_due > 0
            ? `The first grades are due ${formatDate(live.first_due)}, in ${live.days_until_first_due} days. Until then, the backtest is the only evidence.`
            : ""}
        </p>
      )}

      {error && !data && (
        <p className="mt-6 text-sm text-critical-ink">The track record could not be loaded: {error}</p>
      )}
      {!data && loading && <Skeleton className="mt-6 h-96 w-full" />}

      {data && s.n === 0 && (
        <Card className="mt-4">
          <CardBody className="pt-4">
            <p className="text-sm text-ink-2">
              No graded {kind === "live" ? "live" : ""} estimates yet.{" "}
              {kind !== "live" && (
                <>
                  Run the walk-forward backtest with{" "}
                  <code className="rounded bg-surface-2 px-1">make backtest</code> to replay the engine on
                  past data.
                </>
              )}
            </p>
          </CardBody>
        </Card>
      )}

      {data && s.n > 0 && (
        <div className={cn("mt-4 space-y-4", loading && "opacity-60")}>
          <Tiles>
            <Stat
              title="Price inside the 80% range"
              value={pct(s.coverage)}
              sub={`target 80% · ${ci(s.coverage_ci)}`}
              tone={Math.abs(s.coverage - 0.8) <= 0.05 ? "text-good-ink" : "text-warning-ink"}
            />
            <Stat
              title="Median error of P50"
              value={pct(s.median_abs_err, 1)}
              sub={`mean ${pct(s.mean_abs_err, 1)} · |realized ÷ P50 − 1|`}
            />
            <Stat
              title="Direction right"
              value={pct(s.direction_hit_rate)}
              sub={`${ci(s.direction_hit_ci)} · stocks rose ${pct(s.realized_up_share)} of the time`}
            />
            <Stat
              title="Brier skill (prob. higher)"
              value={formatValue(s.brier_skill ?? null, "ratio")}
              sub={`Brier ${formatValue(s.brier ?? null, "ratio", { digits: 3 })} vs ${formatValue(s.brier_reference ?? null, "ratio", { digits: 3 })} for the base rate; above 0 beats it`}
              tone={(s.brier_skill ?? 0) > 0 ? "text-good-ink" : "text-warning-ink"}
            />
          </Tiles>
          <p className="text-xs text-muted">
            {s.n} graded estimates for {s.tickers} companies, made {formatDate(s.first)} to{" "}
            {formatDate(s.last)}. Below 10th percentile {pct(s.below_p10)}, above 90th {pct(s.above_p90)} (10%
            each if calibrated).
          </p>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Are the ranges honest?</CardTitle>
              </CardHeader>
              <CardBody>
                <p className="mb-2 text-xs text-muted">
                  For each nominal interval (the 80% one is P10–P90), the share of realized prices that landed
                  inside. On the dashed line the ranges mean what they say; below it they are too narrow.
                </p>
                <CoverageChart rows={r.interval_coverage} />
              </CardBody>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Are the probabilities honest?</CardTitle>
              </CardHeader>
              <CardBody>
                <p className="mb-2 text-xs text-muted">
                  Forecast chance of a higher price after 12 months against how often it happened; dot size
                  shows the number of estimates.
                  {data.calibration.curve.length
                    ? " The line is the recalibration map applied to live reports."
                    : ""}
                </p>
                <ReliabilityChart bins={r.reliability} curve={data.calibration.curve} />
              </CardBody>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Does a higher Trust Rating mean better returns?</CardTitle>
              </CardHeader>
              <CardBody>
                {r.trust.buckets.length ? (
                  <>
                    <p className="mb-2 text-xs text-muted">
                      Average 12-month price return by Trust Rating quintile at the time of the estimate. Rank
                      correlation {formatValue(r.trust.spearman ?? null, "ratio")}; top minus bottom{" "}
                      {pct(r.trust.top_minus_bottom, 1)}. Shown as measured, whatever it says.
                    </p>
                    <TrustChart t={r.trust} />
                  </>
                ) : (
                  <p className="text-sm text-ink-2">{r.trust.note}</p>
                )}
              </CardBody>
            </Card>
            <Card>
              <CardHeader>
                <CardTitle>Where outcomes fell in the forecast</CardTitle>
              </CardHeader>
              <CardBody>
                <p className="mb-2 text-xs text-muted">
                  Each bar is a tenth of the forecast distribution. Flat bars at 10% mean calibrated; tall
                  outer bars mean ranges too narrow; a tilt means the median was biased.
                </p>
                <PitChart rows={r.pit} />
              </CardBody>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Results by group</CardTitle>
            </CardHeader>
            <CardBody>
              <GroupTable r={r} />
            </CardBody>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Accuracy of each valuation method</CardTitle>
            </CardHeader>
            <CardBody>
              <p className="mb-2 text-xs text-muted">
                Each method&apos;s own 12-month figure against the realized price. Once enough estimates are
                graded, these errors adjust the method weights in the blend (see Methodology).
              </p>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[28rem] text-sm">
                  <thead>
                    <tr className="border-b border-line text-left text-xs text-muted">
                      <th className="py-1.5 pr-2 font-medium">Method</th>
                      <th className="py-1.5 pr-2 text-right font-medium">Estimates</th>
                      <th className="py-1.5 pr-2 text-right font-medium">Median error (log)</th>
                      <th className="py-1.5 text-right font-medium">Direction right</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(r.methods as AnySection[]).map((mth) => (
                      <tr key={mth.method} className="border-b border-line last:border-b-0">
                        <td className="py-1.5 pr-2">{mth.label}</td>
                        <td className="tabular py-1.5 pr-2 text-right">{mth.n}</td>
                        <td className="tabular py-1.5 pr-2 text-right">
                          {formatValue(mth.median_abs_log_err, "ratio", { digits: 3 })}
                        </td>
                        <td className="tabular py-1.5 text-right">{pct(mth.direction_hit_rate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </CardBody>
          </Card>
        </div>
      )}

      {data && (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Recalibration log</CardTitle>
            </CardHeader>
            <CardBody>
              <p className="mb-2 text-xs text-muted">
                Every fitted correction, applied or not, with the out-of-sample evidence. Live reports use the
                latest applied one dated on or before their date; backtests always use the raw model.
              </p>
              <Changes cal={data.calibration} />
            </CardBody>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Past estimates for one stock</CardTitle>
            </CardHeader>
            <CardBody>
              <TickerLookup />
            </CardBody>
          </Card>
        </div>
      )}

      {data && (
        <p className="mt-6 flex flex-wrap items-center gap-1 text-xs text-muted">
          <AlertTriangle className="size-3.5" aria-hidden /> {DISCLAIMER_SHORT} Past accuracy does not
          guarantee future accuracy. Engine {data.engine_version} · config {data.config_hash}.{" "}
          <Link href="/methodology" className="underline underline-offset-2">
            How grading works
          </Link>
        </p>
      )}
    </div>
  );
}
