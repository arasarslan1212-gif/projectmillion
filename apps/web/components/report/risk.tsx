"use client";

import * as Collapsible from "@radix-ui/react-collapsible";
import { AlertOctagon, AlertTriangle, CheckCircle2, ChevronDown, Info, MinusCircle } from "lucide-react";
import { useCallback, useState } from "react";
import { axisStyle, baseOption, EChart } from "@/components/charts/echart";
import { MetricCell } from "@/components/ui/metric";
import { cn } from "@/lib/cn";
import { formatDate, formatValue } from "@/lib/format";
import type { ThemeColors } from "@/lib/theme";
import { withAlpha } from "@/lib/theme";
import type { AnySection, Metric } from "@/lib/types";

const SEVERITY: Record<string, { label: string; icon: typeof AlertOctagon; cls: string }> = {
  high: { label: "High", icon: AlertOctagon, cls: "text-critical-ink" },
  medium: { label: "Medium", icon: AlertTriangle, cls: "text-warning-ink" },
  low: { label: "Low", icon: Info, cls: "text-ink-2" },
  info: { label: "Info", icon: Info, cls: "text-muted" },
};

export function RedFlags({ rf }: { rf: AnySection }) {
  const [showPassed, setShowPassed] = useState(false);
  return (
    <div>
      {rf.triggered.length === 0 ? (
        <p className="flex items-center gap-2 text-sm text-good-ink">
          <CheckCircle2 className="size-4" aria-hidden /> No red flags triggered among {rf.passed.length}{" "}
          checks.
        </p>
      ) : (
        <ul className="space-y-2">
          {rf.triggered.map((f: AnySection) => {
            const s = SEVERITY[f.severity];
            const Icon = s.icon;
            return (
              <li key={f.id} className="flex gap-2 rounded-lg border border-line p-2.5">
                <Icon className={cn("mt-0.5 size-4 shrink-0", s.cls)} aria-hidden />
                <div className="min-w-0">
                  <div className="text-sm font-medium">
                    {f.title}{" "}
                    <span className={cn("ml-1 text-xs font-semibold", s.cls)}>{s.label} severity</span>
                  </div>
                  <p className="text-sm text-ink-2">{f.explanation}</p>
                  <p className="text-xs text-muted">
                    Source: {f.source}
                    {f.url && (
                      <>
                        {" · "}
                        <a
                          href={f.url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-accent-ink underline"
                        >
                          filing
                        </a>
                      </>
                    )}
                  </p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <Collapsible.Root open={showPassed} onOpenChange={setShowPassed} className="mt-3">
        <Collapsible.Trigger className="flex items-center gap-1 text-xs text-muted hover:text-ink-2">
          <ChevronDown
            className={cn("size-3.5 transition-transform", !showPassed && "-rotate-90")}
            aria-hidden
          />
          {rf.passed.length} checks passed · {rf.not_checked.length} could not be checked
        </Collapsible.Trigger>
        <Collapsible.Content>
          <ul className="mt-2 space-y-1 text-xs">
            {rf.passed.map((f: AnySection) => (
              <li key={f.id} className="flex gap-1.5 text-ink-2">
                <CheckCircle2 className="mt-0.5 size-3.5 shrink-0 text-good-ink" aria-hidden />
                <span>
                  <span className="font-medium">{f.title}:</span> {f.explanation}
                </span>
              </li>
            ))}
            {rf.not_checked.map((f: AnySection) => (
              <li key={f.id} className="flex gap-1.5 text-muted">
                <MinusCircle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                <span>
                  <span className="font-medium">{f.title}:</span> not checked ({f.reason})
                </span>
              </li>
            ))}
          </ul>
        </Collapsible.Content>
      </Collapsible.Root>
    </div>
  );
}

function Underwater({ d }: { d: AnySection }) {
  const build = useCallback(
    (c: ThemeColors) => ({
      ...baseOption(c),
      legend: { show: false },
      tooltip: { ...(baseOption(c).tooltip as object), valueFormatter: (v: number) => formatValue(v, "pct") },
      xAxis: {
        type: "category",
        data: d.dates,
        ...axisStyle(c),
        splitLine: { show: false },
        boundaryGap: false,
      },
      yAxis: {
        type: "value",
        max: 0,
        ...axisStyle(c),
        axisLabel: { color: c.muted, formatter: (v: number) => formatValue(v, "pct", { digits: 0 }) },
      },
      series: [
        {
          name: "Drawdown from peak",
          type: "line",
          data: d.values,
          symbol: "none",
          lineStyle: { width: 2, color: c.critical },
          areaStyle: { color: withAlpha(c.critical, 0.1) },
        },
      ],
    }),
    [d],
  );
  return (
    <div>
      <div className="text-xs font-semibold text-ink-2">Drawdown from previous peak (weekly, 5 years)</div>
      <EChart height={200} ariaLabel="Drawdown from previous peak over five years" build={build} />
    </div>
  );
}

function RiskFactorChanges({ d }: { d: AnySection | undefined }) {
  if (!d) return null;
  if (d.status !== "ok") return <p className="text-sm text-muted">Not compared: {d.reason}.</p>;
  const groups: [string, string, AnySection[]][] = [
    ["added", "New in the latest 10-K", d.added],
    ["removed", "No longer mentioned", d.removed],
    ["reworded", "Substantially reworded", d.reworded],
  ];
  const none = !d.added.length && !d.removed.length && !d.reworded.length;
  return (
    <div>
      <p className="text-sm text-ink-2">
        The{" "}
        <a
          href={d.latest.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-accent-ink underline"
        >
          10-K filed {formatDate(d.latest.filed)}
        </a>{" "}
        lists {d.latest.n_risks} risk factors, against {d.previous.n_risks} in the{" "}
        <a
          href={d.previous.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-accent-ink underline"
        >
          one filed {formatDate(d.previous.filed)}
        </a>
        {none
          ? "; the risks described are essentially unchanged."
          : `: ${d.added.length} new, ${d.removed.length} dropped, ${d.reworded.length} substantially reworded.`}
      </p>
      {!none && (
        <div className="mt-2 grid gap-3 md:grid-cols-3">
          {groups
            .filter(([, , items]) => items.length)
            .map(([id, label, items]) => (
              <div key={id} className="rounded-lg border border-line p-3">
                <div
                  className={cn(
                    "text-xs font-semibold",
                    id === "added" && "text-critical-ink",
                    id === "removed" && "text-good-ink",
                  )}
                >
                  {label}
                </div>
                <ul className="mt-1 space-y-1.5 text-xs text-ink-2">
                  {items.map((x, i) => (
                    <li key={i}>“{x.title}”</li>
                  ))}
                </ul>
              </div>
            ))}
        </div>
      )}
      <p className="mt-1 text-xs text-muted">{d.method}</p>
    </div>
  );
}

export function RiskSection({ r }: { r: AnySection }) {
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3 lg:grid-cols-5">
        {(r.metrics as Metric[]).map((m) => (
          <MetricCell key={m.id} m={m} />
        ))}
      </div>
      <Underwater d={r.drawdown} />
      <div>
        <h3 className="mb-2 text-sm font-semibold">Red flags</h3>
        <RedFlags rf={r.red_flags} />
      </div>
      <div>
        <h3 className="mb-2 text-sm font-semibold">What changed in the 10-K risk factors</h3>
        <RiskFactorChanges d={r.risk_factor_changes} />
      </div>
      <p className="text-xs text-muted">{r.notes.join(" ")}</p>
    </div>
  );
}
