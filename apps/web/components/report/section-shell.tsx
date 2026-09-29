"use client";

import * as Collapsible from "@radix-ui/react-collapsible";
import { AlertTriangle, ChevronDown } from "lucide-react";
import { type ReactNode, useState } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";
import { formatDateTime } from "@/lib/format";
import type { AnySection, SourceMeta } from "@/lib/types";

export function SourceBadges({ sources }: { sources?: SourceMeta[] }) {
  if (!sources?.length) return null;
  const uniq = new Map<string, SourceMeta>();
  for (const s of sources) if (s.source && !uniq.has(s.source)) uniq.set(s.source, s);
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
      {[...uniq.values()].map((s) => (
        <span
          key={s.source}
          className={cn(
            "rounded border border-line px-1.5 py-0.5",
            s.status === "stale" && "border-warning/50 text-warning-ink",
            s.status === "missing" && "line-through",
          )}
          title={s.reason ?? (s.fetched_at ? `fetched ${formatDateTime(s.fetched_at)}` : undefined)}
        >
          {s.source}
          {s.fetched_at ? ` · ${formatDateTime(s.fetched_at)}` : ""}
          {s.status === "stale" ? " · stale" : ""}
        </span>
      ))}
    </div>
  );
}

export function MissingNote({ children }: { children: ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm text-ink-2">
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning-ink" aria-hidden />
      <div>{children}</div>
    </div>
  );
}

export function SectionShell({
  id,
  title,
  subtitle,
  data,
  loading,
  error,
  children,
  actions,
  defaultOpen = true,
  skeletonHeight = "h-40",
}: {
  id: string;
  title: string;
  subtitle?: ReactNode;
  data: AnySection | null;
  loading: boolean;
  error: string | null;
  children?: ReactNode;
  actions?: ReactNode;
  defaultOpen?: boolean;
  skeletonHeight?: string;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section
      id={id}
      aria-labelledby={`${id}-title`}
      className="report-section rounded-2xl border border-line bg-surface shadow-card"
    >
      <Collapsible.Root open={open} onOpenChange={setOpen}>
        <div className="flex flex-wrap items-start gap-2 px-4 pt-4 sm:px-6 sm:pt-5">
          <Collapsible.Trigger asChild>
            <button
              type="button"
              className="group flex min-w-0 flex-1 items-start gap-2 text-left"
              aria-expanded={open}
            >
              <ChevronDown
                className={cn(
                  "mt-0.5 size-4 shrink-0 text-muted transition-transform",
                  !open && "-rotate-90",
                )}
                aria-hidden
              />
              <span className="min-w-0">
                <h2 id={`${id}-title`} className="text-base font-semibold tracking-tight text-ink">
                  {title}
                </h2>
                {subtitle && <span className="mt-0.5 block text-xs text-muted">{subtitle}</span>}
              </span>
            </button>
          </Collapsible.Trigger>
          {actions}
        </div>
        {/* always mounted, so a collapsed section still prints in full */}
        <Collapsible.Content forceMount className="data-[state=closed]:hidden print:!block">
          <div className={cn("px-4 pt-3 pb-5 sm:px-6", loading && data && "opacity-60 transition-opacity")}>
            {!data && loading && (
              <div className="space-y-2" aria-busy="true" aria-label={`Loading ${title}`}>
                <Skeleton className="h-4 w-1/3" />
                <Skeleton className={cn("w-full", skeletonHeight)} />
              </div>
            )}
            {!data && !loading && error && (
              <MissingNote>This section could not be loaded: {error}</MissingNote>
            )}
            {data && data.status === "error" && <MissingNote>{data.reason}</MissingNote>}
            {data && data.status === "missing" && <MissingNote>Insufficient data: {data.reason}</MissingNote>}
            {data && data.status === "not_applicable" && <p className="text-sm text-ink-2">{data.reason}</p>}
            {data && (data.status === "ok" || data.status === "partial") && children}
            {data && data.reason && data.status === "partial" && (
              <p className="mt-3 text-xs text-muted">{data.reason}</p>
            )}
          </div>
          {data?.sources?.length ? (
            <div className="rounded-b-2xl border-t border-line bg-surface-2/40 px-4 py-2 sm:px-6">
              <SourceBadges sources={data.sources} />
            </div>
          ) : null}
        </Collapsible.Content>
      </Collapsible.Root>
    </section>
  );
}
