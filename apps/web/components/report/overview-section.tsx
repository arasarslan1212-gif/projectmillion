"use client";

import Link from "next/link";
import { MetricCell } from "@/components/ui/metric";
import { formatDate, formatValue } from "@/lib/format";
import type { AnySection, Metric } from "@/lib/types";

function MixBar({ title, block }: { title: string; block: AnySection | null }) {
  if (!block) return null;
  const items: { name: string; value: number; share: number | null }[] = block.items.slice(0, 6);
  const other = block.items.slice(6).reduce((a: number, x: AnySection) => a + (x.share ?? 0), 0);
  const colors = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)", "var(--s5)", "var(--s6)"];
  return (
    <div>
      <div className="flex items-baseline justify-between text-xs">
        <span className="font-semibold text-ink-2">{title}</span>
        <span className="text-muted">
          FY{block.fiscal_year} · {block.source}
        </span>
      </div>
      <div
        className="mt-2 flex h-3 w-full gap-[2px] overflow-hidden rounded"
        role="img"
        aria-label={`${title}: ${items.map((i) => `${i.name} ${Math.round((i.share ?? 0) * 100)}%`).join(", ")}`}
      >
        {items.map((it, i) => (
          <div
            key={it.name}
            style={{ width: `${(it.share ?? 0) * 100}%`, background: colors[i] }}
            title={`${it.name}: ${formatValue(it.share, "pct")}`}
          />
        ))}
        {other > 0 && (
          <div
            style={{ width: `${other * 100}%`, background: "var(--axis)" }}
            title={`Other: ${formatValue(other, "pct")}`}
          />
        )}
      </div>
      <ul className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-3">
        {items.map((it, i) => (
          <li key={it.name} className="flex items-center gap-1.5">
            <span
              className="inline-block size-2.5 shrink-0 rounded-sm"
              style={{ background: colors[i] }}
              aria-hidden
            />
            <span className="truncate text-ink-2">{it.name}</span>
            <span className="tabular ml-auto text-ink">{formatValue(it.share, "pct", { digits: 0 })}</span>
          </li>
        ))}
        {other > 0 && (
          <li className="flex items-center gap-1.5">
            <span className="inline-block size-2.5 rounded-sm bg-axis" aria-hidden />
            <span className="text-ink-2">Other</span>
            <span className="tabular ml-auto">{formatValue(other, "pct", { digits: 0 })}</span>
          </li>
        )}
      </ul>
    </div>
  );
}

export function OverviewSection({ o }: { o: AnySection }) {
  return (
    <div className="space-y-5">
      <div>
        <p className="max-w-3xl text-sm leading-relaxed text-ink">{o.description}</p>
        <p className="mt-1 text-xs text-muted">{o.description_note}</p>
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <div>
          <h3 className="mb-2 text-xs font-semibold text-ink-2">Company facts</h3>
          <div className="grid grid-cols-2 gap-x-4 gap-y-3">
            {(o.facts as Metric[]).map((m) => (
              <MetricCell key={m.id} m={m} />
            ))}
          </div>
        </div>
        <div>
          <h3 className="mb-2 text-xs font-semibold text-ink-2">Share structure</h3>
          <div className="grid grid-cols-2 gap-x-4 gap-y-3">
            {(o.share_structure as Metric[]).map((m) => (
              <MetricCell key={m.id} m={m} />
            ))}
          </div>
        </div>
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        {o.segments.product || o.segments.geography ? (
          <>
            <MixBar title="Revenue by segment" block={o.segments.product} />
            <MixBar title="Revenue by geography" block={o.segments.geography} />
          </>
        ) : (
          <p className="text-xs text-muted">Revenue mix unavailable: {o.segments_reason}.</p>
        )}
      </div>
      <div>
        <h3 className="mb-2 text-xs font-semibold text-ink-2">Market position</h3>
        {o.market_position.products.length > 0 && (
          <p className="text-sm">
            <span className="text-muted">Key product lines: </span>
            {o.market_position.products.join(", ")}
          </p>
        )}
        {o.market_position.products_note && (
          <p className="text-xs text-muted">{o.market_position.products_note}</p>
        )}
        <div className="mt-2 flex flex-wrap items-center gap-1.5 text-sm">
          <span className="text-muted">Main competitors:</span>
          {o.market_position.competitors.length ? (
            o.market_position.competitors.map((c: AnySection) => (
              <Link
                key={c.ticker}
                href={`/stock/${c.ticker}`}
                className="rounded border border-line px-1.5 py-0.5 text-xs hover:bg-surface-2"
                title={c.name}
              >
                {c.ticker}
              </Link>
            ))
          ) : (
            <span className="text-xs text-muted">none identified</span>
          )}
        </div>
        {o.market_position.competitors_note && (
          <p className="mt-1 text-xs text-muted">{o.market_position.competitors_note}</p>
        )}
      </div>
      {o.recent_filings?.length > 0 && (
        <div>
          <h3 className="mb-1 text-xs font-semibold text-ink-2">Recent 8-K filings</h3>
          <ul className="space-y-0.5 text-xs">
            {o.recent_filings.map((f: AnySection) => (
              <li key={f.url ?? f.date}>
                <a className="text-accent-ink underline" href={f.url ?? "#"} target="_blank" rel="noreferrer">
                  {formatDate(f.date)}
                </a>{" "}
                <span className="text-muted">items {f.items.join(", ") || "—"}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
