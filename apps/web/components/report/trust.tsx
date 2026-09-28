"use client";

import * as Collapsible from "@radix-ui/react-collapsible";
import { ChevronDown } from "lucide-react";
import { useCallback, useState } from "react";
import { EChart } from "@/components/charts/echart";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/cn";
import { formatValue, gradeColor } from "@/lib/format";
import type { ThemeColors } from "@/lib/theme";
import { withAlpha } from "@/lib/theme";
import type { AnySection, Unit } from "@/lib/types";

export function ScoreBar({ score, label }: { score: number | null; label?: string }) {
  if (score === null || score === undefined) return <span className="text-xs text-muted">n/a</span>;
  const color =
    score >= 60
      ? "var(--good)"
      : score >= 40
        ? "var(--accent)"
        : score >= 25
          ? "var(--serious)"
          : "var(--critical)";
  return (
    <div
      className="flex items-center gap-2"
      aria-label={label ? `${label}: ${Math.round(score)} of 100` : undefined}
    >
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-surface-2" aria-hidden>
        <div className="h-full rounded-full" style={{ width: `${Math.max(2, score)}%`, background: color }} />
      </div>
      <span className="tabular w-7 text-right text-xs font-medium">{Math.round(score)}</span>
    </div>
  );
}

function Radar({ pillars }: { pillars: AnySection[] }) {
  const avail = pillars.filter((p) => p.score !== null);
  const build = useCallback(
    (c: ThemeColors) => ({
      backgroundColor: "transparent",
      textStyle: { fontFamily: "system-ui, sans-serif" },
      tooltip: {
        trigger: "item",
        backgroundColor: c.surface,
        borderColor: c.grid,
        textStyle: { color: c.ink, fontSize: 12 },
      },
      radar: {
        indicator: avail.map((p) => ({ name: p.label, max: 100 })),
        radius: "65%",
        splitNumber: 4,
        axisName: { color: c.ink2, fontSize: 11 },
        splitLine: { lineStyle: { color: c.grid } },
        splitArea: { show: false },
        axisLine: { lineStyle: { color: c.grid } },
      },
      series: [
        {
          type: "radar",
          name: "Pillar scores",
          data: [{ value: avail.map((p) => Math.round(p.score)), name: "Pillar score (0–100)" }],
          symbolSize: 7,
          lineStyle: { width: 2, color: c.series[0] },
          itemStyle: { color: c.series[0], borderColor: c.surface, borderWidth: 2 },
          areaStyle: { color: withAlpha(c.series[0], 0.12) },
        },
      ],
    }),
    [avail],
  );
  return (
    <EChart
      height={300}
      ariaLabel={`Trust Rating pillars: ${avail.map((p) => `${p.label} ${Math.round(p.score)}`).join(", ")}`}
      build={build}
      table={{
        caption: "Pillar scores",
        columns: ["Pillar", "Score", "Weight"],
        rows: pillars.map((p) => [
          p.label,
          p.score === null ? "n/a" : Math.round(p.score),
          formatValue(p.effective_weight, "pct", { digits: 0 }),
        ]),
      }}
    />
  );
}

