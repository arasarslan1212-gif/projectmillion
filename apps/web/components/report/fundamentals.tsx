"use client";

import { useCallback, useMemo, useState } from "react";
import { axisStyle, baseOption, EChart } from "@/components/charts/echart";
import { MetricCell } from "@/components/ui/metric";
import { Segmented } from "@/components/ui/segmented";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Tip } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import { formatValue } from "@/lib/format";
import type { ThemeColors } from "@/lib/theme";
import { withAlpha } from "@/lib/theme";
import type { AnySection, Metric, Unit } from "@/lib/types";

type Mode = "values" | "common" | "yoy";

interface StmtRow {
  key: string;
  label: string;
  unit: Unit;
  values: (number | null)[];
  yoy: (number | null)[];
  common_size: (number | null)[];
  concept: string | null;
  derived: string | null;
  cagr: Record<string, number | null> | null;
}

function StatementTable({ block, mode, stmt }: { block: AnySection; mode: Mode; stmt: string }) {
  const rows: StmtRow[] = block.statements[stmt] ?? [];
  const cols: { label: string; end: string; filed: string | null }[] = block.columns;
  if (!rows.length) return <p className="text-sm text-muted">No data for this statement.</p>;
  const showCagr = rows.some((r) => r.cagr);
  return (
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className="tabular w-full min-w-[640px] text-right text-xs">
        <caption className="sr-only">
          {stmt} statement,{" "}
          {mode === "values"
            ? "reported values"
            : mode === "common"
              ? "common-size"
              : "year-over-year change"}
        </caption>
        <thead className="bg-surface-2 text-muted">
          <tr>
            <th scope="col" className="sticky left-0 z-10 bg-surface-2 px-2 py-1.5 text-left font-medium">
              Item
            </th>
            {cols.map((c) => (
              <th
                key={c.label}
                scope="col"
                className="px-2 py-1.5 font-medium whitespace-nowrap"
                title={c.filed ? `Period end ${c.end}; filed ${c.filed}` : c.end}
              >
                {c.label}
              </th>
            ))}
            {showCagr && (
              <>
                <th className="px-2 py-1.5 font-medium">3y CAGR</th>
                <th className="px-2 py-1.5 font-medium">5y CAGR</th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className="border-t border-line">
              <th
                scope="row"
                className="sticky left-0 z-10 bg-surface px-2 py-1 text-left font-normal whitespace-nowrap text-ink-2"
              >
                <Tip
                  content={
                    <div className="space-y-1">
                      <div className="font-semibold">{r.label}</div>
                      {r.concept && (
                        <div>
                          XBRL concept: <span className="font-mono">{r.concept}</span>
                        </div>
                      )}
                      {r.derived && <div>Derived: {r.derived}</div>}
                      <div className="text-muted">Source: SEC EDGAR company facts (point-in-time)</div>
                    </div>
                  }
                >
                  <button
                    type="button"
                    className="text-left underline decoration-dotted decoration-muted/50 underline-offset-2"
                  >
                    {r.label}
                  </button>
                </Tip>
              </th>
              {(mode === "values" ? r.values : mode === "common" ? r.common_size : r.yoy).map((v, i) => (
                <td key={i} className={cn("px-2 py-1", v !== null && v < 0 && "text-critical-ink")}>
                  {mode === "values"
                    ? formatValue(v, r.unit)
                    : formatValue(v, "pct", { signed: mode === "yoy" })}
                </td>
              ))}
              {showCagr && (
                <>
                  <td className="px-2 py-1">{formatValue(r.cagr?.["3y"] ?? null, "pct")}</td>
                  <td className="px-2 py-1">{formatValue(r.cagr?.["5y"] ?? null, "pct")}</td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function barOption(
  c: ThemeColors,
  labels: string[],
  values: (number | null)[],
  estimates: (number | null)[],
  unit: Unit,
  title: string,
) {
  const data = values.map((v) => ({
    value: v,
    itemStyle: { color: c.series[0], borderRadius: v !== null && v < 0 ? [0, 0, 4, 4] : [4, 4, 0, 0] },
  }));
  const est = estimates.map((v) => ({
    value: v,
    itemStyle: {
      color: withAlpha(c.series[0], 0.35),
      borderRadius: [4, 4, 0, 0],
      borderColor: c.series[0],
      borderWidth: 1,
      borderType: "dashed",
    },
  }));
  return {
    ...baseOption(c),
    legend: { show: false },
    grid: { left: 4, right: 8, top: 24, bottom: 4, containLabel: true },
    tooltip: {
      ...(baseOption(c).tooltip as object),
      trigger: "axis",
      valueFormatter: (v: number) => formatValue(v, unit),
    },
    xAxis: { type: "category", data: labels, ...axisStyle(c), splitLine: { show: false } },
    yAxis: {
      type: "value",
      ...axisStyle(c),
      axisLabel: {
        color: c.muted,
        formatter: (v: number) => formatValue(v, unit, { digits: unit === "usd_per_share" ? 2 : 0 }),
      },
    },
    series: [
      {
        name: title,
        type: "bar",
        data: [...data, ...est.map(() => ({ value: null }))],
        barMaxWidth: 24,
        stack: "a",
      },
      {
        name: `${title} (consensus estimate)`,
        type: "bar",
        data: [...values.map(() => ({ value: null })), ...est],
        barMaxWidth: 24,
        stack: "a",
      },
    ],
  };
}

function FinancialBars({ f }: { f: AnySection }) {
  const ann = f.annual;
  const cols: string[] = ann.columns.map((c: { label: string }) => c.label);
  const row = (key: string): (number | null)[] => {
    for (const stmt of Object.values(ann.statements) as StmtRow[][]) {
      const r = stmt.find((x) => x.key === key);
      if (r) return r.values;
    }
    return cols.map(() => null);
  };
  const est = f.estimates?.rows ?? [];
  const estLabels = est.map((e: { label: string }) => e.label);
  const specs: { key: string; title: string; unit: Unit; est: (number | null)[] }[] = [
    {
      key: "revenue",
      title: "Revenue",
      unit: "usd",
      est: est.map((e: AnySection) => e.revenue?.mean ?? null),
    },
    {
      key: "eps_diluted",
      title: "Diluted EPS",
      unit: "usd_per_share",
      est: est.map((e: AnySection) => e.eps?.mean ?? null),
    },
    f.profile === "bank" || f.profile === "insurer"
      ? { key: "net_income", title: "Net income", unit: "usd", est: [] }
      : { key: "fcf", title: "Free cash flow", unit: "usd", est: [] },
  ];
  return (
    <div>
      <div className="grid gap-4 md:grid-cols-3">
        {specs.map((s) => {
          const vals = row(s.key);
          const labels = [...cols, ...(s.est.length ? estLabels : [])];
          return (
            <div key={s.key}>
              <div className="text-xs font-semibold text-ink-2">{s.title}</div>
              <EChart
                height={200}
                ariaLabel={`${s.title} by fiscal year${s.est.length ? ", with consensus estimates" : ""}`}
                build={(c) => barOption(c, labels, vals, s.est, s.unit, s.title)}
                table={{
                  caption: s.title,
                  columns: ["Period", s.title],
                  rows: labels.map((l, i) => [
                    l,
                    formatValue(i < vals.length ? vals[i] : (s.est[i - vals.length] ?? null), s.unit),
                  ]),
                }}
              />
            </div>
          );
        })}
      </div>
      <p className="mt-2 text-xs text-muted">
        Solid bars: reported (SEC filings). Dashed bars: analyst consensus
        {f.estimates?.source ? ` (${f.estimates.source})` : ""}. {f.estimates?.eps_basis}{" "}
        {f.estimates?.rows?.length
          ? ""
          : f.estimates?.reason
            ? `Estimates unavailable: ${f.estimates.reason}.`
            : ""}{" "}
        Free-cash-flow estimates are not available from the configured source.
      </p>
    </div>
  );
}

const MARGIN_NAMES: Record<string, string> = {
  gross_margin: "Gross",
  operating_margin: "Operating",
  net_margin: "Net",
  fcf_margin: "FCF",
};

function MarginsChart({ f }: { f: AnySection }) {
  const names = MARGIN_NAMES;
  const r = f.ratios;
  const keys = ["gross_margin", "operating_margin", "net_margin", "fcf_margin"];
  const rows = keys.map((k) => r.rows.find((x: AnySection) => x.key === k)).filter(Boolean);
  const build = useCallback(
    (c: ThemeColors) => ({
      ...baseOption(c),
      tooltip: { ...(baseOption(c).tooltip as object), valueFormatter: (v: number) => formatValue(v, "pct") },
      xAxis: {
        type: "category",
        data: r.columns,
        ...axisStyle(c),
        splitLine: { show: false },
        boundaryGap: false,
      },
      yAxis: {
        type: "value",
        ...axisStyle(c),
        axisLabel: { color: c.muted, formatter: (v: number) => formatValue(v, "pct", { digits: 0 }) },
      },
      series: rows.map((row: AnySection, i: number) => ({
        name: names[row.key],
        type: "line",
        data: row.values,
        lineStyle: { width: 2, color: c.series[i] },
        itemStyle: { color: c.series[i] },
        symbol: "circle",
        symbolSize: 6,
        connectNulls: false,
        endLabel: { show: true, formatter: names[row.key], color: c.ink2, fontSize: 11 },
      })),
      grid: { left: 8, right: 70, top: 28, bottom: 8, containLabel: true },
    }),
    [r, rows],
  );
  if (!rows.length) return null;
  return (
    <div>
      <div className="text-xs font-semibold text-ink-2">Margins over time</div>
      <EChart
        height={240}
        ariaLabel="Gross, operating, net and free-cash-flow margins by fiscal year"
        build={build}
        table={{
          caption: "Margins by fiscal year",
          columns: ["Year", ...rows.map((x: AnySection) => names[x.key])],
          rows: r.columns.map((col: string, i: number) => [
            col,
            ...rows.map((x: AnySection) => formatValue(x.values[i], "pct")),
          ]),
        }}
      />
    </div>
  );
}

function RatioTable({ f }: { f: AnySection }) {
  const r = f.ratios;
  return (
    <div className="overflow-x-auto rounded-lg border border-line">
      <table className="tabular w-full min-w-[640px] text-right text-xs">
        <caption className="sr-only">Financial ratios by fiscal year</caption>
        <thead className="bg-surface-2 text-muted">
          <tr>
            <th className="sticky left-0 bg-surface-2 px-2 py-1.5 text-left font-medium">Ratio</th>
            <th className="px-2 py-1.5 font-medium">TTM</th>
            {r.columns.map((c: string) => (
              <th key={c} className="px-2 py-1.5 font-medium">
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {r.rows.map((row: AnySection) => (
            <tr key={row.key} className="border-t border-line">
              <th
                scope="row"
                className="sticky left-0 bg-surface px-2 py-1 text-left font-normal whitespace-nowrap text-ink-2"
              >
                {row.label}
              </th>
              <td className="px-2 py-1 font-medium">{formatValue(row.ttm, row.unit)}</td>
              {row.values.map((v: number | null, i: number) => (
                <td key={i} className="px-2 py-1">
                  {formatValue(v, row.unit)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DebtLadder({ q }: { q: AnySection }) {
  const build = useCallback(
    (c: ThemeColors) => ({
      ...baseOption(c),
      legend: { show: false },
      tooltip: { ...(baseOption(c).tooltip as object), valueFormatter: (v: number) => formatValue(v, "usd") },
      xAxis: {
        type: "category",
        data: q.debt_ladder.map((x: AnySection) => x.bucket),
        ...axisStyle(c),
        splitLine: { show: false },
      },
      yAxis: {
        type: "value",
        ...axisStyle(c),
        axisLabel: { color: c.muted, formatter: (v: number) => formatValue(v, "usd", { digits: 0 }) },
      },
      series: [
        {
          name: "Principal due",
          type: "bar",
          barMaxWidth: 24,
          data: q.debt_ladder.map((x: AnySection) => x.amount),
          itemStyle: { color: c.series[0], borderRadius: [4, 4, 0, 0] },
        },
      ],
    }),
    [q],
  );
  return (
    <div>
      <div className="text-xs font-semibold text-ink-2">
        Debt maturity ladder (as of {q.debt_ladder_as_of})
      </div>
      <EChart
        height={200}
        ariaLabel="Debt principal due by year"
        build={build}
        table={{
          caption: "Debt maturities",
          columns: ["Bucket", "Principal due"],
          rows: q.debt_ladder.map((x: AnySection) => [x.bucket, formatValue(x.amount, "usd")]),
        }}
      />
    </div>
  );
}

export function FundamentalsSection({ f }: { f: AnySection }) {
  const [period, setPeriod] = useState<"annual" | "quarterly">("annual");
  const [mode, setMode] = useState<Mode>("values");
  const block = period === "annual" ? f.annual : f.quarterly;
  const growth: Metric[] = useMemo(
    () => (f.growth as Metric[]).filter((m) => /_(1y|3y|5y|10y)$|_q$/.test(m.id)),
    [f.growth],
  );
  const growthMain = growth.filter((m) => /^(revenue|eps|fcf|dps)_/.test(m.id));
  return (
    <div className="space-y-5">
      <FinancialBars f={f} />
      <Tabs defaultValue="statements">
        <TabsList>
          <TabsTrigger value="statements">Statements</TabsTrigger>
          <TabsTrigger value="ratios">Ratios</TabsTrigger>
          <TabsTrigger value="growth">Growth &amp; quality</TabsTrigger>
          <TabsTrigger value="kpis">Sector KPIs</TabsTrigger>
        </TabsList>
        <TabsContent value="statements">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <Segmented
              label="Period"
              value={period}
              onChange={setPeriod}
              options={[
                { value: "annual", label: "Annual" },
                { value: "quarterly", label: "Quarterly" },
              ]}
            />
            <Segmented
              label="Display"
              value={mode}
              onChange={setMode}
              options={[
                { value: "values", label: "Values" },
                { value: "common", label: "Common-size" },
                { value: "yoy", label: period === "annual" ? "YoY %" : "vs. year-ago Q" },
              ]}
            />
            <span className="text-xs text-muted">
              {mode === "common"
                ? "Income and cash-flow items as % of revenue; balance-sheet items as % of total assets."
                : f.ttm_note}
            </span>
          </div>
          <Tabs defaultValue="income">
            <TabsList className="border-b-0">
              <TabsTrigger value="income">Income statement</TabsTrigger>
              <TabsTrigger value="balance">Balance sheet</TabsTrigger>
              <TabsTrigger value="cashflow">Cash flow</TabsTrigger>
            </TabsList>
            {(["income", "balance", "cashflow"] as const).map((s) => (
              <TabsContent key={s} value={s}>
                <StatementTable block={block} mode={mode} stmt={s} />
              </TabsContent>
            ))}
          </Tabs>
          <ul className="mt-2 list-disc space-y-0.5 pl-4 text-xs text-muted">
            {f.notes.map((n: string) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </TabsContent>
        <TabsContent value="ratios">
          <div className="space-y-4">
            <MarginsChart f={f} />
            <RatioTable f={f} />
          </div>
        </TabsContent>
        <TabsContent value="growth">
          <div className="space-y-5">
            <div>
              <h3 className="mb-2 text-xs font-semibold text-ink-2">Growth</h3>
              <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
                {growthMain.map((m) => (
                  <MetricCell key={m.id} m={m} signed />
                ))}
              </div>
            </div>
            <div>
              <h3 className="mb-2 text-xs font-semibold text-ink-2">Quality</h3>
              <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
                {(f.quality.metrics as Metric[]).map((m) => (
                  <MetricCell key={m.id} m={m} />
                ))}
              </div>
            </div>
            {f.quality.debt_ladder ? (
              <DebtLadder q={f.quality} />
            ) : (
              <p className="text-xs text-muted">{f.quality.debt_ladder_note}</p>
            )}
          </div>
        </TabsContent>
        <TabsContent value="kpis">
          <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
            {(f.sector_kpis as Metric[]).map((m) => (
              <MetricCell key={m.id} m={m} />
            ))}
          </div>
          <p className="mt-3 text-xs text-muted">
            KPIs for the <span className="font-medium">{f.profile.replace("_", " ")}</span> profile. Items
            marked insufficient data are not reported in standardized XBRL and are never estimated.
          </p>
        </TabsContent>
      </Tabs>
    </div>
  );
}
