"use client";

import Link from "next/link";
import { AlertTriangle } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { axisStyle, baseOption, EChart } from "@/components/charts/echart";
import { ScoreBar } from "@/components/report/trust";
import { MetricTip } from "@/components/ui/metric";
import { Segmented } from "@/components/ui/segmented";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getJSON, useDebounced } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDate, formatValue } from "@/lib/format";
import { DISCLAIMER_SHORT } from "@/lib/legal";
import type { ThemeColors } from "@/lib/theme";
import { withAlpha } from "@/lib/theme";
import type { AnySection, Metric } from "@/lib/types";

function Tile({ m, sub, hero }: { m: Metric; sub?: React.ReactNode; hero?: boolean }) {
  return (
    <div className="rounded-lg border border-line p-3">
      <MetricTip m={m}>
        <button
          type="button"
          className="text-left text-xs text-muted underline decoration-dotted decoration-muted/50 underline-offset-2"
        >
          {m.label}
        </button>
      </MetricTip>
      <div className={cn("mt-0.5 font-semibold", hero ? "text-3xl" : "text-xl")}>
        {formatValue(m.value, m.unit, { signed: m.unit === "pct" })}
      </div>
      {sub && <div className="mt-0.5 text-xs text-ink-2">{sub}</div>}
    </div>
  );
}

/** One horizontal scale with the 80% range, P50, today's price, intrinsic value and the market band. */
function RangeFigure({
  v,
  consensus,
}: {
  v: AnySection;
  consensus?: { all?: number | null; trusted?: number | null };
}) {
  const t = v.target;
  const pts = [
    t.p10,
    t.p90,
    v.price,
    v.intrinsic,
    v.market_band.p10,
    v.market_band.p90,
    consensus?.trusted,
    consensus?.all,
  ].filter((x): x is number => typeof x === "number" && Number.isFinite(x) && x > 0);
  const lo = Math.min(...pts) * 0.95;
  const hi = Math.max(...pts) * 1.05;
  const pos = (x: number) => `${((x - lo) / (hi - lo)) * 100}%`;
  const marks: { x: number | null | undefined; label: string; cls: string }[] = [
    { x: v.price, label: "Today", cls: "bg-ink" },
    { x: t.p50, label: "P50", cls: "bg-accent" },
    { x: v.intrinsic, label: "Intrinsic value", cls: "bg-[var(--s7)]" },
    { x: consensus?.trusted, label: "Trusted consensus", cls: "bg-[var(--s3)]" },
    { x: consensus?.all, label: "All-analyst consensus", cls: "bg-[var(--s2)]" },
  ];
  return (
    <div
      className="mt-2"
      role="img"
      aria-label={`App 12-month range ${formatValue(t.p10, "usd_per_share")} to ${formatValue(t.p90, "usd_per_share")}, median ${formatValue(t.p50, "usd_per_share")}, today ${formatValue(v.price, "usd_per_share")}`}
    >
      <div className="relative h-14">
        <div
          className="absolute top-6 h-2 rounded-full bg-surface-2"
          style={{
            left: pos(v.market_band.p10),
            width: `calc(${pos(v.market_band.p90)} - ${pos(v.market_band.p10)})`,
          }}
          title="Market-implied band (volatility only)"
        />
        <div
          className="absolute top-5 h-4 rounded-full bg-accent-wash ring-1 ring-accent/40"
          style={{ left: pos(t.p10), width: `calc(${pos(t.p90)} - ${pos(t.p10)})` }}
          title="App P10–P90 range"
        />
        {marks.map((mk) =>
          typeof mk.x === "number" && mk.x > 0 ? (
            <div
              key={mk.label}
              className="absolute top-3 flex -translate-x-1/2 flex-col items-center"
              style={{ left: pos(mk.x) }}
            >
              <div className={cn("h-8 w-0.5 rounded", mk.cls)} />
            </div>
          ) : null,
        )}
      </div>
      <div className="relative h-4 text-[11px] text-muted">
        {[
          { x: t.p10, label: "P10" },
          { x: t.p90, label: "P90" },
        ].map((e) => {
          const f = (e.x - lo) / (hi - lo);
          return (
            <span
              key={e.label}
              className={cn(
                "absolute whitespace-nowrap",
                f < 0.12 ? "" : f > 0.88 ? "-translate-x-full" : "-translate-x-1/2",
              )}
              style={{ left: pos(e.x) }}
            >
              {e.label} {formatValue(e.x, "usd_per_share")}
            </span>
          );
        })}
      </div>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-2">
        {marks.map((mk) =>
          typeof mk.x === "number" && mk.x > 0 ? (
            <li key={mk.label} className="flex items-center gap-1.5">
              <span className={cn("inline-block h-3 w-0.5 rounded", mk.cls)} aria-hidden />
              {mk.label} {formatValue(mk.x, "usd_per_share")}
            </li>
          ) : null,
        )}
        <li className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-4 rounded bg-accent-wash ring-1 ring-accent/40" aria-hidden />{" "}
          App 80% range (P10–P90)
        </li>
        <li className="flex items-center gap-1.5">
          <span className="inline-block h-2 w-4 rounded bg-surface-2" aria-hidden /> Market-implied band
          (volatility only)
        </li>
      </ul>
    </div>
  );
}

