"use client";

import { useCallback } from "react";
import { axisStyle, baseOption, EChart } from "@/components/charts/echart";
import { MissingNote } from "@/components/report/section-shell";
import { cn } from "@/lib/cn";
import { formatDate, formatValue } from "@/lib/format";
import type { ThemeColors } from "@/lib/theme";
import type { AnySection } from "@/lib/types";

const t = (x: number | null | undefined) => (x == null ? "—" : x.toFixed(1));

function FactorChart({ rows }: { rows: AnySection[] }) {
  const build = useCallback(
    (c: ThemeColors) => ({
      ...baseOption(c),
      legend: { show: false },
      grid: { left: 8, right: 48, top: 8, bottom: 8, containLabel: true },
      tooltip: {
        ...(baseOption(c).tooltip as object),
        axisPointer: { type: "shadow" },
        formatter: (ps: { dataIndex: number }[]) => {
          const r = rows[ps[0].dataIndex];
          return `${r.label}: beta <b>${r.beta.toFixed(2)}</b> (t ${t(r.t)}${r.significant ? "" : ", not distinguishable from zero"})`;
        },
      },
      xAxis: { type: "value", ...axisStyle(c) },
      yAxis: {
        type: "category",
        inverse: true,
        data: rows.map((r) => `${r.label}${r.significant ? "" : " (n.s.)"}`),
        ...axisStyle(c),
        splitLine: { show: false },
        axisLabel: { color: c.ink2 },
      },
      series: [
        {
          type: "bar",
          barMaxWidth: 16,
          data: rows.map((r) => ({
            value: r.beta,
            itemStyle: {
              color: r.beta >= 0 ? c.divergePos : c.divergeNeg,
              opacity: r.significant ? 1 : 0.35,
              borderRadius: r.beta >= 0 ? [0, 4, 4, 0] : [4, 0, 0, 4],
            },
          })),
          label: {
            show: true,
            position: "right",
            color: c.ink2,
            fontSize: 10,
            formatter: (p: { value: number }) => p.value.toFixed(2),
          },
        },
      ],
    }),
    [rows],
  );
  return (
    <EChart
      build={build}
      height={Math.max(170, 32 * rows.length + 20)}
      ariaLabel="Factor exposures: regression betas of weekly returns"
      table={{
        caption: "Factor exposures",
        columns: ["Factor", "Beta", "t-stat", "Significant", "Funds (long − short)"],
        rows: rows.map((r) => [
          r.label,
          r.beta.toFixed(2),
          t(r.t),
          r.significant ? "yes" : "no",
          (r.funds ?? []).join(" − "),
        ]),
      }}
    />
  );
}

