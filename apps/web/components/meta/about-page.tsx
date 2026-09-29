"use client";

import Link from "next/link";
import { Badge } from "@/components/ui/badge";
import { useHealth } from "@/lib/api";
import { APP_NAME, DISCLAIMER_FULL } from "@/lib/legal";

const SOURCES: { name: string; use: string; terms: string; attribution: string }[] = [
  {
    name: "SEC EDGAR",
    use: "Company list, XBRL financial statements (point-in-time, by filing date), filings, Form 4 insider trades, 13F holdings, 10-K text",
    terms:
      "U.S. government public data under the SEC fair-access policy (identified User-Agent, rate-limited).",
    attribution: "“Source: SEC EDGAR” on every figure from filings.",
  },
  {
    name: "FRED (Federal Reserve Bank of St. Louis)",
    use: "Treasury yields (risk-free rate), CPI, credit spreads, dollar and oil series",
    terms: "Free API; only public-domain series are used.",
    attribution:
      "This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis.",
  },
  {
    name: "FINRA",
    use: "Equity short interest",
    terms: "Public dataset via the FINRA Query API.",
    attribution: "“Source: FINRA” on short-interest figures.",
  },
  {
    name: "Tiingo, Finnhub, Financial Modeling Prep, Benzinga via Massive",
    use: "Prices, estimates, analyst price targets and ratings, news headlines, profiles (depending on the configured data tier)",
    terms:
      "Commercial providers. Standard plans are generally licensed for personal use; public display needs their commercial licenses.",
    attribution: "Each figure names its provider.",
  },
  {
    name: "Anthropic Claude API (optional)",
    use: "Classifying news and writing the Verdict and Explain text from the app's facts",
    terms: "The model never produces a number: every number it writes is checked against the facts it cites.",
    attribution: "Model-written text is labeled.",
  },
  {
    name: "TradingView Lightweight Charts™ and Apache ECharts",
    use: "Chart rendering",
    terms: "Apache-2.0.",
    attribution: "Link to TradingView in the footer and on the price chart.",
  },
];

export function AboutPage() {
  const h = useHealth();
  return (
    <div className="mx-auto max-w-4xl space-y-6 px-4 py-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">About {APP_NAME}</h1>
        <p className="mt-2 text-sm leading-relaxed text-ink-2">
          {APP_NAME} builds one honest, explainable research page for a US-listed stock: company data and
          fundamentals, the app&apos;s own Trust Rating and 12-month price range with a confidence level, Wall
          Street analysts weighted by how their past calls turned out, news and sentiment, risks, and an
          Explain section that traces every conclusion back to a number.
        </p>
      </div>

      <section aria-labelledby="how" className="rounded-xl border border-line bg-surface p-4 sm:p-5">
        <h2 id="how" className="text-base font-semibold">
          How it works
        </h2>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-ink-2">
          <li>
            Every number is computed by deterministic, tested code. A language model, when enabled, only
            writes words.
          </li>
          <li>
            Every weight, threshold and assumption lives in one configuration file; the{" "}
            <Link href="/methodology" className="text-accent-ink underline underline-offset-2">
              Methodology
            </Link>{" "}
            page is generated from it.
          </li>
          <li>
            Every report&apos;s estimate is stored and graded 12 months later, and the results, good or bad,
            are on the{" "}
            <Link href="/track-record" className="text-accent-ink underline underline-offset-2">
              Track record
            </Link>{" "}
            page.
          </li>
          <li>
            Missing data is shown as missing, with the reason. Nothing is filled in or estimated silently.
          </li>
        </ul>
      </section>

      <section aria-labelledby="deploy" className="rounded-xl border border-line bg-surface p-4 sm:p-5">
        <h2 id="deploy" className="text-base font-semibold">
          This deployment
        </h2>
        {!h ? (
          <p className="mt-2 text-sm text-muted">Engine status unavailable.</p>
        ) : (
          <div className="mt-2 space-y-2 text-sm">
            <p className="flex flex-wrap items-center gap-2 text-ink-2">
              Data mode <b className="text-ink">{h.data_mode}</b> · tier{" "}
              <b className="text-ink">{h.data_tier}</b> · engine {h.engine_version} · config {h.config_hash}
              {h.synthetic && <Badge tone="synthetic">Synthetic test data</Badge>}
              <Badge tone={h.llm_enabled ? "accent" : "neutral"}>
                {h.llm_enabled ? "Language model enabled" : "Template text (no language model configured)"}
              </Badge>
            </p>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-1 sm:grid-cols-2">
              {Object.entries(h.providers).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-3 border-b border-line py-1">
                  <dt className="capitalize text-ink-2">{k.replace(/_/g, " ")}</dt>
                  <dd className="text-right">{v}</dd>
                </div>
              ))}
            </dl>
          </div>
        )}
      </section>

      <section aria-labelledby="sources" className="rounded-xl border border-line bg-surface p-4 sm:p-5">
        <h2 id="sources" className="text-base font-semibold">
          Data sources and attribution
        </h2>
        <dl className="mt-2 space-y-3">
          {SOURCES.map((s) => (
            <div key={s.name} className="text-sm">
              <dt className="font-medium">{s.name}</dt>
              <dd className="text-ink-2">{s.use}.</dd>
              <dd className="text-xs text-muted">
                {s.terms} {s.attribution}
              </dd>
            </div>
          ))}
        </dl>
        <p className="mt-3 text-xs text-muted">
          The app shows headlines, short summaries in its own words and links, never full articles or
          paywalled research, and uses no scraped sources whose terms prohibit it.
        </p>
      </section>

      <section aria-labelledby="privacy" className="rounded-xl border border-line bg-surface p-4 sm:p-5">
        <h2 id="privacy" className="text-base font-semibold">
          Your data
        </h2>
        <p className="mt-2 text-sm text-ink-2">
          Recently viewed stocks, the watchlist and the Plain/Analyst setting are stored in your browser. The
          server stores each day&apos;s estimate per stock (for the track record) and the reports you choose
          to share as snapshot links. There are no accounts and no tracking.
        </p>
      </section>

      <section
        aria-labelledby="legal"
        className="rounded-xl border border-warning/40 bg-warning/10 p-4 sm:p-5"
      >
        <h2 id="legal" className="text-base font-semibold">
          Important
        </h2>
        <p className="mt-2 text-sm text-ink-2">{DISCLAIMER_FULL}</p>
        <p className="mt-2 text-sm text-ink-2">
          Targets are always the app&apos;s model estimates, never recommendations. Publishing ratings and
          price targets publicly can raise securities-regulation questions; this software needs legal review
          before any public or paid launch.
        </p>
      </section>
    </div>
  );
}
