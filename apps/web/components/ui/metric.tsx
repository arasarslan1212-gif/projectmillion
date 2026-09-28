"use client";

import { Info } from "lucide-react";
import { useDefinitions } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatDate, formatMetric } from "@/lib/format";
import type { Metric } from "@/lib/types";
import { Tip } from "./tooltip";

/** Tooltip body: definition, formula, source and as-of date for one metric. */
export function MetricTipBody({ m }: { m: Metric }) {
  const defs = useDefinitions();
  const d = defs[m.def] ?? defs[m.id];
  return (
    <div className="space-y-1.5">
      <div className="font-semibold">{d?.label ?? m.label}</div>
      {d?.definition && <p className="text-ink-2">{d.definition}</p>}
      {d?.formula && (
        <p>
          <span className="text-muted">Formula: </span>
          <span className="font-mono text-[11px]">{d.formula}</span>
        </p>
      )}
      {m.status !== "ok" && m.reason && <p className="text-warning-ink">Not shown: {m.reason}</p>}
      {m.note && <p className="text-ink-2">{m.note}</p>}
      <p className="text-muted">
        Source: {m.source ?? "—"}
        {m.as_of ? ` · as of ${formatDate(m.as_of)}` : ""}
      </p>
    </div>
  );
}

export function MetricTip({ m, children }: { m: Metric; children: React.ReactNode }) {
  return <Tip content={<MetricTipBody m={m} />}>{children}</Tip>;
}

/** Label + value cell with a keyboard-focusable info tooltip. */
export function MetricCell({
  m,
  className,
  digits,
  signed,
  emphasize,
}: {
  m?: Metric | null;
  className?: string;
  digits?: number;
  signed?: boolean;
  emphasize?: boolean;
}) {
  if (!m) return null;
  const missing = m.value === null || m.value === undefined;
  return (
    <div className={cn("min-w-0", className)}>
      <MetricTip m={m}>
        <button
          type="button"
          className="group flex max-w-full items-center gap-1 text-left text-xs text-muted hover:text-ink-2"
        >
          <span className="min-w-0 truncate">{m.label}</span>
          <Info className="size-3 shrink-0 opacity-60 group-hover:opacity-100" aria-hidden />
          <span className="sr-only">definition and source</span>
        </button>
      </MetricTip>
      <div
        className={cn(
          "tabular mt-0.5 truncate",
          emphasize ? "text-lg font-semibold" : "text-sm font-medium",
          missing && "text-muted",
        )}
      >
        {missing ? (
          <span title={m.reason ?? "insufficient data"}>Insufficient data</span>
        ) : (
          formatMetric(m, { digits, signed })
        )}
      </div>
    </div>
  );
}

export function MetricInline({
  m,
  digits,
  signed,
  className,
}: {
  m?: Metric | null;
  digits?: number;
  signed?: boolean;
  className?: string;
}) {
  if (!m) return <span className="text-muted">—</span>;
  return (
    <MetricTip m={m}>
      <button
        type="button"
        className={cn(
          "tabular underline decoration-dotted decoration-muted/60 underline-offset-2",
          className,
        )}
      >
        {m.value === null ? "n/a" : formatMetric(m, { digits, signed })}
      </button>
    </MetricTip>
  );
}
