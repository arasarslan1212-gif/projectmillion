# Build Plan: AI Stock Analysis Web App

*Written 2026-09-28, before any code. Every later deviation is recorded in `DECISIONS.md`.*

## 0. Constraints found before starting

| Constraint | Consequence | Mitigation |
|---|---|---|
| This environment's egress policy blocks **every** market-data host (SEC, FRED, FINRA, FMP, Finnhub, Tiingo, Massive/Benzinga, Nasdaq). Only npm/PyPI are reachable. Direct fetches of provider docs are blocked too; only web search works. | Real fixtures can't be recorded from here, and real tickers can't be loaded live from here. | (1) All adapters are written against the providers' documented response shapes and share one HTTP layer with **record/replay**. (2) `make record-fixtures` records the 6 real tickers as soon as the network is opened. (3) Meanwhile, a **synthetic** fixture set with obviously fake tickers (`ZZTEC`, `ZZBNK`, …) runs through the *same* adapters, so the whole pipeline is exercised end to end. It is labeled SYNTHETIC everywhere and never presented as real (see DECISIONS D-001). |
| No provider API keys and no `ANTHROPIC_API_KEY` in the environment. | LLM narratives can't be generated here. | Every narrative has a deterministic, fact-validated **template fallback**, which the spec already requires. The LLM path is tested with a fake client. |
| The Docker daemon isn't running here; PostgreSQL 16 binaries are available. | `docker compose up` can't be tested here. | Compose files are written for users. Tests run on SQLite, plus a local Postgres run for the migrations. |

## 1. Architecture

```
                ┌──────────────────────── apps/web (Next.js 16, TS, Tailwind 4) ──────────────────────┐
 Browser ─────▶ │ /             search + recent + watchlist                                            │
                │ /stock/[t]    report page: sticky badges, progressive sections                       │
                │ /compare      2–4 tickers   /track-record   /methodology   /s/[token] (snapshot)     │
                │ lightweight-charts (price) + ECharts (everything else)                               │
                └──────────────┬───────────────────────────────────────────────────────────────────────┘
                               │ /api/engine/* (Next rewrite → ENGINE_URL)
                ┌──────────────▼────────────── services/engine (Python 3.12, FastAPI) ─────────────────┐
                │ api/        REST: search, report sections, compare, snapshots, track record, meta     │
                │ report/     ReportBuilder: memoised per-ticker DataView, each section isolated        │
                │ fundamentals/  XBRL → standardized PIT statements, TTM, ratios, sector KPIs           │
                │ analysis/   quality scores, risk, technicals, percentiles, Trust Rating, red flags    │
                │ valuation/  WACC, DCF + Monte Carlo, reverse DCF, multiples, sector models, blend,    │
                │             confidence, sanity checks                                                │
                │ analysts/   analyst + firm Trust Scores (shrinkage), consensus, trusted consensus    │
                │ news/       dedupe clustering, LLM classification, sentiment series, digest          │
                │ llm/        facts JSON, Anthropic client, cache, cost log, number validator,         │
                │             templates                                                                │
                │ track/      snapshots, outcome scoring, walk-forward backtest, calibration           │
                │ providers/  interfaces + adapters (SEC, FRED, FINRA, FMP, Tiingo, Finnhub, Massive)   │
                │ http/       rate limiter, retries + backoff, circuit breaker, record/replay          │
                │ jobs/       APScheduler: refreshes, analyst scoring, matured-prediction scoring      │
                └──────────────┬───────────────────────────────────────────────────────────────────────┘
                               │ SQLAlchemy 2 + Alembic
                        PostgreSQL (compose) / SQLite (local dev + tests)
config/engine.yaml  ← every weight/threshold/assumption; its hash is stamped on every report,
                      and the Methodology page is rendered from it.
fixtures/           ← recorded HTTP (real) + synthetic HTTP fixtures for DATA_MODE=mock
```

**Why two services?** The quantitative code (DCF, Monte Carlo, regressions, isotonic calibration) is clearer and easier to test in numpy/scipy, and the spec defaults to it. The web layer stays purely presentational: it never computes a number, it only formats them.

**The number contract.** The engine returns every figure as a `Metric` object: `{id, value, unit, status, reason, source, as_of, def}`. The web only formats. Tooltips come from a definitions registry (`config/metrics.yaml`) served at `/api/meta/definitions`, the same registry the Methodology page renders.

