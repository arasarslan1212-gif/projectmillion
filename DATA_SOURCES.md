# Data sources, licenses and attribution

Every figure the app shows carries its source and as-of date. This file lists each provider, what it is used for, its license terms as understood on 2026-09-28, and the attribution it requires. **Re-check each provider's current terms before any public or paid deployment**; standard plans at several vendors are for personal use only.

Verification status: the adapters were written against each provider's published response shapes. The build environment had no network access to the providers, so the adapters have **not yet been exercised against the live APIs**. Run `make record-fixtures` with network access to verify and record them.

| Provider | Used for | Tier | License / terms | Attribution shown |
|---|---|---|---|---|
| **SEC EDGAR** (`data.sec.gov`, `www.sec.gov`) | Ticker↔CIK map, XBRL company facts, frames, submissions (8-K items, NT filings), Form 4, 10-K text | all | U.S. government public data. Fair-access policy: ≤10 requests/second and a descriptive `User-Agent` with a contact email (`SEC_USER_AGENT`). The app throttles to 5 req/s. | "Source: SEC EDGAR" on every fundamentals/filings figure |
| **FRED** (Federal Reserve Bank of St. Louis) | 10-year and 3-month Treasury yields, CPI, Baa spread, dollar index, WTI | all | Free API key. Only public-domain series are used; some FRED series are copyrighted by third parties and are not used. | Footer: "This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis." |
| **FINRA** | Equity short interest (twice monthly) | all | Public dataset via the FINRA Query API. | "Source: FINRA" on short-interest figures |
| **Tiingo** | End-of-day prices, dividends and splits | free | Free and Power tiers are **personal/internal use only**; public display needs a commercial license. | "Source: Tiingo" |
| **Finnhub** | Company news headlines, analyst recommendation trends (consensus only), earnings surprises/calendar | free, starter | Free tier: 60 calls/minute. Redistribution/display outside personal use needs a commercial agreement. | "Source: Finnhub" |
| **Financial Modeling Prep** | Prices, quote, profile, executives, employee counts, segments, peers, consensus estimates, earnings, **per-analyst price targets** (`price-target-news`), firm grades, target consensus, news headlines, institutional holders | starter, pro | Standard plans are licensed for personal use; public display requires FMP's data display/licensing agreement. Earnings-call transcripts need the Ultimate plan and are not used unless licensed. | "Source: Financial Modeling Prep" |
| **Benzinga via Massive** (formerly Polygon.io) | Per-analyst ratings and price targets (analyst, firm, prior/current rating and target) | pro | Commercial terms via Massive/Benzinga (expansions from ~$99/month on top of a Massive plan). | "Source: Benzinga via Massive" |
| **Anthropic Claude API** | Headline summaries and classification; the Verdict and Explain narratives (optional) | optional | Anthropic commercial terms. LLM output never produces numbers, and every number in a narrative is checked against the facts (see README). | "Summary written by the app" labels |
| **TradingView Lightweight Charts™** | Price chart rendering | — | Apache-2.0. The NOTICE file's attribution and a link to tradingview.com must be shown; the chart's attribution logo is kept on and the footer links to TradingView. | Footer and on-chart logo |
| **Apache ECharts** | All other charts | — | Apache-2.0. | — |

## What is never stored or shown

- Full news articles: only headline, source, time, link, and a summary of at most 2 sentences in the app's own words.
- Paywalled broker research: bank/broker cards show only the rating, target and date, a one-sentence description the app generates from those fields, and a link to the public headline. The feeds carry no reasoning, and the cards say so (DECISIONS.md D-028).

## Analyst data, and what the app derives from it

- **Stored:** each analyst action (date, firm, analyst name when provided, rating, target, provider headline and link) in `analyst_actions`, to build track records across stocks.
- **Derived by the app:** Trust Scores, the trusted consensus, target-revision history, and rating counts over time. These are the app's own computations, labelled as such.
- **Tier fallback:** per-analyst (FMP `price-target-news` joined to FMP `grades`, or Benzinga via Massive) → firm-level grades only → consensus only (Finnhub recommendation trends + FMP target consensus) → none. The UI shows which level is in use.
- Earnings-call transcripts beyond what a license allows. None are used by default.
- Scraped data from sites whose terms prohibit it. Yahoo Finance and similar unofficial endpoints are not used.

## Synthetic data (development only)

When no provider is reachable, `FIXTURE_SET=synthetic` serves a generated market of fake companies (tickers `ZZ*`/`ZQ*`, names ending "(Synthetic)", links to example.com). It exists for development and tests. Every page that shows it carries a **SYNTHETIC TEST DATA** banner. See DECISIONS.md D-001 and D-013.
