"use client";

import { CheckCircle2, Clock, Snowflake, XCircle } from "lucide-react";
import Link from "next/link";
import { ReportPage } from "@/components/report/report-page";
import { Skeleton } from "@/components/ui/skeleton";
import { useJSON } from "@/lib/api";
import { formatDate, formatDateTime, formatValue } from "@/lib/format";
import type { AnySection } from "@/lib/types";

export function SnapshotView({ token }: { token: string }) {
  const { data, error } = useJSON<AnySection>(`/snapshot/${encodeURIComponent(token)}`);
  if (error && !data)
    return (
      <div className="mx-auto max-w-3xl px-4 py-16">
        <h1 className="text-xl font-semibold">Snapshot not found</h1>
        <p className="mt-2 text-ink-2">{error}</p>
        <Link href="/" className="mt-4 inline-block text-accent-ink underline">
          Back to search
        </Link>
      </div>
    );
  if (!data)
    return (
      <div className="mx-auto max-w-7xl space-y-3 px-4 py-6" aria-busy="true">
        <Skeleton className="h-10 w-80" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  const r = data.report;
  const t = data.target;
  const o = data.outcome;
  return (
    <div>
      <div className="mx-auto max-w-7xl px-4 pt-4">
        <div className="rounded-lg border border-warning/40 bg-warning/10 px-3 py-2 text-sm">
          <p className="flex flex-wrap items-center gap-x-2 font-medium text-ink">
            <Snowflake className="size-4 text-warning-ink" aria-hidden />
            Frozen snapshot of the {data.ticker} report from {formatDate(data.as_of)}
            <Link
              href={`/stock/${encodeURIComponent(String(data.ticker))}`}
              className="ml-auto text-xs text-accent-ink underline"
            >
              Open the live report
            </Link>
          </p>
          <p className="mt-0.5 text-xs text-ink-2">
            Every number is as the app computed it when the snapshot was taken (
            {formatDateTime(data.created_at)}, engine {data.engine_version}, config {data.config_hash});
            nothing on this page updates.
          </p>
          {t?.p50 != null && (
            <p className="mt-1 flex items-center gap-1.5 text-xs">
              {o ? (
                o.in_band ? (
                  <CheckCircle2 className="size-3.5 text-good-ink" aria-hidden />
                ) : (
                  <XCircle className="size-3.5 text-critical-ink" aria-hidden />
                )
              ) : (
                <Clock className="size-3.5 text-muted" aria-hidden />
              )}
              {o
                ? `Graded ${formatDate(o.horizon_date)}: the price was ${formatValue(o.realized_price, "usd_per_share")}, ${o.in_band ? "inside" : "outside"} the app's 80% range of ${formatValue(t.p10, "usd_per_share")}–${formatValue(t.p90, "usd_per_share")} (P50 ${formatValue(t.p50, "usd_per_share")}).`
                : `The app's estimate (P50 ${formatValue(t.p50, "usd_per_share")}, range ${formatValue(t.p10, "usd_per_share")}–${formatValue(t.p90, "usd_per_share")}) will be graded on ${formatDate(data.due)} and shown here and on the track record.`}
            </p>
          )}
        </div>
      </div>
      <ReportPage
        ticker={String(data.ticker)}
        frozen={{
          sections: r.sections,
          generated_at: r.generated_at,
          engine_version: r.engine_version,
          config_hash: r.config_hash,
        }}
      />
    </div>
  );
}
