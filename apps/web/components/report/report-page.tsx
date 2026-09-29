"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { PriceChart } from "@/components/charts/price-chart";
import { MissingNote, SectionShell } from "@/components/report/section-shell";
import { getJSON, type SectionState, useSection } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { DISCLAIMER_SHORT } from "@/lib/legal";
import { pushRecent } from "@/lib/recent";
import type { AnySection } from "@/lib/types";
import { AnalystsSection } from "./analysts";
import { CapitalSection } from "./capital";
import { DividendsSection } from "./dividends";
import { EarningsSection } from "./earnings";
import { ExplainSection, ModeToggle, VerdictCard } from "./explain";
import { FundamentalsSection } from "./fundamentals";
import { NewsSection } from "./news";
import { ReportHeader } from "./header";
import { SnapshotStats } from "./overview";
import { OverviewSection } from "./overview-section";
import { OwnershipSection } from "./ownership";
import { PeersSection } from "./peers";
import { QuantSection } from "./quant";
import { RiskSection } from "./risk";
import { TrustSection } from "./trust";
import { ValuationSection } from "./valuation";
import { CAN_COMPUTE } from "@/lib/static";

const NAV = [
  { id: "snapshot", label: "Snapshot" },
  { id: "overview", label: "Overview" },
  { id: "chart", label: "Chart" },
  { id: "trust", label: "Trust Rating" },
  { id: "valuation", label: "Price target" },
  { id: "explain", label: "Explain" },
  { id: "analysts", label: "Analysts" },
  { id: "news", label: "News" },
  { id: "earnings", label: "Earnings" },
  { id: "dividends", label: "Dividends" },
  { id: "ownership", label: "Ownership" },
  { id: "capital", label: "Capital allocation" },
  { id: "fundamentals", label: "Fundamentals" },
  { id: "risk", label: "Risk & red flags" },
  { id: "quant", label: "Quant" },
  { id: "peers", label: "Peers" },
];

/** A report frozen at a point in time (shared snapshot links): sections are supplied, nothing is fetched. */
export interface FrozenReport {
  sections: Record<string, AnySection>;
  generated_at?: string;
  engine_version?: string;
  config_hash?: string;
}

function pick(state: SectionState, frozen: FrozenReport | undefined, name: string): SectionState {
  if (!frozen) return state;
  const data = frozen.sections[name] ?? null;
  return {
    data,
    loading: false,
    error: data ? null : "This section is not part of the snapshot.",
    notFound: false,
  };
}

