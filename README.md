# Candor: explainable stock research

A web app that produces a complete, honest, explainable research report for any US-listed stock. It covers fundamentals, the app's own Trust Rating and its 12-month price range with a confidence level, Wall Street analysts weighted by their proven track records, news and sentiment, risks, and interactive charts. An **Explain** section traces every conclusion back to a number.

> **For education and information only. Not investment advice.** The app is not a registered investment adviser or broker-dealer. Ratings, targets and probabilities are model estimates that can be wrong. Past performance does not predict future results.

## Quick start (no API keys needed)

```bash
make setup     # Python 3.12 venv (uv) + npm install
make dev       # engine on :8000, web on :3000
```

Open http://localhost:3000. With no keys configured, the app runs in **mock mode**. If you have recorded real fixtures (see below), mock mode replays them. Otherwise it uses the **synthetic** fixture set: fake companies `ZZTEC`, `ZZBNK`, `ZZREI`, `ZZGRO`, `ZZUTL`, `ZZSML`, clearly labeled SYNTHETIC on every page.

With Docker: `cp .env.example .env && docker compose up` starts PostgreSQL, the engine, the scheduler worker and the web app.

## On GitHub Pages: the engine in your browser

GitHub Pages only serves files, so the site published by `.github/workflows/pages.yml` runs the analysis engine in the visitor's browser. The engine is the same Python code, run by [Pyodide](https://pyodide.org) (CPython compiled to WebAssembly) in a web worker, on the synthetic market. The workflow:

1. Smoke-tests the engine in Pyodide (`apps/web/scripts/engine-smoke.mjs`). This fails fast if something doesn't run in WebAssembly, and reports where its answers differ from the native engine's.
2. Runs the backtest and exports the engine's API responses for the six synthetic stocks with `python -m engine.tools.export_static`, so those pages load instantly.
3. Bundles the engine with `python -m engine.tools.build_browser_bundle`. The bundle holds the code, the config, the database after the backtest (track record, calibration, analyst history) without its provider caches, and two small wheels. It comes to about 1.6 MB; numpy, pandas and scipy come from Pyodide's CDN, about 30 MB on the first visit, then cached.
4. Builds the static site (`STATIC_DEMO=1 NEXT_PUBLIC_STATIC_DEMO=1 NEXT_PUBLIC_BROWSER_ENGINE=1 next build`) and tests it in headless Chromium (`apps/web/scripts/engine-e2e.mjs`) before deploying.

On the site, saved answers show at once and everything else is computed live in the browser: the what-if DCF, peer edits, refresh, compare and watchlist sets, alerts, and full reports for all 78 synthetic companies (the six headline stocks and their ZQ… peers). Two things still need a server: share links, since a snapshot would exist only in one browser, and real market data, since browsers can't call the providers and API keys would be public. Changes last until the page is reloaded.

To enable it, set **Settings → Pages → Build and deployment → Source** to **GitHub Actions**. After the next push, or a manual run of the "Pages demo" workflow, the site is at `https://<owner>.github.io/<repo>/`.

### On Vercel (or another static host)

`vercel.json` (at the repository root and in `apps/web`, whichever the Vercel project uses as its root) builds this same self-contained site with `apps/web/scripts/build-static-site.sh`: the engine export and bundle, then the static build into `apps/web/out`. A plain `next build` isn't enough on its own: that build expects the Python engine running next to it and shows "The analysis engine isn't reachable" without it.

On Vercel:
- With `apps/web` as the Root Directory, keep **Include files outside the root directory** enabled, because the build needs `services/engine`.
- To use real data, set the same `FINNHUB_API_KEY` and `SEC_USER_AGENT` as Environment Variables.
- Builds take about 10 minutes, mostly the synthetic backtest. `SKIP_BACKTEST=1` skips it, leaving the track record empty.

### Real stocks on the site

Add these repository secrets (**Settings → Secrets and variables → Actions**):

| Secret | Value |
|---|---|
| `FINNHUB_API_KEY` | A free key from https://finnhub.io/register. It supplies quotes, news, analyst consensus and earnings; its free plan has no daily price history, so the price chart, risk and quant sections stay empty without a price source. |
| `SEC_USER_AGENT` | Your app name and a contact email, e.g. `Candor Research you@example.com`. The SEC requires a reachable contact and refuses others, including GitHub no-reply addresses. |
| `FRED_API_KEY` (optional) | A free key from FRED, for live interest rates. Without it, rates fall back to the config's defaults. |

