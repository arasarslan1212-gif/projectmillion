"use client";

import { MetricCell } from "@/components/ui/metric";
import type { AnySection, Metric } from "@/lib/types";

export function SnapshotStats({
  company,
  nextEarnings,
}: {
  company: AnySection;
  nextEarnings?: Metric | null;
}) {
  const s = company.stats;
  const cells = [
    s.market_cap,
    s.enterprise_value,
    s.pe,
    s.ev_ebitda,
    s.dividend_yield,
    s.beta,
    s.low_52w,
    s.high_52w,
    s.volume,
    s.avg_volume,
    s.volume_ratio,
    s.shares_outstanding,
    nextEarnings ?? null,
  ];
  return (
    <div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-3 lg:grid-cols-7">
        {cells.map((m) => (m ? <MetricCell key={m.id} m={m} /> : null))}
      </div>
      <RangeBar low={s.low_52w?.value} high={s.high_52w?.value} price={company.price.price.value} />
      <p className="mt-2 text-xs text-muted">Fundamentals: {company.ttm_note}.</p>
    </div>
  );
}

export function RangeBar({
  low,
  high,
  price,
}: {
  low: number | null;
  high: number | null;
  price: number | null;
}) {
  if (low === null || high === null || price === null || high <= low) return null;
  const pos = Math.min(1, Math.max(0, (price - low) / (high - low)));
  return (
    <div className="mt-4 max-w-md">
      <div className="flex justify-between text-[11px] text-muted">
        <span>52-week low</span>
        <span>52-week high</span>
      </div>
      <div
        className="relative mt-1 h-1.5 rounded-full bg-surface-2"
        role="img"
        aria-label={`Price is at ${Math.round(pos * 100)}% of its 52-week range`}
      >
        <div
          className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface bg-accent"
          style={{ left: `${pos * 100}%` }}
        />
      </div>
    </div>
  );
}