## 2. Data providers

Checked on 2026-09-28 by web search (direct doc fetches were blocked by egress). **Re-verify pricing and terms before paying.**

| Provider | Used for | Tier | Cost / limits (as found) | Terms that matter |
|---|---|---|---|---|
| **SEC EDGAR** (`data.sec.gov`, `www.sec.gov`) | Ticker→CIK map, XBRL company facts (point-in-time via `filed`), submissions (8-K items, NT 10-K, 4.02), Form 4 XML, 13F, 10-K text, frames (sector distributions) | all | Free. ≤10 req/s; a descriptive `User-Agent` with contact email is mandatory (403 plus a temporary IP block otherwise) | Public data. Fair-access policy. We throttle to 5 req/s. |
| **FRED** (`api.stlouisfed.org`) | 10y Treasury (DGS10), CPI, GDP, BAA spread | all | Free API key. ~120 req/min | Must display "This product uses the FRED® API but is not endorsed or certified by the Federal Reserve Bank of St. Louis." Some third-party series are copyrighted, so we use only public-domain series (DGS10, CPIAUCSL, GDP, BAA10Y). |
| **FINRA** (`api.finra.org`) | Equity short interest (twice monthly), Reg SHO daily short volume | all | Public datasets via the Query API | Attribute FINRA. |
| **Tiingo** | EOD prices (adjusted + raw), splits/dividends | free | Free: 1,000 req/day, 50/hr, 500 unique symbols/month. Power ($10/mo): news + higher limits | **Free and Power tiers are personal/internal use only.** Public display needs a commercial license. |
| **Finnhub** | Company news (free), recommendation trends (free, consensus distribution only), earnings surprises | free | Free: 60 calls/min. Price targets and upgrades/downgrades are premium | Attribution. Commercial display needs a license. |
| **Financial Modeling Prep (FMP)** | **Per-analyst price targets** (`price-target-news`: analystName, analystCompany, priceTarget, priceWhenPosted, newsURL, publishedDate), firm grades history, estimates, earnings, profile, news, insider, 13F, peers | starter | Free: 250 req/day. Starter/Premium/Ultimate (300/750/3,000 req/min). Transcripts only on Ultimate | Personal use on standard plans. Public display/redistribution needs FMP's data display license. |
| **Benzinga via Massive** (formerly Polygon) | Best per-analyst data: analyst_name, firm, rating_prior/current, pt_prior/current, action codes, analyst details | pro | Benzinga expansions from ~$99/mo on top of a Massive plan | Commercial terms via Massive/Benzinga. |
| Alpha Vantage, EODHD, Intrinio, Nasdaq Data Link | Evaluated, **not selected** | — | AV free = 25 req/day (too low). EODHD all-in-one $99.99/mo with no confirmed per-analyst targets. Intrinio and Nasdaq Data Link are enterprise-priced | — |

**Selection criterion #1 (per-analyst history):** FMP `price-target-news` is the most affordable source of per-analyst targets. It lacks the rating in the same record, so we join it to FMP firm grades by firm and date (±3 days). Benzinga-via-Massive is the higher-quality pro option. The **fallback chain** is implemented and labeled in the UI:
`per-analyst (pro/starter) → firm-level (grades only) → consensus only (Finnhub recommendation trends) → none`.

**`DATA_TIER` feature matrix**

| Feature | free | starter | pro |
|---|---|---|---|
| Fundamentals, filings, Form 4, 13F, red flags | SEC | SEC (+FMP fill-ins) | same |
| EOD prices | Tiingo free key | FMP | FMP / Massive |
| Estimates and revisions | — (label) | FMP (revisions are built by snapshotting daily) | FMP |
| Analyst trust | consensus distribution only | per-analyst (FMP) | per-analyst (Benzinga) |
| News | Finnhub free | FMP + Finnhub | + Benzinga news |
| Transcripts | — | — | only with a licensed source (FMP Ultimate). Otherwise "not licensed" |
| Options implied move | — | — | only if an options adapter is configured; otherwise historical move only |

## 3. Database schema (SQLAlchemy + Alembic)