function MethodsTable({ v, withAnalysts }: { v: AnySection; withAnalysts: boolean }) {
  const blendRows: AnySection[] = withAnalysts === v.include_analysts ? v.blend : v.blend_alternative.weights;
  const byId = new Map(blendRows.map((b) => [b.id, b]));
  return (
    <div className="overflow-x-auto">
      <table className="tabular w-full min-w-[640px] text-xs">
        <caption className="sr-only">Valuation methods and blend weights</caption>
        <thead className="text-muted">
          <tr>
            <th className="py-1 text-left font-medium">Method</th>
            <th className="whitespace-nowrap py-1 pl-2 text-right font-medium">Value / share</th>
            <th className="whitespace-nowrap py-1 pl-2 text-right font-medium">12-mo target</th>
            <th className="whitespace-nowrap py-1 pl-2 text-right font-medium">Weight</th>
            <th className="py-1 pl-3 text-left font-medium">Notes</th>
          </tr>
        </thead>
        <tbody>
          {v.methods.map((m: AnySection) => {
            const b = byId.get(m.id);
            return (
              <tr key={m.id} className={cn("border-t border-line align-top", !b && "text-muted")}>
                <td className="min-w-[9rem] py-1.5 pr-2 font-medium">{m.label}</td>
                <td className="py-1.5 text-right">{m.value ? formatValue(m.value, "usd_per_share") : "—"}</td>
                <td className="py-1.5 text-right">{b ? formatValue(b.target_12m, "usd_per_share") : "—"}</td>
                <td className="py-1.5 text-right">
                  {b ? formatValue(b.weight, "pct", { digits: 0 }) : "0%"}
                </td>
                <td className="py-1.5 pl-3 text-ink-2">
                  {m.reason ? `Not used: ${m.reason}.` : (m.notes ?? []).join(" ")}
                  {b && b.applicability < 1 ? ` Applicability ${Math.round(b.applicability * 100)}%.` : ""}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Histogram({ v }: { v: AnySection }) {
  const mc = v.dcf.monte_carlo;
  const edges: number[] = mc.histogram.edges;
  const priceInRange = v.price >= edges[0] && v.price <= edges[edges.length - 1];
  const shareAbove: number | null = mc.share_above_price ?? null;
  const build = useCallback(
    (c: ThemeColors) => {
      const mids = mc.histogram.counts.map((_: number, i: number) => (edges[i] + edges[i + 1]) / 2);
      const idx = (x: number) =>
        mids.reduce(
          (best: number, m: number, i: number) => (Math.abs(m - x) < Math.abs(mids[best] - x) ? i : best),
          0,
        );
      const line = (x: number, name: string, color: string) => ({
        xAxis: idx(x),
        name,
        lineStyle: { color, width: 2, type: "solid" },
        label: { formatter: name, color: c.ink2, fontSize: 10 },
      });
      return {
        ...baseOption(c),
        legend: { show: false },
        tooltip: {
          ...(baseOption(c).tooltip as object),
          formatter: (p: { dataIndex: number; value: number }[]) =>
            `<b>${p[0].value}</b> draws near ${formatValue(mids[p[0].dataIndex], "usd_per_share")}`,
        },
        xAxis: {
          type: "category",
          data: mids.map((m: number) => formatValue(m, "usd_per_share", { digits: 0 })),
          ...axisStyle(c),
          splitLine: { show: false },
        },
        yAxis: { type: "value", ...axisStyle(c) },
        series: [
          {
            type: "bar",
            data: mc.histogram.counts,
            barCategoryGap: "8%",
            itemStyle: { color: withAlpha(c.series[0], 0.75), borderRadius: [2, 2, 0, 0] },
            markLine: {
              symbol: "none",
              data: [
                line(mc.percentiles.p10, "P10", c.series[0]),
                line(mc.percentiles.p50, "P50", c.series[0]),
                line(mc.percentiles.p90, "P90", c.series[0]),
                ...(priceInRange ? [line(v.price, "Price", c.ink)] : []),
              ],
            },
          },
        ],
      };
    },
    [mc, edges, v.price, priceInRange],
  );
  return (
    <div>
      <p className="text-xs text-ink-2">
        {mc.draws.toLocaleString()} DCF draws (seed {mc.seed}) varying near-term growth (σ{" "}
        {formatValue(mc.inputs.sigma_growth, "pct")}), target margin (σ{" "}
        {formatValue(mc.inputs.sigma_margin, "pct")}, correlation {mc.inputs.growth_margin_correlation} with
        growth), WACC (σ {formatValue(mc.inputs.sigma_wacc, "pct")}) and terminal growth (σ{" "}
        {formatValue(mc.inputs.sigma_terminal_growth, "pct")}). Intrinsic value per share: P10{" "}
        {formatValue(mc.percentiles.p10, "usd_per_share")}, P50{" "}
        {formatValue(mc.percentiles.p50, "usd_per_share")}, P90{" "}
        {formatValue(mc.percentiles.p90, "usd_per_share")}.{" "}
        {shareAbove !== null && (
          <>
            About {formatValue(shareAbove, "prob", { digits: 0 })} of draws are above today&apos;s price (
            {formatValue(v.price, "usd_per_share")})
            {priceInRange ? "" : ", which lies outside the range shown"}.
          </>
        )}
      </p>
      <EChart
        height={240}
        ariaLabel="Histogram of Monte Carlo DCF values per share"
        build={build}
        table={{
          caption: "Monte Carlo percentiles",
          columns: ["Percentile", "Value per share"],
          rows: Object.entries(mc.percentiles).map(([k, x]) => [
            k.toUpperCase(),
            formatValue(x as number, "usd_per_share"),
          ]),
        }}
      />
    </div>
  );
}

function Heatmap({ v }: { v: AnySection }) {
  const s = v.dcf.sensitivity;
  const build = useCallback(
    (c: ThemeColors) => {
      const data: [number, number, number | null][] = [];
      s.values.forEach((row: (number | null)[], i: number) =>
        row.forEach((val, j) => data.push([j, i, val === null ? null : val / v.price - 1])),
      );
      return {
        backgroundColor: "transparent",
        textStyle: { fontFamily: "system-ui, sans-serif" },
        tooltip: {
          backgroundColor: c.surface,
          borderColor: c.grid,
          textStyle: { color: c.ink, fontSize: 12 },
          formatter: (p: { data: [number, number, number | null] }) => {
            const val = s.values[p.data[1]][p.data[0]];
            return val === null
              ? "n/a"
              : `<b>${formatValue(val, "usd_per_share")}</b> (${formatValue(p.data[2], "pct", { signed: true })} vs. price)<br/>WACC ${formatValue(s.waccs[p.data[1]], "pct")} · terminal g ${formatValue(s.growths[p.data[0]], "pct")}`;
          },
        },
        grid: { left: 8, right: 8, top: 8, bottom: 40, containLabel: true },
        xAxis: {
          type: "category",
          data: s.growths.map((g: number) => formatValue(g, "pct")),
          name: "Terminal growth",
          nameLocation: "middle",
          nameGap: 24,
          nameTextStyle: { color: c.muted },
          axisLabel: { color: c.muted },
          axisTick: { show: false },
          axisLine: { lineStyle: { color: c.axis } },
        },
        yAxis: {
          type: "category",
          data: s.waccs.map((w: number) => formatValue(w, "pct")),
          name: "WACC",
          nameTextStyle: { color: c.muted },
          axisLabel: { color: c.muted },
          axisTick: { show: false },
          axisLine: { lineStyle: { color: c.axis } },
        },
        visualMap: {
          show: false,
          min: -0.5,
          max: 0.5,
          inRange: { color: [c.critical, c.dark ? "#383835" : "#f0efec", c.series[0]] },
        },
        series: [
          {
            type: "heatmap",
            data,
            label: {
              show: true,
              formatter: (p: { data: [number, number, number | null] }) =>
                s.values[p.data[1]][p.data[0]] === null
                  ? ""
                  : formatValue(s.values[p.data[1]][p.data[0]], "usd_per_share", { digits: 0 }),
              color: c.ink,
              fontSize: 10,
            },
            itemStyle: { borderColor: c.surface, borderWidth: 2 },
          },
        ],
      };
    },
    [s, v.price],
  );
  return (
    <div>
      <p className="text-xs text-ink-2">
        DCF value per share for combinations of WACC and terminal growth. Blue cells are above today&apos;s
        price, red below, gray near it.
      </p>
      <EChart
        height={300}
        ariaLabel="DCF sensitivity heatmap of WACC against terminal growth"
        build={build}
        table={{
          caption: "DCF sensitivity",
          columns: ["WACC", ...s.growths.map((g: number) => `g ${formatValue(g, "pct")}`)],
          rows: s.values.map((row: (number | null)[], i: number) => [
            formatValue(s.waccs[i], "pct"),
            ...row.map((x) => formatValue(x, "usd_per_share")),
          ]),
        }}
      />
    </div>
  );
}

function Tornado({ v }: { v: AnySection }) {
  const rows: AnySection[] = v.dcf.tornado;
  const base = rows[0]?.base ?? 0;
  const build = useCallback(
    (c: ThemeColors) => ({
      ...baseOption(c),
      legend: { ...(baseOption(c).legend as object), data: ["Driver lower", "Driver higher"] },
      tooltip: {
        ...(baseOption(c).tooltip as object),
        trigger: "axis",
        axisPointer: { type: "shadow" },
        valueFormatter: (x: number) => formatValue(base + x, "usd_per_share"),
      },
      grid: { left: 8, right: 24, top: 28, bottom: 8, containLabel: true },
      xAxis: {
        type: "value",
        ...axisStyle(c),
        axisLabel: {
          color: c.muted,
          formatter: (x: number) => formatValue(base + x, "usd_per_share", { digits: 0 }),
        },
      },
      yAxis: {
        type: "category",
        data: [...rows].reverse().map((r) => `${r.driver} ±${(r.delta * 100).toFixed(1)}pp`),
        ...axisStyle(c),
        splitLine: { show: false },
      },
      series: [
        {
          name: "Driver lower",
          type: "bar",
          stack: "t",
          barMaxWidth: 18,
          data: [...rows].reverse().map((r) => r.low - base),
          itemStyle: { color: c.series[1], borderRadius: 3 },
        },
        {
          name: "Driver higher",
          type: "bar",
          stack: "u",
          barMaxWidth: 18,
          data: [...rows].reverse().map((r) => r.high - base),
          itemStyle: { color: c.series[0], borderRadius: 3 },
          barGap: "-100%",
        },
      ],
    }),
    [rows, base],
  );
  return (
    <div>
      <p className="text-xs text-ink-2">
        How much the DCF value per share (base {formatValue(base, "usd_per_share")}) moves when each driver
        changes by the stated amount, largest effect first.
      </p>
      <EChart
        height={260}
        ariaLabel="Tornado chart of DCF drivers"
        build={build}
        table={{
          caption: "DCF drivers",
          columns: ["Driver", "Lower", "Higher"],
          rows: rows.map((r) => [
            r.driver,
            formatValue(r.low, "usd_per_share"),
            formatValue(r.high, "usd_per_share"),
          ]),
        }}
      />
    </div>
  );
}

const MULTIPLE_LABELS: Record<string, string> = {
  pe: "P/E",
  ev_ebitda: "EV/EBITDA",
  ev_sales: "EV/Sales",
  p_fcf: "P/FCF",
  p_b: "P/B",
  p_ffo: "P/FFO",
};

function MultiplesHistory({ v, profile }: { v: AnySection; profile: string }) {
  const mh = v.multiples_history;
  const allowed = Object.keys(mh.series).filter((k) =>
    k === "p_ffo"
      ? profile === "reit"
      : k === "p_b"
        ? ["bank", "insurer", "financial_other", "reit"].includes(profile)
        : true,
  );
  const [key, setKey] = useState(allowed[0] ?? "pe");
  const band = mh.bands[key];
  const build = useCallback(
    (c: ThemeColors) => ({
      ...baseOption(c),
      legend: { show: false },
      tooltip: { ...(baseOption(c).tooltip as object), valueFormatter: (x: number) => formatValue(x, "x") },
      xAxis: {
        type: "category",
        data: mh.dates,
        ...axisStyle(c),
        splitLine: { show: false },
        boundaryGap: false,
      },
      yAxis: {
        type: "value",
        scale: true,
        ...axisStyle(c),
        axisLabel: { color: c.muted, formatter: (x: number) => formatValue(x, "x", { digits: 0 }) },
      },
      series: [
        {
          name: MULTIPLE_LABELS[key],
          type: "line",
          data: mh.series[key],
          symbol: "none",
          connectNulls: false,
          lineStyle: { width: 2, color: c.series[0] },
          markArea: band
            ? {
                silent: true,
                itemStyle: { color: withAlpha(c.series[0], 0.08) },
                data: [[{ yAxis: band.mean - band.std, name: "±1σ" }, { yAxis: band.mean + band.std }]],
              }
            : undefined,
          markLine: band
            ? {
                symbol: "none",
                silent: true,
                lineStyle: { color: c.muted, type: "solid", width: 1 },
                label: { color: c.muted, formatter: "5y mean" },
                data: [{ yAxis: band.mean }],
              }
            : undefined,
        },
      ],
    }),
    [mh, key, band],
  );
  if (!allowed.length)
    return <p className="text-xs text-muted">Not enough point-in-time history for multiples.</p>;
  return (
    <div>
      <div className="flex flex-wrap items-center gap-2">
        <Segmented
          label="Multiple"
          value={key}
          onChange={setKey}
          options={allowed.map((k) => ({ value: k, label: MULTIPLE_LABELS[k] }))}
        />
        {band && (
          <span className="text-xs text-muted">
            5-year mean {formatValue(band.mean, "x")} ± {formatValue(band.std, "x")} (n={band.n}, winsorized)
          </span>
        )}
      </div>
      <EChart
        height={240}
        ariaLabel={`${MULTIPLE_LABELS[key]} history with one-standard-deviation band`}
        build={build}
      />
      <p className="text-xs text-muted">
        Each point uses trailing fundamentals and the closing price on that quarter&apos;s filing date
        (point-in-time).
      </p>
    </div>
  );
}

function WhatIf({ ticker, v }: { ticker: string; v: AnySection }) {
  const base = v.dcf.inputs;
  const [inp, setInp] = useState({
    growth1: base.growth1,
    margin_target: base.margin_target,
    wacc: base.wacc,
    terminal_growth: base.terminal_growth,
    capex_pct: base.capex_pct,
  });
  const dq = useDebounced(inp, 250);
  const [res, setRes] = useState<AnySection | null>(null);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    const ctrl = new AbortController();
    getJSON<AnySection>(`/valuation/${encodeURIComponent(ticker)}/dcf`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(dq),
      signal: ctrl.signal,
    })
      .then((r) => {
        setRes(r);
        setErr(null);
      })
      .catch((e) => !ctrl.signal.aborted && setErr(e.message));
    return () => ctrl.abort();
  }, [dq, ticker]);
  const sliders: { key: keyof typeof inp; label: string; min: number; max: number; step: number }[] = [
    { key: "growth1", label: "Near-term revenue growth", min: -0.2, max: 0.6, step: 0.005 },
    { key: "margin_target", label: "Target operating margin", min: -0.2, max: 0.6, step: 0.005 },
    { key: "wacc", label: "WACC", min: 0.04, max: 0.16, step: 0.0025 },
    { key: "terminal_growth", label: "Terminal growth", min: 0.0, max: 0.03, step: 0.0025 },
    { key: "capex_pct", label: "Capex % of revenue", min: 0, max: 0.5, step: 0.005 },
  ];
  return (
    <div className="grid gap-4 md:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div className="space-y-3">
        {sliders.map((s) => (
          <label key={s.key} className="block">
            <div className="flex justify-between text-xs">
              <span className="text-ink-2">{s.label}</span>
              <span className="tabular font-medium">
                {formatValue(inp[s.key], "pct")}{" "}
                <span className="text-muted">(base {formatValue(base[s.key], "pct")})</span>
              </span>
            </div>
            <input
              type="range"
              min={s.min}
              max={s.max}
              step={s.step}
              value={inp[s.key]}
              onChange={(e) => setInp({ ...inp, [s.key]: Number(e.target.value) })}
              className="mt-1 w-full accent-[var(--accent)]"
              aria-label={s.label}
            />
          </label>
        ))}
        <button
          type="button"
          className="text-xs text-accent-ink underline"
          onClick={() =>
            setInp({
              growth1: base.growth1,
              margin_target: base.margin_target,
              wacc: base.wacc,
              terminal_growth: base.terminal_growth,
              capex_pct: base.capex_pct,
            })
          }
        >
          Reset to the app&apos;s assumptions
        </button>
      </div>
      <div className="rounded-lg border border-line p-3" aria-live="polite">
        <div className="text-xs text-muted">DCF value per share with your assumptions</div>
        <div className="text-3xl font-semibold">
          {res ? formatValue(res.per_share, "usd_per_share") : "…"}
        </div>
        {res && (
          <div className="mt-1 space-y-0.5 text-xs text-ink-2">
            <div>
              {formatValue(res.upside, "pct", { signed: true })} vs. price{" "}
              {formatValue(res.price, "usd_per_share")} · app base DCF{" "}
              {formatValue(res.base_per_share, "usd_per_share")}
            </div>
            <div>
              Terminal value is {formatValue(res.terminal_share, "pct", { digits: 0 })} of enterprise value.
            </div>
            {res.notes?.map((n: string) => (
              <div key={n} className="text-warning-ink">
                {n}
              </div>
            ))}
            <div className="text-muted">{res.disclaimer}</div>
          </div>
        )}
        {err && <p className="mt-1 text-xs text-critical-ink">{err}</p>}
      </div>
    </div>
  );
}

export function ValuationSection({
  v,
  ticker,
  profile,
  consensus,
}: {
  v: AnySection;
  ticker: string;
  profile: string;
  consensus?: { all?: number | null; trusted?: number | null };
}) {
  const [withAnalysts, setWithAnalysts] = useState<boolean>(v.include_analysts);
  const t = withAnalysts === v.include_analysts ? v.target : v.blend_alternative.target;
  const m = v.metrics;
  const conf = v.confidence;
  const hasAnalyst = v.methods.some((x: AnySection) => x.id === "analyst_consensus" && x.value);
  const roeBasis = v.reverse_dcf?.basis === "return on equity";
  const scenarios = useMemo(() => Object.entries(v.scenarios ?? {}) as [string, AnySection][], [v.scenarios]);
  return (
    <div className="space-y-5">
      {v.sanity.length > 0 && (
        <ul className="space-y-1">
          {v.sanity.map((s: AnySection) => (
            <li
              key={s.id}
              className="flex items-start gap-2 rounded-md border border-warning/40 bg-warning/10 px-3 py-1.5 text-xs text-ink"
            >
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-warning-ink" aria-hidden />
              {s.message}
            </li>
          ))}
        </ul>
      )}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile
          m={{ ...m.p50, value: t.p50 }}
          hero
          sub={
            <>
              80% range {formatValue(t.p10, "usd_per_share")}–{formatValue(t.p90, "usd_per_share")}
            </>
          }
        />
        <Tile
          m={{ ...m.implied_return, value: t.implied_return }}
          sub={
            <>
              Mean of the distribution {formatValue(t.expected_return, "pct", { signed: true })}
              {t.expected_return - t.implied_return > 0.25
                ? " (pulled up by a few large-gain scenarios)"
                : ""}
            </>
          }
        />
        <Tile
          m={{ ...m.prob_up, value: t.prob_up }}
          sub={
            <>≥20% drawdown along the way: {formatValue(v.target.prob_drawdown_20, "prob", { digits: 0 })}</>
          }
        />
        <Tile
          m={m.confidence}
          sub={
            <>
              {conf.level}
              {conf.capped ? " (capped for this profile)" : ""}
            </>
          }
        />
      </div>
      <RangeFigure v={{ ...v, target: t }} consensus={consensus} />
      <p className="text-xs text-ink-2">
        Long-term intrinsic value estimate:{" "}
        <span className="font-medium">{formatValue(v.intrinsic, "usd_per_share")}</span>. The 12-month median
        assumes the price earns its cost of equity ({formatValue(v.wacc.cost_of_equity, "pct")}) net of
        dividends and closes {Math.round(v.sigma.convergence * 100)}% of the gap to intrinsic value within a
        year. {DISCLAIMER_SHORT}
      </p>

      <div>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <h3 className="text-sm font-semibold">Methods and blend</h3>
          <Segmented
            label="Analyst consensus in the blend"
            value={withAnalysts ? "with" : "without"}
            onChange={(x) => setWithAnalysts(x === "with")}
            options={[
              { value: "with", label: "With analyst consensus" },
              { value: "without", label: "Without" },
            ]}
          />
          {!hasAnalyst && (
            <span className="text-xs text-muted">
              No analyst targets available, so both versions are identical.
            </span>
          )}
        </div>
        <MethodsTable v={v} withAnalysts={withAnalysts} />
        <p className="mt-1 text-xs text-muted">
          Weights = profile weight × applicability × measured accuracy ({v.accuracy_source}). Uncertainty:
          market σ {formatValue(v.sigma.market, "pct")}, method dispersion{" "}
          {formatValue(v.sigma.method_dispersion, "pct")}
          {v.dcf ? `, DCF Monte Carlo σ ${formatValue(v.sigma.monte_carlo, "pct")}` : ""}, widened ×
          {v.sigma.widening.toFixed(2)} for confidence
          {v.target.calibration && v.sigma.calibration_scale !== 1
            ? `, scaled ×${v.sigma.calibration_scale.toFixed(2)} by the track-record recalibration`
            : ""}{" "}
          → total σ {formatValue(v.sigma.total, "pct")}.
        </p>
        {v.target.calibration && (
          <p className="mt-1 text-xs text-muted">
            Recalibrated from {v.target.calibration.n} graded past estimates (fitted{" "}
            {formatDate(v.target.calibration.fitted_on)}
            {v.target.calibration.prob_map_applied
              ? "; the probability of a higher price is recalibrated too"
              : ""}
            ). The median (P50) is never moved.{" "}
            <Link href="/track-record" className="underline underline-offset-2">
              Track record
            </Link>
          </p>
        )}
      </div>

      <div>
        <h3 className="mb-2 text-sm font-semibold">Why confidence is {conf.level.toLowerCase()}</h3>
        <ul className="grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2">
          {conf.breakdown.map((b: AnySection) => (
            <li key={b.id} className="flex min-w-0 items-center gap-3 text-xs">
              <span className="w-32 shrink-0 text-ink-2">{b.label}</span>
              <ScoreBar score={b.score} label={b.label} />
              <span className="min-w-0 truncate text-muted" title={b.note}>
                {b.note}
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-1 text-xs text-muted">{conf.explain}</p>
      </div>

      <Tabs defaultValue={v.dcf ? "dcf" : "reverse"}>
        <TabsList>
          {v.dcf && <TabsTrigger value="dcf">DCF</TabsTrigger>}
          {v.dcf && <TabsTrigger value="mc">Monte Carlo</TabsTrigger>}
          {v.dcf && <TabsTrigger value="sens">Sensitivity</TabsTrigger>}
          {v.dcf && <TabsTrigger value="tornado">Drivers</TabsTrigger>}
          {scenarios.length > 0 && <TabsTrigger value="scen">Scenarios</TabsTrigger>}
          <TabsTrigger value="reverse">{roeBasis ? "Implied ROE" : "Reverse DCF"}</TabsTrigger>
          <TabsTrigger value="hist">Multiples history</TabsTrigger>
          {v.dcf && <TabsTrigger value="whatif">What-if</TabsTrigger>}
        </TabsList>
        {v.dcf && (
          <TabsContent value="dcf">
            <div className="grid gap-4 lg:grid-cols-2">
              <div>
                <h4 className="mb-1 text-xs font-semibold text-ink-2">Assumptions</h4>
                <table className="tabular w-full text-xs">
                  <tbody>
                    {(
                      [
                        ["growth1", "Near-term revenue growth", "pct"],
                        ["margin0", "Current operating margin", "pct"],
                        ["margin_target", "Target operating margin", "pct"],
                        ["wacc", "WACC", "pct"],
                        ["terminal_growth", "Terminal growth", "pct"],
                        ["tax0", "Tax rate (now → 21% long run)", "pct"],
                        ["capex_pct", "Capex % of revenue", "pct"],
                        ["dna_pct", "D&A % of revenue", "pct"],
                        ["nwc_pct", "Net working capital % of revenue", "pct"],
                      ] as const
                    ).map(([k, lbl, u]) => (
                      <tr key={k} className="border-t border-line align-top">
                        <td className="py-1 pr-2 text-ink-2">{lbl}</td>
                        <td className="py-1 text-right font-medium">{formatValue(v.dcf.inputs[k], u)}</td>
                        <td className="py-1 pl-3 text-[11px] text-muted">{v.dcf.input_sources[k] ?? ""}</td>
                      </tr>
                    ))}
                    <tr className="border-t border-line">
                      <td className="py-1 pr-2 text-ink-2">Equity bridge</td>
                      <td className="py-1 text-right font-medium" colSpan={2}>
                        EV {formatValue(v.dcf.enterprise_value, "usd")} − debt{" "}
                        {formatValue(v.dcf.inputs.debt, "usd")} + cash {formatValue(v.dcf.inputs.cash, "usd")}{" "}
                        − minorities {formatValue(v.dcf.inputs.minority, "usd")} − pension{" "}
                        {formatValue(v.dcf.inputs.pension_deficit, "usd")} ={" "}
                        {formatValue(v.dcf.equity_value, "usd")} ÷{" "}
                        {formatValue(v.dcf.inputs.shares, "shares")} shares ={" "}
                        {formatValue(v.dcf.per_share, "usd_per_share")}
                      </td>
                    </tr>
                  </tbody>
                </table>
                <p className="mt-1 text-[11px] text-muted">
                  Terminal value = {formatValue(v.dcf.terminal_share, "pct", { digits: 0 })} of enterprise
                  value. Stock-based compensation is treated as a real expense.
                </p>
                {v.dcf.notes.map((n: string) => (
                  <p key={n} className="text-[11px] text-warning-ink">
                    {n}
                  </p>
                ))}
              </div>
              <div className="overflow-x-auto">
                <h4 className="mb-1 text-xs font-semibold text-ink-2">
                  Projection (free cash flow to the firm)
                </h4>
                <table className="tabular w-full min-w-[480px] text-right text-[11px]">
                  <thead className="text-muted">
                    <tr>
                      <th className="py-1 text-left font-medium">Year</th>
                      <th className="py-1 font-medium">Growth</th>
                      <th className="py-1 font-medium">Revenue</th>
                      <th className="py-1 font-medium">Margin</th>
                      <th className="py-1 font-medium">NOPAT</th>
                      <th className="py-1 font-medium">Reinvest</th>
                      <th className="py-1 font-medium">FCFF</th>
                      <th className="py-1 font-medium">PV</th>
                    </tr>
                  </thead>
                  <tbody>
                    {v.dcf.table.map((r: AnySection) => (
                      <tr key={r.year} className="border-t border-line">
                        <td className="py-0.5 text-left">{r.year}</td>
                        <td>{formatValue(r.growth, "pct")}</td>
                        <td>{formatValue(r.revenue, "usd")}</td>
                        <td>{formatValue(r.margin, "pct")}</td>
                        <td>{formatValue(r.nopat, "usd")}</td>
                        <td>{formatValue(r.reinvestment, "usd")}</td>
                        <td>{formatValue(r.fcff, "usd")}</td>
                        <td>{formatValue(r.pv, "usd")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </TabsContent>
        )}
        {v.dcf && (
          <TabsContent value="mc">
            <Histogram v={v} />
          </TabsContent>
        )}
        {v.dcf && (
          <TabsContent value="sens">
            <Heatmap v={v} />
          </TabsContent>
        )}
        {v.dcf && (
          <TabsContent value="tornado">
            <Tornado v={v} />
          </TabsContent>
        )}
        {scenarios.length > 0 && (
          <TabsContent value="scen">
            <div className="grid gap-3 sm:grid-cols-3">
              {scenarios.map(([name, s]) => (
                <div key={name} className="rounded-lg border border-line p-3">
                  <div className="text-xs font-semibold capitalize text-ink-2">
                    {name} case · probability {formatValue(s.probability, "pct", { digits: 0 })}
                  </div>
                  <div className="mt-1 text-xl font-semibold">{formatValue(s.value, "usd_per_share")}</div>
                  <ul className="mt-1 space-y-0.5 text-xs text-ink-2">
                    {s.growth1 !== undefined && <li>Near-term growth {formatValue(s.growth1, "pct")}</li>}
                    {s.margin_target !== undefined && (
                      <li>Target margin {formatValue(s.margin_target, "pct")}</li>
                    )}
                    {s.wacc !== undefined && <li>WACC {formatValue(s.wacc, "pct")}</li>}
                    {s.roe !== undefined && <li>ROE {formatValue(s.roe, "pct")}</li>}
                    {s.cost_of_equity !== undefined && (
                      <li>Cost of equity {formatValue(s.cost_of_equity, "pct")}</li>
                    )}
                  </ul>
                </div>
              ))}
            </div>
            <p className="mt-2 text-xs text-muted">
              Scenario values are intrinsic values from the {v.dcf ? "DCF" : "excess-return model"};
              probabilities are fixed in the config, not estimated.
            </p>
          </TabsContent>
        )}
        <TabsContent value="reverse">
          {v.reverse_dcf ? (
            <div className="space-y-1 text-sm">
              <p className="font-medium">{v.reverse_dcf.statement}</p>
              {v.reverse_dcf.assessment && roeBasis && (
                <p className="text-ink-2">
                  Assessment: <span className="font-medium">{v.reverse_dcf.assessment}</span> compared with
                  the 5-year median ROE ({formatValue(v.reverse_dcf.history_roe, "pct")}) and trailing ROE (
                  {formatValue(v.reverse_dcf.trailing_roe, "pct")}).
                </p>
              )}
              {v.reverse_dcf.assessment && !roeBasis && (
                <p className="text-ink-2">
                  Assessment: <span className="font-medium">{v.reverse_dcf.assessment}</span> compared with
                  delivered growth ({formatValue(v.reverse_dcf.history_growth, "pct")}) and consensus (
                  {formatValue(v.reverse_dcf.consensus_growth, "pct")}).
                </p>
              )}
              <p className="text-xs text-muted">
                {roeBasis
                  ? "Justified price-to-book = (ROE − g) ÷ (cost of equity − g), solved for ROE."
                  : `Solved against today's enterprise value of ${formatValue(v.reverse_dcf.enterprise_value, "usd")} at the app's WACC.`}
              </p>
            </div>
          ) : (
            <p className="text-sm text-muted">Reverse DCF unavailable (no market cap).</p>
          )}
        </TabsContent>
        <TabsContent value="hist">
          <MultiplesHistory v={v} profile={profile} />
        </TabsContent>
        {v.dcf && (
          <TabsContent value="whatif">
            <WhatIf ticker={ticker} v={v} />
          </TabsContent>
        )}
      </Tabs>
      <div className="text-xs text-muted">
        {roeBasis ? "Reference WACC" : "WACC"} {formatValue(v.wacc.value, "pct")}: cost of equity{" "}
        {formatValue(v.wacc.cost_of_equity, "pct")} (risk-free {formatValue(v.wacc.risk_free, "pct")} from{" "}
        {v.wacc.risk_free_source}; beta {v.wacc.beta.toFixed(2)} ({v.wacc.beta_source}); equity risk premium{" "}
        {formatValue(v.wacc.erp, "pct")}
        ), after-tax cost of debt {formatValue(v.wacc.cost_of_debt_after_tax, "pct")} (
        {v.wacc.cost_of_debt_source}); weights {formatValue(v.wacc.weight_equity, "pct", { digits: 0 })}{" "}
        equity / {formatValue(v.wacc.weight_debt, "pct", { digits: 0 })} debt. {v.wacc.notes.join(" ")}
      </div>
      <p className="text-xs text-ink-2">{v.disclaimer}</p>
    </div>
  );
}
