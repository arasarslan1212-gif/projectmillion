"use client";

import Link from "next/link";
import { useHealth } from "@/lib/api";
import { DISCLAIMER_FULL } from "@/lib/legal";

export function SiteFooter() {
  const health = useHealth();
  const finnhub =
    !health?.synthetic && Object.values(health?.providers ?? {}).some((p) => p.includes("Finnhub"));
  return (
    <footer className="mt-16 border-t border-line bg-surface/60">
      <div className="mx-auto max-w-7xl space-y-2 px-4 py-8 text-xs leading-relaxed text-muted">
        <p className="text-ink-2">{DISCLAIMER_FULL}</p>
        <p>
          Data: SEC EDGAR (public filings), FINRA (short interest)
          {finnhub ? (
            <>
              , and{" "}
              <a className="underline" href="https://finnhub.io" target="_blank" rel="noreferrer">
                Finnhub.io
              </a>{" "}
              (prices, news, analyst consensus)
            </>
          ) : (
            ", and the commercial providers configured for this deployment"
          )}
          ; see{" "}
          <Link className="underline" href="/about">
            About &amp; data sources
          </Link>
          . This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of
          St. Louis. Price charts by{" "}
          <a className="underline" href="https://www.tradingview.com/" target="_blank" rel="noreferrer">
            TradingView
          </a>{" "}
          Lightweight Charts™.
        </p>
      </div>
    </footer>
  );
}