- `companies(ticker PK, cik, name, exchange, sic, sic_desc, sector, industry, profile_json, is_synthetic, updated_at)`
- `prices(ticker, date, open, high, low, close, adj_close, volume, source, PK(ticker,date))`
- `corporate_actions(ticker, date, kind[split|dividend], value, source)`
- `fundamentals(cik, taxonomy, concept, unit, period_start, period_end, fy, fp, form, accn, filed_at, value, frame)`: raw point-in-time XBRL facts. Index `(cik, concept, period_end, filed_at)`.
- `estimates(ticker, period_end, period_type, metric, mean, low, high, n, as_of, source)`
- `estimate_revisions(ticker, period_end, metric, as_of, mean, source)`: daily snapshots, so revisions can be computed even from providers without history.
- `analyst_actions(id, ticker, analyst_key, analyst_name, firm, date, action, rating, rating_prior, rating_norm, target, target_prior, price_when_posted, url, source, source_uid UNIQUE)`
- `analyst_scores(analyst_key, scope, n_calls, hit_rate, mape, excess_3m/6m/12m, bullish_bias, herding, raw, shrunk, trust_score, computed_at, config_hash)`
- `firm_scores(firm, scope, …same…)`
- `news(id, ticker, published_at, headline, source_name, url UNIQUE, provider, cluster_id, fetched_at)`: headlines and links only, never article bodies.
- `news_analysis(news_id, model, summary, sentiment, relevance, materiality, event_type, input_hash, created_at)`
- `insider_tx(id, ticker, filer, role, tx_date, filed_at, code, open_market, plan_10b5_1, shares, price, value, owned_after, accn, url)`
- `institutional_holdings(ticker, holder, holder_cik, period, filed_at, shares, value, change_shares, source)`
- `short_interest(ticker, settlement_date, short_interest, avg_volume, days_to_cover, source)`
- `macro(series_id, date, value, source)`
- `filings(accn PK, cik, form, filed_at, report_date, items, primary_doc, url)`
- `provider_cache(key PK, provider, dataset, fetched_at, expires_at, payload_json)`: normalized payload cache with TTLs.
- `app_snapshots(id, share_token, ticker, created_at, as_of, price, p10, p50, p90, prob_up, confidence, trust_rating, pillars_json, engine_version, config_hash, is_backtest, report_json)`
- `snapshot_outcomes(snapshot_id, horizon_date, realized_price, in_band, abs_pct_err, realized_up, brier, scored_at)`
- `llm_cache(key PK, model, purpose, input_tokens, output_tokens, cost_usd, output_json, created_at)`
- `watchlist(ticker PK, added_at)`, `alerts(id, ticker, kind, params_json, created_at, last_fired_at)`

## 4. Key modeling decisions (details in DECISIONS.md)

- **12-month target ≠ intrinsic value.** Each method estimates intrinsic value V (today). The long-term intrinsic value is shown separately. The 12-month P50 assumes the price earns its cost of equity (net of dividends) and closes a configurable fraction λ (default 0.4) of the log-gap to V within 12 months. This is deliberately more conservative than "full convergence", because sell-side-style targets are systematically too optimistic. λ is a documented assumption that the backtest evaluates.
- **Range.** Log-normal with σ² = σ_market² + (λ·σ_valuation)², widened as confidence falls. So P10–P90 is an honest 80% interval that the calibration page can check.
- **SBC is a real expense.** GAAP EBIT already deducts it. The engine never adds it back, and the FCF quality metrics show SBC-adjusted FCF.
- **Point-in-time.** Every fact carries `filed_at`. A `DataView(ticker, as_of)` is the only way the analysis code reads data, and it filters by `filed_at ≤ as_of`. When several filings report the same period, it uses the value as originally filed (restatements appear only once they were filed).

## 5. Milestone order

M1 foundations → M2 fundamentals → M3 Trust Rating → M4 valuation → M5 analysts → M6 news → M7 Explain → M8 track record → M9 polish plus extras. Each milestone ends with tests, a run of the app, a visual pass over every section with the synthetic tickers (and real ones once the network is open), a status note, and a commit.

## 6. Extra features (§12), ranked by value ÷ effort