export function ReportPage({ ticker, frozen }: { ticker: string; frozen?: FrozenReport }) {
  const [version, setVersion] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const src = frozen ? "" : ticker; // an empty ticker disables fetching
  const company = pick(useSection(src, "company", version), frozen, "company");
  const chart = pick(useSection(src, "chart", version), frozen, "chart");
  const overview = pick(useSection(src, "overview", version), frozen, "overview");
  const headline = pick(useSection(src, "headline", version), frozen, "headline");
  const trust = pick(useSection(src, "trust", version), frozen, "trust");
  const valuation = pick(useSection(src, "valuation", version), frozen, "valuation");
  const analysts = pick(useSection(src, "analysts", version), frozen, "analysts");
  const news = pick(useSection(src, "news", version), frozen, "news");
  const earnings = pick(useSection(src, "earnings", version), frozen, "earnings");
  const dividends = pick(useSection(src, "dividends", version), frozen, "dividends");
  const ownership = pick(useSection(src, "ownership", version), frozen, "ownership");
  const capital = pick(useSection(src, "capital", version), frozen, "capital");
  const risk = pick(useSection(src, "risk", version), frozen, "risk");
  const quant = pick(useSection(src, "quant", version), frozen, "quant");
  const fundamentals = pick(useSection(src, "fundamentals", version), frozen, "fundamentals");
  const explain = pick(useSection(src, "explain", version), frozen, "explain");
  const [peerOverride, setPeerOverride] = useState<string[] | null>(null);
  const peers = pick(
    useSection(
      src,
      "peers",
      version,
      peerOverride ? `peers=${encodeURIComponent(peerOverride.join(","))}` : "",
    ),
    frozen,
    "peers",
  );

  const high52 = company.data?.stats?.high_52w?.value;
  const low52 = company.data?.stats?.low_52w?.value;
  const cone = valuation.data?.cone;
  const consAll = analysts.data?.consensus_all;
  const consTrusted = analysts.data?.consensus_trusted;
  const chartTargets = analysts.data?.chart_targets;
  const newsMarkers = news.data?.markers;
  const overlays = useMemo(
    () => ({
      high52,
      low52,
      cone: cone ?? null,
      consensus: consAll || consTrusted ? { all: consAll, trusted: consTrusted } : null,
      analystTargets: chartTargets ?? [],
      events: newsMarkers ?? [],
    }),
    [high52, low52, cone, consAll, consTrusted, chartTargets, newsMarkers],
  );

  useEffect(() => {
    if (company.data && !frozen) pushRecent(company.data.identity.ticker);
  }, [company.data, frozen]);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await getJSON(`/report/${encodeURIComponent(ticker)}/refresh`, { method: "POST" });
    } finally {
      setVersion((v) => v + 1);
      setRefreshing(false);
    }
  }, [ticker]);

  if (company.notFound) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16">
        <h1 className="text-xl font-semibold">Ticker not found</h1>
        <p className="mt-2 text-ink-2">{company.error}</p>
        <Link href="/" className="mt-4 inline-block text-accent-ink underline">
          Back to search
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-4">
      <div className="z-30 -mx-4 border-b border-line bg-page/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-page/80 sm:sticky sm:top-0 print:static print:bg-transparent print:backdrop-blur-none">
        <p className="hidden pt-2 text-[10px] text-muted print:block">
          {frozen ? "Snapshot of the report" : "Report"} generated{" "}
          {formatDateTime(company.data?.generated_at)} · {DISCLAIMER_SHORT}
        </p>
        <ReportHeader
          company={company.data}
          headline={headline.data}
          headlineError={headline.error}
          onRefresh={frozen || !CAN_COMPUTE ? undefined : refresh}
          refreshing={refreshing}
          frozen={!!frozen}
        />
        <nav aria-label="Report sections" className="no-print -mx-1 flex gap-1 overflow-x-auto pb-2">
          {NAV.map((n) => (
            <a
              key={n.id}
              href={`#${n.id}`}
              className="whitespace-nowrap rounded-md px-2 py-1 text-xs font-medium text-ink-2 hover:bg-surface-2"
            >
              {n.label}
            </a>
          ))}
        </nav>
      </div>

      <div className="mt-4 space-y-4">
        {company.error && !company.data && <MissingNote>{company.error}</MissingNote>}
        {company.data && <VerdictCard e={explain.data} loading={explain.loading} error={explain.error} />}
        <SectionShell
          id="snapshot"
          title="Snapshot"
          subtitle="Key statistics"
          data={company.data}
          loading={company.loading}
          error={company.error}
        >
          {company.data && (
            <SnapshotStats company={company.data} nextEarnings={earnings.data?.metrics?.next_date ?? null} />
          )}
        </SectionShell>
        <SectionShell
          id="overview"
          title="Company overview"
          data={overview.data}
          loading={overview.loading}
          error={overview.error}
        >
          {overview.data && <OverviewSection o={overview.data} />}
        </SectionShell>
        <SectionShell
          id="chart"
          title="Price chart"
          data={chart.data}
          loading={chart.loading}
          error={chart.error}
          skeletonHeight="h-96"
        >
          {chart.data && <PriceChart chart={chart.data} ticker={ticker.toUpperCase()} overlays={overlays} />}
        </SectionShell>
        <SectionShell
          id="trust"
          title="Trust Rating"
          subtitle="The app's own rating of business strength, reliability and valuation relative to the sector"
          data={trust.data}
          loading={trust.loading}
          error={trust.error}
          skeletonHeight="h-80"
        >
          {trust.data && <TrustSection t={trust.data} />}
        </SectionShell>
        <SectionShell
          id="valuation"
          title="Price target & valuation"
          subtitle="The app's 12-month model estimate, its range, and the valuation methods behind it"
          data={valuation.data}
          loading={valuation.loading}
          error={valuation.error}
          skeletonHeight="h-96"
        >
          {valuation.data && (
            <ValuationSection
              v={valuation.data}
              ticker={ticker}
              profile={company.data?.identity?.profile ?? "general"}
              consensus={
                analysts.data
                  ? { all: analysts.data.consensus_all, trusted: analysts.data.consensus_trusted }
                  : undefined
              }
            />
          )}
        </SectionShell>
        <SectionShell
          id="explain"
          title="Explain: how the app reached this view"
          subtitle="Every number below comes from the report's facts; hover or tap a sentence to see which"
          data={explain.data}
          loading={explain.loading}
          error={explain.error}
          skeletonHeight="h-96"
          actions={<ModeToggle />}
        >
          {explain.data && <ExplainSection e={explain.data} />}
        </SectionShell>
        <SectionShell
          id="analysts"
          title="Wall Street analysts: who to trust"
          subtitle="Analysts' own targets and ratings, scored on how their past calls worked out"
          data={analysts.data}
          loading={analysts.loading}
          error={analysts.error}
          skeletonHeight="h-96"
        >
          {analysts.data && <AnalystsSection a={analysts.data} appTarget={valuation.data?.target?.p50} />}
        </SectionShell>
        <SectionShell
          id="news"
          title="News and sentiment"
          subtitle="Deduplicated stories, their tone and importance, and what changed recently"
          data={news.data}
          loading={news.loading}
          error={news.error}
          skeletonHeight="h-96"
        >
          {news.data && <NewsSection n={news.data} />}
        </SectionShell>
        <SectionShell
          id="earnings"
          title="Earnings"
          subtitle="Results against estimates, how the stock reacted, and what comes next"
          data={earnings.data}
          loading={earnings.loading}
          error={earnings.error}
        >
          {earnings.data && <EarningsSection e={earnings.data} />}
        </SectionShell>
        <SectionShell
          id="dividends"
          title="Dividends"
          data={dividends.data}
          loading={dividends.loading}
          error={dividends.error}
        >
          {dividends.data && <DividendsSection d={dividends.data} />}
        </SectionShell>
        <SectionShell
          id="ownership"
          title="Ownership, insiders and short interest"
          data={ownership.data}
          loading={ownership.loading}
          error={ownership.error}
        >
          {ownership.data && <OwnershipSection o={ownership.data} />}
        </SectionShell>
        <SectionShell
          id="capital"
          title="Capital allocation"
          subtitle="Returns on new investment, buyback timing, dilution, payouts and dividends: how management used the cash"
          data={capital.data}
          loading={capital.loading}
          error={capital.error}
        >
          {capital.data && <CapitalSection c={capital.data} />}
        </SectionShell>
        <SectionShell
          id="fundamentals"
          title="Fundamentals"
          subtitle="Statements, ratios, growth, quality and sector KPIs from SEC filings"
          data={fundamentals.data}
          loading={fundamentals.loading}
          error={fundamentals.error}
          skeletonHeight="h-72"
        >
          {fundamentals.data && <FundamentalsSection f={fundamentals.data} />}
        </SectionShell>
        <SectionShell
          id="risk"
          title="Risk & red flags"
          data={risk.data}
          loading={risk.loading}
          error={risk.error}
        >
          {risk.data && <RiskSection r={risk.data} />}
        </SectionShell>
        <SectionShell
          id="quant"
          title="Quantitative views"
          subtitle="Factor exposures, macro sensitivity and month-of-year patterns, with their statistical reliability"
          data={quant.data}
          loading={quant.loading}
          error={quant.error}
        >
          {quant.data && <QuantSection q={quant.data} />}
        </SectionShell>
        <SectionShell id="peers" title="Peers" data={peers.data} loading={peers.loading} error={peers.error}>
          {peers.data && (
            <PeersSection key={peerOverride?.join(",") ?? "auto"} p={peers.data} onPeers={setPeerOverride} />
          )}
        </SectionShell>
        <p className="text-xs text-muted">
          {DISCLAIMER_SHORT} Report generated {formatDateTime(company.data?.generated_at)} · engine{" "}
          {company.data?.engine_version} · config {company.data?.config_hash}
        </p>
      </div>
    </div>
  );
}
