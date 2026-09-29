# Roadmap

What is not built yet, and why. Items are grouped by what blocks them; within a group, the most valuable come first.

## Blocked on data access (network or licenses)

- **Verify every adapter against the live APIs and record real fixtures.** The build environment could not reach any market-data host, so all development ran on the synthetic market. With network access: `DATA_TIER=starter make record-fixtures`, then the integration tests run on AAPL, JPM, O, an unprofitable grower, a utility and a small cap (spec §10). Expect adjustments where real responses differ from the documented shapes.
- **Re-run the backtest on real data** (`make backtest` with `track.backtest.tickers` set) and review the calibration log before trusting any recalibration. The synthetic results say nothing about real markets.
- **Management credibility score (guidance vs. delivered).** Needs guidance history: parse 8-K Item 2.02 press-release exhibits, or license a guidance dataset. Until then the pillar is shown as missing and the other pillars are reweighted.
- **Options data:** implied earnings move vs. the historical move, implied-volatility sanity band, unusual options activity. Needs an options feed.
- **Earnings-call tone shift and highlights.** Needs licensed transcripts (e.g. FMP Ultimate). The section says "not licensed on this tier".
- **Intraday data:** the 1D range, VWAP and after-hours price need an intraday/extended-hours feed.
- **Index membership.** Needs a licensed constituents source.
- **Social sentiment.** Only through official APIs within their terms, labeled as noisy.

## Analysis

- **Point-in-time universe for backtests.** Include companies that were later delisted (from SEC filer histories) to reduce survivorship bias, instead of only noting it.
- **10-K diff beyond Risk Factors.** The Item 1A diff is built (D-060). Still to do: MD&A and 10-Q diffs, and an optional LLM summary checked against the diff. Tune the paragraph matching on real filings, whose risk factors use bold headings over several paragraphs.
- **M&A track record.** Tag goodwill impairments and acquisition prices per deal, to judge acquisitions after the fact; the capital-allocation scorecard shows M&A for information only today.
- **Event studies:** the stock's average reaction to past events of the same 8-K item type.
- **Executive pay alignment** from DEF 14A (pay vs. total shareholder return).
- **Supply-chain and customer-concentration extraction** from 10-K text (today: a keyword-based concentration red flag).
- **More sector KPIs** where companies use custom XBRL extensions (NRR, same-store sales, occupancy, production): per-company tag mapping.
- **Calibration by more dimensions** (sector × volatility × size) once live history is large enough; today buckets are by volatility only.

## Product

- **Accounts**, so watchlists and alerts follow a user across devices. Today the watchlist lives in the browser and is synced to a single server-side list per deployment.
- **Alert delivery** by email or push. Alerts are evaluated daily into an in-app inbox (D-061).
- **Server-rendered PDF** (headless browser) for a consistent file; today PDF export uses the browser's print dialog with a print stylesheet.
- **Portfolio weights** in the watchlist view (today equal weights, labeled as an illustration).
- **Non-US listings.** Out of scope per the spec; the provider layer would need non-SEC fundamentals.

## Engineering

- Load test on PostgreSQL with many concurrent cold reports; move heavy sections (valuation Monte Carlo, peers) to a job queue if cold loads exceed the 15 s target on real providers.
- End-to-end browser tests (Playwright) in CI for the report, compare, watchlist, track record and snapshot pages, including the accessibility audit that was run manually for M9.
- Run the language-model narrative path against the real API with a small evaluation set (fact-check pass rate, fallback rate, cost per report).
