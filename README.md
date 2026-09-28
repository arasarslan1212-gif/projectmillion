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
