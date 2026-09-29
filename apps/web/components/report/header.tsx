"use client";

import { Bookmark, BookmarkCheck, Printer, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MetricTip } from "@/components/ui/metric";
import { Skeleton } from "@/components/ui/skeleton";
import { Tip } from "@/components/ui/tooltip";
import { cn } from "@/lib/cn";
import { direction, formatDate, formatMetric, formatValue, gradeColor } from "@/lib/format";
import { DISCLAIMER_SHORT } from "@/lib/legal";
import { toggleWatch, useWatchlist } from "@/lib/recent";
import { ModeToggle } from "./explain";
import { ShareButton } from "./share-button";
import type { AnySection } from "@/lib/types";
import { STATIC_DEMO } from "@/lib/static";

function HeadlineBadge({
  label,
  children,
  tip,
}: {
  label: string;
  children: React.ReactNode;
  tip: React.ReactNode;
}) {
  return (
    <Tip content={tip}>
      <button
        type="button"
        className="min-w-0 rounded-xl border border-line bg-surface px-3.5 py-2 text-left shadow-card transition-colors hover:border-line-strong sm:min-w-[8.5rem]"
      >
        <div className="text-[11px] font-medium uppercase tracking-wider text-muted">{label}</div>
        <div className="tabular mt-1 text-[15px] font-semibold tracking-tight">{children}</div>
      </button>
    </Tip>
  );
}