With the first two secrets set:

1. Each weekday night, and on every push, the workflow records real data for the stocks in `config/site_tickers.txt` (`DATA_MODE=record`: every provider response is saved, keys stripped).
2. It exports the saved answers.
3. It bundles the recording, so the in-browser engine replays it and downloads only the files each request needs.

The site then carries those stocks, and their peers' data, as of the last close. The backtest track record needs years of history that free data doesn't provide, so it starts empty on real data. `python -m engine.tools.probe_providers` checks each live source through the engine's adapters, and the "Data probe" workflow runs it with the secrets.

To build it locally:

```bash
cd services/engine && export DATA_MODE=mock FIXTURE_SET=synthetic DATABASE_URL=sqlite:///demo.db
.venv/bin/python -m engine.tools.export_static --out ../../apps/web/public/data   # --no-backtest for a quick run
.venv/bin/python -m engine.tools.build_browser_bundle --db demo.db --out ../../apps/web/public/engine
cd ../../apps/web && STATIC_DEMO=1 NEXT_PUBLIC_STATIC_DEMO=1 NEXT_PUBLIC_BROWSER_ENGINE=1 npx next build
```

Serve `apps/web/out` with any static file server. Leave out `NEXT_PUBLIC_BROWSER_ENGINE` for a read-only site that shows only the saved answers.

## Deploy the live app

The app runs as one Docker container: the Python engine and the web server together (the `Dockerfile` at the repository root). With data keys it researches any US-listed stock live; without them it runs on the synthetic market, labeled as such. `.github/workflows/deploy.yml` builds the image on every push and tests it within 512 MB of memory, on the synthetic market and, when the data secrets are set, on live data.

### On Render (free)