| Rank | Feature | Value | Effort | Plan |
|---|---|---|---|---|
| 1 | Interactive DCF sliders (growth, margin, WACC, terminal g), recomputed by the engine | High | Low | Build (M9) |
| 2 | Management credibility score (guidance vs. delivered, from 8-K Item 2.02 exhibits and estimates) | High | Med | Build (M7/M9), data permitting |
| 3 | Capital allocation scorecard: buyback timing vs. later price, SBC dilution, dividend policy | High | Med | Build (M9) |
| 4 | Pre-mortem ("12 months later it fell 40%: most likely reasons"), grounded in the facts JSON | High | Low | Build (M7) |
| 5 | Factor exposures (market, size, value, momentum, quality proxies via ETF regressions) | Med | Med | Build (M9) |
| 6 | Macro sensitivity (rates, oil, dollar, credit spreads; FRED series) | Med | Low | Build (M9) |
| 7 | 10-K Risk Factors / MD&A year-over-year diff with a short LLM summary | High | Med | Build if time allows, otherwise ROADMAP |
| 8 | Post-earnings drift and seasonality statistics | Med | Low | Build (M9) |
| 9 | Alerts (target band crossed, view-change trigger crossed, insider cluster buy, high-trust analyst change, new 8-K), evaluated by a job and shown in an in-app inbox | Med | Med | Build a basic version |
| 10 | Portfolio/watchlist aggregate (Trust Rating and risk across the watchlist) | Med | Low | Build (M9) |
| 11 | Beginner glossary generated from the metric registry | Med | Low | Build (M9) |
| 12 | Event studies (reaction to similar past 8-K event types) | Med | Med | ROADMAP |
| 13 | Executive pay alignment (DEF 14A) | Med | High | ROADMAP |
| 14 | Earnings call tone shift (needs licensed transcripts) | Med | High | ROADMAP |
| 15 | Unusual options activity (needs an options feed) | Low | High | ROADMAP |
| 16 | Supply-chain / customer concentration extraction from the 10-K | Med | Med | Concentration flag in M3. The full extraction goes on the ROADMAP |

## 7. Requirements the available data can't fully support, and the fallbacks

| Requirement | Gap | Fallback (labeled in the UI) |
|---|---|---|
| Per-analyst trust on the free tier | No free per-analyst history exists | Consensus distribution only, labeled "Analyst-level track records unavailable on this data tier" |
| Estimate revision history (7/30/60/90d) | FMP gives current estimates; history is thin | Snapshot estimates daily into `estimate_revisions`. Revisions show "insufficient history" until 7/30/60/90 days of snapshots exist |
| Bank/broker reasoning text | Research is paywalled | Rating and target only, with "No public reasoning available". A 1–2 sentence summary only when a public news URL exists |
| Transcripts and call tone | Need a licensed source | Section shows "not licensed on this tier" |
| Implied volatility / implied earnings move | No options feed selected | Historical average post-earnings move only |
| After-hours price | EOD feeds don't carry it | Hidden when missing |
| Sector KPIs (NIM, CET1, occupancy, same-store sales, NRR, production) | Often not XBRL-tagged, or company-specific extensions | Pulled from standard tags where they exist. Otherwise "unavailable: not tagged in XBRL" |
| Revenue by segment/geography | Segment facts use dimensional XBRL, which the companyfacts API omits | FMP segment endpoints on starter+. On free: "unavailable on free tier" |
| Employees, CEO, tenure, founding date | Not in XBRL (employee count is sometimes tagged in `dei`) | FMP profile on starter+; `dei:EntityNumberOfEmployees` when present; otherwise unavailable |
| Index membership | No free authoritative source | "unavailable" (ROADMAP: licensed index constituents) |
| Pension deficit in the equity bridge | Inconsistent tagging | Included when `DefinedBenefitPlanFundedStatusOfPlan` is present; otherwise the caveat is shown |
| Live track record | Needs 12 months of history | Walk-forward backtest, clearly labeled BACKTEST, until live snapshots mature |
| Survivorship bias | Universe = currently listed companies | Caveat shown on every backtest view |

## 8. Questions for you (non-blocking; defaults in brackets)

1. Monthly data budget? [Assume **starter ≈ $30–70/mo**: FMP Starter/Premium. Free tier fully supported.]
2. Deploy target? [Local Docker Compose; the app is stateless apart from Postgres, so any container host works.]
3. Non-US markets? [US-listed only, per the spec.]
4. Will this be public or paid? [Assume **private/personal**. Public display needs commercial data licenses (Tiingo, FMP, Finnhub) and legal review (see README).]
5. Can the environment's network allowlist be opened (hosts listed in §0)? [Until then, synthetic fixtures only.]
