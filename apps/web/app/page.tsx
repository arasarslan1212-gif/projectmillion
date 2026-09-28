"use client";

import Link from "next/link";
import { TickerSearch } from "@/components/ticker-search";
import { useHealth } from "@/lib/api";
import { useRecent, useWatchlist } from "@/lib/recent";

const REAL_EXAMPLES = ["AAPL", "JPM", "O", "NEE", "MSFT", "KO"];
const SYNTHETIC_EXAMPLES = ["ZZTEC", "ZZBNK", "ZZREI", "ZZGRO", "ZZUTL", "ZZSML"];

function TickerChips({ title, tickers, empty }: { title: string; tickers: string[]; empty: string }) {
  return (
    <section aria-labelledby={`h-${title}`} className="rounded-xl border border-line bg-surface p-4">
      <h2 id={`h-${title}`} className="text-sm font-semibold">
        {title}
      </h2>
      {tickers.length === 0 ? (
        <p className="mt-2 text-sm text-muted">{empty}</p>
      ) : (
        <ul className="mt-3 flex flex-wrap gap-2">
          {tickers.map((t) => (
            <li key={t}>
              <Link
                href={`/stock/${t}`}
                className="inline-block rounded-md border border-line px-2.5 py-1 text-sm font-medium hover:bg-surface-2"
              >
                {t}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export default function Home() {
  const health = useHealth();
  const recent = useRecent();
  const [watch] = useWatchlist();
  const examples = health?.synthetic ? SYNTHETIC_EXAMPLES : REAL_EXAMPLES;
  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:py-16">
      <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Research any US-listed stock</h1>
      <p className="mt-2 max-w-2xl text-ink-2">
        One page per company: fundamentals, the app&apos;s own rating and 12-month range with its confidence,
        analysts weighted by their track records, news, risks, and the full reasoning behind every number.
      </p>
      <div className="mt-6">
        <TickerSearch autoFocus />
      </div>
      <div className="mt-8 grid gap-4 sm:grid-cols-2">
        <TickerChips title="Recently viewed" tickers={recent} empty="Reports you open appear here." />
        <TickerChips title="Watchlist" tickers={watch} empty="Add a stock from its report page." />
      </div>
      <div className="mt-4">
        <TickerChips
          title={health?.synthetic ? "Synthetic test companies" : "Examples"}
          tickers={examples}
          empty=""
        />
      </div>
      {health && (
        <p className="mt-6 text-xs text-muted">
          Data tier: <span className="font-medium text-ink-2">{health.data_tier}</span> · mode{" "}
          {health.data_mode}
          {health.fixture_set ? ` (${health.fixture_set} fixtures)` : ""} · narratives:{" "}
          {health.llm_enabled ? "LLM with fact validation" : "templates (no LLM key configured)"} · data as of{" "}
          {health.today}
        </p>
      )}
    </div>
  );
}