`render.yaml` describes the service for [Render](https://render.com):

1. Sign in to https://render.com with your GitHub account.
2. Choose **New → Blueprint**, connect this repository and pick its branch. Render reads `render.yaml`.
3. Fill in the values it asks for, then click **Apply**:
   - `SEC_USER_AGENT`: your name and email, e.g. `Jane Doe jane@example.com`. The SEC requires a real contact.
   - `FINNHUB_API_KEY`: a free key from https://finnhub.io/register (quotes, news, analyst consensus, earnings).
   - `TIINGO_API_KEY`: a free key from https://www.tiingo.com (daily price history and dividends; Finnhub's free plan has neither). Without it, reports price off Finnhub's live quote, and the price chart, dividends, risk and quant sections stay empty.
   - `FRED_API_KEY` (optional): live interest rates.
4. The first build takes about ten minutes. The app is then at the `onrender.com` address shown on the service's page, and every push redeploys it.

On the free plan the service sleeps after 15 minutes without visits, and the next visit wakes it in about a minute. It also gets a tenth of a CPU, so a stock's first report takes a minute or two; reports already computed that day show at once. Anyone with the address can use the app. Tiingo's free plan is for personal use, so keep the address to yourself. For a faster service, change `plan: free` to `starter` in `render.yaml`.

### On a Hugging Face Space (PRO)

Hugging Face hosts Docker Spaces only with a [PRO subscription](https://huggingface.co/pro). With it, the Space gets 2 CPUs and 16 GB of memory, and can be private to your account. Create a token with **Write** permission (Settings → Access Tokens) and add it as the `HF_TOKEN` repository secret, along with the data keys above as secrets (**Settings → Secrets and variables → Actions**). Then run **Actions → Deploy app → Run workflow**. The workflow creates a private Space named `<you>/candor`, copies the keys into it, and prints the app's address once it's running. Set the `HF_SPACE` repository variable (owner/name) to choose another Space, or `HF_SPACE_PRIVATE` to `false` to make a new one public.

### Elsewhere

The same image runs on any Docker host (Railway, Fly.io, Google Cloud Run, a VPS). Pass the same variables and route port `$PORT` (default 7860). The database is SQLite in `/tmp`, so history (track record, alerts) resets when the container restarts, unless `DATABASE_URL` points at persistent storage.

## What's in the app

| Page | What it shows |
|---|---|
| `/` | Search with autocomplete, recently viewed, watchlist |
| `/stock/[ticker]` | The report. Header badges (Trust Rating, the app's P10/P50/P90 target, confidence, all-analyst and trusted consensus), a fact-checked Verdict, and sections for the snapshot, overview, price chart with overlays, Trust Rating, price target and valuation (with DCF what-if sliders), Explain (including a pre-mortem), analysts, news, earnings, dividends, ownership, capital allocation, fundamentals, risk (including what changed in the 10-K risk factors), quantitative views (factor exposures, macro sensitivity, seasonality) and peers. Plain/Analyst toggle, Share link, PDF (print) |
| `/compare?t=A,B,C` | Two to four stocks side by side: scores, targets, pillars, key metrics, indexed price chart, pillar radar |
| `/watchlist` | Watched stocks with scores and risk, and an equal-weight aggregate (volatility, correlation, sector mix) |
| `/alerts` | An inbox for the watchlist: price leaving the app's range, view-change triggers, insider cluster buys, high-trust analyst rating changes, new 8-Ks |
| `/s/[token]` | A shared report, frozen as it was on the day, later showing how its estimate turned out |
| `/track-record` | How past estimates held up (backtest until live history matures), with the recalibration log |
| `/methodology`, `/glossary` | Every parameter, generated from `config/engine.yaml`; every metric definition |
| `/about` | Data sources and attribution, this deployment's providers and mode, legal notes |

Measured on the synthetic market, a cold report takes about 3 s and a cached one under 0.1 s, with sections appearing as they finish (DECISIONS D-056). Every page passes an axe-core WCAG 2.1 AA audit in light and dark mode (D-055).

## Using real data

1. `cp .env.example .env`, set `DATA_MODE=live`, choose `DATA_TIER` (`free` | `starter` | `pro`), and add keys:
   - `free`: `FRED_API_KEY`, `TIINGO_API_KEY` (prices), `FINNHUB_API_KEY` (news, recommendation trends). SEC and FINRA need no key; set `SEC_USER_AGENT` to your app name and email.
   - `starter`: add `FMP_API_KEY` (per-analyst price targets, estimates, profile).
   - `pro`: add `MASSIVE_API_KEY` (Benzinga analyst ratings).
2. Optional: `ANTHROPIC_API_KEY` for LLM-written narratives. Without it, every narrative uses validated templates.
3. To record mock-mode fixtures for offline use and tests: `DATA_TIER=starter make record-fixtures` (records AAPL, JPM, O, RIVN, DUK and a small cap; pass your own tickers to `scripts/record_fixtures.py`).

See **DATA_SOURCES.md** for licenses and attribution. **Legal note:** publishing ratings and price targets publicly can raise securities-regulation questions, and most data vendors require a commercial license for public display. Get legal review before any public or paid launch.

## Architecture

```
apps/web          Next.js 16 (App Router), TypeScript, Tailwind 4; lightweight-charts + ECharts
services/engine   Python 3.12, FastAPI, pandas/numpy/scipy, SQLAlchemy + Alembic
config/           engine.yaml (every weight/threshold/assumption) and metrics.yaml (definitions)
fixtures/         recorded provider responses for mock mode
scripts/          fixture recording and utilities
```

- **Numbers come from code; words come from the LLM.** Every figure is computed by deterministic, tested Python. The web only formats values.
- **Point-in-time.** Facts carry their SEC filing dates, and a report "as of" a date sees only what was public then.
- **Swappable providers.** Analysis code depends on interfaces (`engine/providers/base.py`); vendors live in adapters behind a shared HTTP layer that handles rate limits, retries with backoff, a circuit breaker, and record/replay.

Full design: PLAN.md. Decisions and trade-offs: DECISIONS.md. Future work: ROADMAP.md.

## Development

```bash
make test        # lint + typecheck + engine tests (pytest) + web tests (vitest)
make fmt         # ruff + prettier
make migrate     # alembic upgrade head (DATABASE_URL)
```

## Track record

Every live report stores a snapshot of its estimate; a daily job grades snapshots once their 12-month horizon passes, and a weekly job refits (and logs) the recalibration. Until live history matures, the evidence is a walk-forward, point-in-time backtest, labeled BACKTEST everywhere it appears:

```bash
make backtest                                   # default universe, quarterly from 2019, then recalibrate
make backtest ARGS="--tickers AAPL,JPM --every-months 6"
make score-outcomes                             # grade snapshots that are due
make recalibrate                                # refit the prob-up map and range scale; every fit is logged
```

Results are at `/track-record`. `/methodology` is generated from `config/engine.yaml`, so it always shows the parameters the engine runs with.