function SeasonChart({ rows }: { rows: AnySection[] }) {
  const build = useCallback(
    (c: ThemeColors) => ({
      ...baseOption(c),
      legend: { show: false },
      grid: { left: 8, right: 8, top: 20, bottom: 8, containLabel: true },
      tooltip: {
        ...(baseOption(c).tooltip as object),
        axisPointer: { type: "shadow" },
        formatter: (ps: { dataIndex: number }[]) => {
          const r = rows[ps[0].dataIndex];
          return `${r.month}: average ${formatValue(r.mean, "pct", { signed: true })} over ${r.n} years (positive ${formatValue(r.positive_share, "pct", { digits: 0 })})<br/>vs. market ${formatValue(r.excess_mean, "pct", { signed: true })} · t ${t(r.t)}${r.significant ? " · significant" : ""}`;
        },
      },
      xAxis: {
        type: "category",
        data: rows.map((r) => r.month),
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
          type: "bar",
          barCategoryGap: "30%",
          data: rows.map((r) => ({
            value: r.mean,
            itemStyle: {
              color: (r.mean ?? 0) >= 0 ? c.divergePos : c.divergeNeg,
              borderRadius: (r.mean ?? 0) >= 0 ? [3, 3, 0, 0] : [0, 0, 3, 3],
            },
          })),
          label: {
            show: true,
            position: "top",
            color: c.ink,
            fontSize: 11,
            formatter: (p: { dataIndex: number }) => (rows[p.dataIndex].significant ? "*" : ""),
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
      ariaLabel="Average return by calendar month"
      table={{
        caption: "Month-of-year returns",
        columns: ["Month", "Average", "Positive", "vs. market", "t-stat", "Years"],
        rows: rows.map((r) => [
          r.month,
          formatValue(r.mean, "pct", { signed: true }),
          formatValue(r.positive_share, "pct", { digits: 0 }),
          formatValue(r.excess_mean, "pct", { signed: true }),
          t(r.t),
          r.n,
        ]),
      }}
    />
  );
}

function effectText(r: AnySection): string {
  return `${formatValue(r.effect, "pct", { signed: true })} per ${r.unit}`;
}

export function QuantSection({ q }: { q: AnySection }) {
  const f = q.factors;
  const s = q.seasonality;
  const mkt = f.rows?.find((r: AnySection) => r.id === "market");
  const tilts = (f.rows ?? []).filter((r: AnySection) => r.id !== "market" && r.significant);
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold">Factor exposures</h3>
        {f.status !== "ok" ? (
          <MissingNote>Not available: {f.reason}.</MissingNote>
        ) : (
          <>
            <p className="mt-0.5 text-sm text-ink-2">
              {mkt ? `It has moved about ${mkt.beta.toFixed(2)}× the market (t ${t(mkt.t)}). ` : ""}
              {tilts.length
                ? `Reliable style tilts: ${tilts.map((r: AnySection) => `${r.label.toLowerCase()} ${r.beta > 0 ? "positive" : "negative"}`).join(", ")}.`
                : "No style tilt is distinguishable from zero."}{" "}
              The model explains {formatValue(f.r2, "pct", { digits: 0 })} of weekly moves; the rest is
              company-specific.
            </p>
            <FactorChart rows={f.rows} />
            <p className="text-xs text-muted">
              Weekly returns {formatDate(f.start)} to {formatDate(f.end)} ({f.n_weeks} weeks). Faded bars and
              “n.s.” mark estimates with |t| below 2. Unexplained return (alpha){" "}
              {formatValue(f.alpha_annual, "pct", { signed: true })} a year, t {t(f.alpha_t)}:{" "}
              {Math.abs(f.alpha_t) < 2 ? "not distinguishable from luck" : "large relative to its noise"}.
              {f.missing_factors?.length ? ` Missing factors: ${f.missing_factors.join(", ")}.` : ""}
            </p>
          </>
        )}
      </div>

      <div>
        <h3 className="text-sm font-semibold">Macro sensitivity</h3>
        {q.macro.rows.length === 0 ? (
          <MissingNote>Macro series unavailable.</MissingNote>
        ) : (
          <>
            <p className="mt-0.5 text-xs text-muted">
              How the stock has reacted, beyond the market&apos;s own move, when each series changed (weekly,
              three years).
            </p>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full min-w-[32rem] text-sm">
                <thead>
                  <tr className="border-b border-line text-left text-xs text-muted">
                    <th className="py-1.5 pr-2 font-medium">Series</th>
                    <th className="py-1.5 pr-2 text-right font-medium">Typical reaction</th>
                    <th className="py-1.5 pr-2 text-right font-medium">t-stat</th>
                    <th className="py-1.5 pr-2 text-right font-medium">Correlation</th>
                    <th className="py-1.5 font-medium">Reading</th>
                  </tr>
                </thead>
                <tbody>
                  {q.macro.rows.map((r: AnySection) => (
                    <tr key={r.id} className="border-b border-line last:border-b-0">
                      <td className="py-1.5 pr-2">{r.label}</td>
                      <td className="tabular py-1.5 pr-2 text-right">{effectText(r)}</td>
                      <td className="tabular py-1.5 pr-2 text-right">{t(r.t)}</td>
                      <td className="tabular py-1.5 pr-2 text-right">
                        {formatValue(r.correlation, "ratio")}
                      </td>
                      <td className={cn("py-1.5 text-xs", r.significant ? "text-ink" : "text-muted")}>
                        {r.significant ? "a reliable link" : "no reliable link"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="mt-1 text-xs text-muted">
              Source: {q.macro.rows[0]?.source}. Historical association, not a forecast.
            </p>
          </>
        )}
      </div>

      <div>
        <h3 className="text-sm font-semibold">Month-of-year returns</h3>
        {s.status !== "ok" ? (
          <MissingNote>Not available: {s.reason}.</MissingNote>
        ) : (
          <>
            <p className="mt-0.5 text-sm text-ink-2">
              {s.any_significant
                ? `Months marked * stand out beyond chance even after allowing for testing twelve months at once (|t| ≥ ${s.t_threshold.toFixed(2)}).`
                : `No month stands out beyond chance once twelve months are tested at once (|t| ≥ ${s.t_threshold.toFixed(2)} would be needed); the best (${s.best}) and worst (${s.worst}) months are likely noise.`}
            </p>
            <SeasonChart rows={s.rows} />
            <p className="text-xs text-muted">Average monthly return over the last {s.years} years.</p>
          </>
        )}
      </div>
      <p className="text-xs text-muted">{q.note}</p>
    </div>
  );
}