function PillarRow({ p }: { p: AnySection }) {
  const [open, setOpen] = useState(false);
  return (
    <Collapsible.Root open={open} onOpenChange={setOpen} className="border-t border-line first:border-t-0">
      <Collapsible.Trigger asChild>
        <button
          type="button"
          className="flex w-full items-center gap-3 py-2 text-left hover:bg-surface-2/60"
          aria-expanded={open}
        >
          <ChevronDown
            className={cn("size-4 shrink-0 text-muted transition-transform", !open && "-rotate-90")}
            aria-hidden
          />
          <span className="min-w-0 flex-1 text-sm font-medium">{p.label}</span>
          {p.capped_by.length > 0 && <Badge tone="critical">capped</Badge>}
          <span className="hidden text-xs text-muted sm:inline">
            weight {formatValue(p.effective_weight || p.weight, "pct", { digits: 0 })}
          </span>
          <ScoreBar score={p.score} label={p.label} />
        </button>
      </Collapsible.Trigger>
      <Collapsible.Content>
        <div className="pb-3 pl-7">
          <p className="text-sm text-ink-2">{p.explanation}</p>
          {(p.raise_if || p.lower_if) && (
            <ul className="mt-1 space-y-0.5 text-xs text-muted">
              {p.raise_if && <li>↑ {p.raise_if}</li>}
              {p.lower_if && <li>↓ {p.lower_if}</li>}
            </ul>
          )}
          <div className="mt-2 overflow-x-auto">
            <table className="tabular w-full min-w-[520px] text-xs">
              <caption className="sr-only">Metrics in the {p.label} pillar</caption>
              <thead className="text-muted">
                <tr>
                  <th className="py-1 text-left font-medium">Metric</th>
                  <th className="py-1 text-right font-medium">Value</th>
                  <th className="py-1 text-right font-medium">Basis</th>
                  <th className="py-1 pl-3 text-left font-medium">Score</th>
                </tr>
              </thead>
              <tbody>
                {p.metrics.map((m: AnySection) => (
                  <tr key={m.id} className="border-t border-line align-top">
                    <td className="py-1 pr-2">
                      <div>{m.label}</div>
                      {(m.note || m.reason) && (
                        <div className="text-[11px] text-muted">
                          {m.value === null ? `Not scored: ${m.reason}` : m.note}
                        </div>
                      )}
                    </td>
                    <td className="py-1 text-right">{formatValue(m.value, m.unit as Unit)}</td>
                    <td className="py-1 text-right text-muted">
                      {m.basis === "sector"
                        ? `${Math.round(m.percentile)}th pct of ${m.n}`
                        : m.basis === "anchor"
                          ? "anchors"
                          : "—"}
                    </td>
                    <td className="py-1 pl-3">
                      <ScoreBar score={m.score} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Collapsible.Content>
    </Collapsible.Root>
  );
}

function AccountingScores({ s }: { s: AnySection }) {
  const items = [
    { key: "altman", title: "Altman Z" },
    { key: "piotroski", title: "Piotroski F" },
    { key: "beneish", title: "Beneish M" },
  ];
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {items.map(({ key, title }) => {
        const v = s[key];
        return (
          <div key={key} className="rounded-lg border border-line p-3">
            <div className="text-xs text-muted">{v?.variant ?? title}</div>
            <div className="tabular mt-0.5 text-lg font-semibold">
              {v?.value === null || v?.value === undefined
                ? "n/a"
                : v.value.toFixed(key === "piotroski" ? 0 : 2)}
            </div>
            <div className="text-xs text-ink-2">
              {[
                v?.zone ? `Zone: ${v.zone}` : (v?.reason ?? (v ? null : "Not applicable to this profile")),
                v?.period,
              ]
                .filter(Boolean)
                .join(" · ")}
            </div>
            {v?.note && <div className="mt-1 text-[11px] text-muted">{v.note}</div>}
          </div>
        );
      })}
    </div>
  );
}

export function TrustSection({ t }: { t: AnySection }) {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
        <div>
          <div className="flex items-baseline gap-3">
            <div className="text-4xl font-semibold">{t.score === null ? "—" : Math.round(t.score)}</div>
            <div className={cn("text-2xl font-semibold", gradeColor(t.grade))}>{t.grade ?? ""}</div>
            <div className="text-xs text-muted">
              of 100 · {Math.round((t.coverage ?? 0) * 100)}% of pillar weight had data
            </div>
          </div>
          {t.deductions?.length > 0 && (
            <p className="mt-1 text-xs text-critical-ink">
              Red-flag deductions:{" "}
              {t.deductions.map((d: AnySection) => `${d.flag.replace(/_/g, " ")} −${d.points}`).join(", ")}
              {t.raw_score !== null ? ` (before deductions ${Math.round(t.raw_score)})` : ""}
            </p>
          )}
          <Radar pillars={t.pillars} />
          {t.missing_pillars?.length > 0 && (
            <div className="text-xs text-muted">
              <span className="font-medium text-ink-2">Not scored (weight redistributed):</span>
              <ul className="mt-0.5 list-disc pl-4">
                {t.missing_pillars.map((m: AnySection) => (
                  <li key={m.id}>
                    {m.label}: {m.reason}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <div>
          <div className="rounded-lg border border-line px-3">
            {t.pillars.map((p: AnySection) => (
              <PillarRow key={p.id} p={p} />
            ))}
          </div>
          <p className="mt-2 text-xs text-muted">{t.method}</p>
          <p className="mt-1 text-xs text-muted">{t.universe_note}</p>
        </div>
      </div>
      <div>
        <h3 className="mb-2 text-xs font-semibold text-ink-2">Accounting scores</h3>
        <AccountingScores s={t.accounting_scores} />
      </div>
      <p className="text-xs text-ink-2">{t.disclaimer}</p>
    </div>
  );
}