export function ReportHeader({
  company,
  headline,
  headlineError,
  onRefresh,
  refreshing,
  frozen = false,
}: {
  company: AnySection | null;
  headline: AnySection | null;
  headlineError?: string | null;
  onRefresh?: () => void;
  refreshing: boolean;
  frozen?: boolean;
}) {
  const ticker = company?.identity?.ticker as string | undefined;
  const [watchlist] = useWatchlist();
  const watched = !!ticker && watchlist.includes(ticker);

  if (!company) {
    return (
      <div className="space-y-2 py-3">
        <Skeleton className="h-6 w-64" />
        <Skeleton className="h-8 w-96 max-w-full" />
      </div>
    );
  }
  const id = company.identity;
  const price = company.price.price;
  const chg = company.price.change;
  const chgPct = company.price.change_pct;
  const dir = direction(chgPct?.value);
  const trust = headline?.trust;
  const target = headline?.target;
  const conf = headline?.confidence;
  const cons = headline?.consensus;
  // Once the headline section has loaded, a null item means "not available" (never a spinner forever).
  const pending = headlineError || headline ? <span className="text-muted">Not available</span> : null;

  return (
    <div className="pt-5 pb-3">
      <div className="flex flex-wrap items-end gap-x-6 gap-y-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate text-2xl font-semibold tracking-tight sm:text-[28px]">{id.name}</h1>
            {company.synthetic && <Badge tone="synthetic">Synthetic test company</Badge>}
            {frozen && <Badge tone="warning">Frozen snapshot</Badge>}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-muted">
            <span className="rounded-md bg-surface-2 px-1.5 py-0.5 font-mono font-semibold text-ink-2">
              {id.ticker}
            </span>
            <span>{id.exchange}</span>
            <span aria-hidden>·</span>
            <Tip
              content={
                <div className="space-y-1">
                  <p>{id.sector_note}</p>
                  <p>
                    SIC {id.sic}: {id.sic_description}
                  </p>
                  {id.profile_reason && <p>Analysis profile: {id.profile_reason}.</p>}
                </div>
              }
            >
              <button type="button" className="underline decoration-dotted underline-offset-2">
                {id.sector_label} · {id.profile_label} profile
              </button>
            </Tip>
          </div>
        </div>
        <div className="flex items-baseline gap-2">
          <MetricTip m={price}>
            <button type="button" className="tabular text-3xl font-semibold tracking-tight">
              {formatMetric(price)}
            </button>
          </MetricTip>
          <span
            className={cn(
              "tabular rounded-full px-2 py-0.5 text-sm font-medium",
              dir === "up" && "bg-good/12 text-good-ink",
              dir === "down" && "bg-critical/12 text-critical-ink",
              dir === "flat" && "bg-surface-2 text-muted",
            )}
          >
            {formatMetric(chg, { signed: true })} ({formatMetric(chgPct, { signed: true, digits: 2 })})
          </span>
          <span className="text-xs text-muted">{price.note ?? `as of ${formatDate(price.as_of)}`}</span>
        </div>
        <div className="no-print ml-auto flex flex-wrap items-center gap-1.5">
          <ModeToggle />
          <Button onClick={() => ticker && toggleWatch(ticker)} aria-pressed={watched}>
            {watched ? <BookmarkCheck className="size-3.5" /> : <Bookmark className="size-3.5" />}
            {watched ? "Watching" : "Watch"}
          </Button>
          {onRefresh && (
            <Button onClick={onRefresh} disabled={refreshing} aria-label="Refresh data">
              <RefreshCw className={cn("size-3.5", refreshing && "animate-spin")} />
              <span className="hidden sm:inline">Refresh</span>
            </Button>
          )}
          {!frozen && !STATIC_DEMO && ticker && <ShareButton ticker={ticker} />}
          <Button onClick={() => window.print()} aria-label="Export PDF via print dialog">
            <Printer className="size-3.5" />
            <span className="hidden sm:inline">PDF</span>
          </Button>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-stretch sm:gap-2.5">
        <HeadlineBadge
          label="Trust Rating"
          tip={trust ? <p>{trust.explain}</p> : <p>Computing the app&apos;s Trust Rating…</p>}
        >
          {trust ? (
            trust.score === null ? (
              <span className="text-muted">Insufficient data</span>
            ) : (
              <span>
                {formatValue(trust.score, "score")}
                <span className="text-muted">/100</span>{" "}
                <span className={gradeColor(trust.grade)}>{trust.grade}</span>
              </span>
            )
          ) : (
            (pending ?? <Skeleton className="h-4 w-16" />)
          )}
        </HeadlineBadge>
        <HeadlineBadge
          label="App 12-mo target"
          tip={
            target ? (
              <div className="space-y-1">
                <p>{target.explain}</p>
                <p className="text-muted">{DISCLAIMER_SHORT}</p>
              </div>
            ) : (
              <p>Computing the app&apos;s 12-month range…</p>
            )
          }
        >
          {target ? (
            target.p50 === null ? (
              <span className="text-muted">Insufficient data</span>
            ) : (
              <span>
                {formatValue(target.p50, "usd_per_share")}{" "}
                <span className="text-xs font-normal text-muted">
                  ({formatValue(target.p10, "usd_per_share")}–{formatValue(target.p90, "usd_per_share")}){" "}
                  {formatValue(target.implied_return, "pct", { signed: true })}
                </span>
              </span>
            )
          ) : (
            (pending ?? <Skeleton className="h-4 w-24" />)
          )}
        </HeadlineBadge>
        <HeadlineBadge label="Confidence" tip={conf ? <p>{conf.explain}</p> : <p>Computing confidence…</p>}>
          {conf ? (
            conf.score === null ? (
              <span className="text-muted">—</span>
            ) : (
              <span>
                {formatValue(conf.score, "score")} · {conf.level}
              </span>
            )
          ) : (
            (pending ?? <Skeleton className="h-4 w-16" />)
          )}
        </HeadlineBadge>
        <HeadlineBadge
          label="Analyst consensus"
          tip={cons ? <p>{cons.explain}</p> : <p>Loading analyst data…</p>}
        >
          {cons ? (
            <span className="text-xs">
              All {formatValue(cons.all, "usd_per_share")} · Trusted{" "}
              {formatValue(cons.trusted, "usd_per_share")}
            </span>
          ) : (
            (pending ?? <Skeleton className="h-4 w-24" />)
          )}
        </HeadlineBadge>
      </div>
    </div>
  );
}
