"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { PriceChart } from "@/components/charts/price-chart";
import { MissingNote, SectionShell } from "@/components/report/section-shell";
import { getJSON, useSection } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { DISCLAIMER_SHORT } from "@/lib/legal";
import { pushRecent } from "@/lib/recent";
import { AnalystsSection } from "./analysts";
import { FundamentalsSection } from "./fundamentals";
import { ReportHeader } from "./header";
import { SnapshotStats } from "./overview";
import { OverviewSection } from "./overview-section";
import { PeersSection } from "./peers";
import { RiskSection } from "./risk";
import { TrustSection } from "./trust";
import { ValuationSection } from "./valuation";

const NAV = [
  { id: "snapshot", label: "Snapshot" },
  { id: "overview", label: "Overview" },
  { id: "chart", label: "Chart" },
  { id: "trust", label: "Trust Rating" },
  { id: "valuation", label: "Price target" },
  { id: "analysts", label: "Analysts" },
  { id: "fundamentals", label: "Fundamentals" },
  { id: "risk", label: "Risk & red flags" },
  { id: "peers", label: "Peers" },
];

export function ReportPage({ ticker }: { ticker: string }) {
  const [version, setVersion] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const company = useSection(ticker, "company", version);
  const chart = useSection(ticker, "chart", version);
  const overview = useSection(ticker, "overview", version);
  const headline = useSection(ticker, "headline", version);
  const trust = useSection(ticker, "trust", version);
  const valuation = useSection(ticker, "valuation", version);
  const analysts = useSection(ticker, "analysts", version);
  const risk = useSection(ticker, "risk", version);
  const fundamentals = useSection(ticker, "fundamentals", version);
  const [peerOverride, setPeerOverride] = useState<string[] | null>(null);
  const peers = useSection(
    ticker,
    "peers",
    version,
    peerOverride ? `peers=${encodeURIComponent(peerOverride.join(","))}` : "",
  );

  const high52 = company.data?.stats?.high_52w?.value;
  const low52 = company.data?.stats?.low_52w?.value;
  const cone = valuation.data?.cone;
  const consAll = analysts.data?.consensus_all;
  const consTrusted = analysts.data?.consensus_trusted;
  const chartTargets = analysts.data?.chart_targets;
  const overlays = useMemo(
    () => ({
      high52,
      low52,
      cone: cone ?? null,
      consensus: consAll || consTrusted ? { all: consAll, trusted: consTrusted } : null,
      analystTargets: chartTargets ?? [],
    }),
    [high52, low52, cone, consAll, consTrusted, chartTargets],
  );

  useEffect(() => {
    if (company.data) pushRecent(company.data.identity.ticker);
  }, [company.data]);

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
      <div className="sticky top-0 z-30 -mx-4 border-b border-line bg-page/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-page/80">
        <ReportHeader
          company={company.data}
          headline={headline.data}
          headlineError={headline.error}
          onRefresh={refresh}
          refreshing={refreshing}
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
        <SectionShell
          id="snapshot"
          title="Snapshot"
          subtitle="Key statistics"
          data={company.data}
          loading={company.loading}
          error={company.error}
        >
          {company.data && <SnapshotStats company={company.data} />}
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
