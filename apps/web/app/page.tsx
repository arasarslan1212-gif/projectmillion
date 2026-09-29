"use client";

import { BadgeCheck, Gauge, Scale, Sparkles, Users } from "lucide-react";
import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import { TickerSearch } from "@/components/ticker-search";
import { search, useHealth } from "@/lib/api";
import { STATIC_DEMO } from "@/lib/static";
import { useRecent, useWatchlist } from "@/lib/recent";

const REAL_EXAMPLES = ["AAPL", "MSFT", "NVDA", "JPM", "O", "NEE"];
const SYNTHETIC_EXAMPLES = ["ZZTEC", "ZZBNK", "ZZREI", "ZZGRO", "ZZUTL", "ZZSML"];

const FEATURES: { icon: ReactNode; title: string; body: string }[] = [
  {
    icon: <BadgeCheck className="size-4" />,
    title: "Trust Rating",
    body: "Nine pillars scored against the company's own sector, from balance sheet to earnings quality.",
  },
  {
    icon: <Scale className="size-4" />,
    title: "12-month range",
    body: "A blended valuation with P10–P90 bounds and a confidence level the app grades itself on.",
  },
  {
    icon: <Users className="size-4" />,
    title: "Analysts, weighted",
    body: "Wall Street targets weighted by each analyst's measured track record, not by volume.",
  },
  {
    icon: <Gauge className="size-4" />,
    title: "Explain everything",
    body: "Every conclusion traces to a number, and every number to its source and formula.",
  },
];

function TickerChips({ title, tickers, empty }: { title: string; tickers: string[]; empty: string }) {
  return (
    <section
      aria-labelledby={`h-${title}`}
      className="rounded-2xl border border-line bg-surface p-5 shadow-card"
    >
      <h2 id={`h-${title}`} className="text-sm font-semibold tracking-tight">
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
                className="inline-block rounded-lg border border-line bg-surface px-2.5 py-1 font-mono text-[13px] font-semibold text-ink-2 transition-colors hover:border-line-strong hover:text-ink"
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

/** On the static site, the stocks it carries; otherwise a fixed set of examples. */
function useExamples(synthetic: boolean | undefined): string[] {
  const [site, setSite] = useState<string[] | null>(null);
  useEffect(() => {
    if (!STATIC_DEMO) return;
    search("")
      .then((r) => setSite(r.results.slice(0, 8).map((x) => x.ticker)))
      .catch(() => setSite(null));
  }, []);
  return site ?? (synthetic ? SYNTHETIC_EXAMPLES : REAL_EXAMPLES);
}

export default function Home() {
  const health = useHealth();
  const recent = useRecent();
  const [watch] = useWatchlist();
  const examples = useExamples(health?.synthetic);
  return (
    <div className="relative overflow-hidden">
      <div className="hero-glow pointer-events-none absolute inset-x-0 top-0 h-[480px]" aria-hidden />
      <div className="relative mx-auto max-w-5xl px-4 pt-14 pb-16 sm:pt-20">
        <div className="mx-auto max-w-3xl text-center">
          <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1 text-xs font-medium text-ink-2 shadow-card">
            <Sparkles className="size-3.5 text-accent-ink" aria-hidden />
            Explainable stock research
          </span>
          <h1 className="mt-5 text-4xl font-semibold tracking-tight text-balance sm:text-6xl">
            Research any US stock,{" "}
            <span className="bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent dark:from-indigo-300 dark:to-violet-300">
              honestly.
            </span>
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-base text-pretty text-ink-2 sm:text-lg">
            One page per company: fundamentals, the app&apos;s own rating and 12-month range with its
            confidence, analysts weighted by their track records, news, risks, and the reasoning behind every
            number.
          </p>
          <div className="mx-auto mt-9 max-w-2xl">
            <TickerSearch autoFocus />
          </div>
          <div className="mt-4 flex flex-wrap items-center justify-center gap-1.5 text-xs text-muted">
            <span>{health?.synthetic ? "Synthetic test companies:" : "Try:"}</span>
            {examples.map((t) => (
              <Link
                key={t}
                href={`/stock/${t}`}
                className="rounded-full border border-line bg-surface px-2.5 py-0.5 font-mono font-semibold text-ink-2 transition-colors hover:border-line-strong hover:text-ink"
              >
                {t}
              </Link>
            ))}
          </div>
        </div>

        <ul className="mt-16 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((f) => (
            <li key={f.title} className="rounded-2xl border border-line bg-surface p-5 shadow-card">
              <span className="inline-flex size-8 items-center justify-center rounded-lg bg-accent-wash text-accent-ink">
                {f.icon}
              </span>
              <h2 className="mt-3 text-sm font-semibold tracking-tight">{f.title}</h2>
              <p className="mt-1 text-sm leading-relaxed text-ink-2">{f.body}</p>
            </li>
          ))}
        </ul>

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <TickerChips title="Recently viewed" tickers={recent} empty="Reports you open appear here." />
          <TickerChips title="Watchlist" tickers={watch} empty="Add a stock from its report page." />
        </div>
        {health && (
          <p className="mt-8 text-center text-xs text-muted">
            Data tier <span className="font-medium text-ink-2">{health.data_tier}</span> · {health.data_mode}
            {health.fixture_set ? ` (${health.fixture_set} data)` : ""} · narratives:{" "}
            {health.llm_enabled ? "LLM with fact validation" : "templates"} · data as of {health.today}
          </p>
        )}
      </div>
    </div>
  );
}
