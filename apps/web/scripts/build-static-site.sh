#!/usr/bin/env bash
# Builds the self-contained static site: saved answers plus the analysis engine running in the visitor's browser
# (the same site .github/workflows/pages.yml publishes to GitHub Pages). Hosts that build from the repository,
# such as Vercel (vercel.json), run this instead of a plain `next build`, which would need a Python engine
# server next to it.
#
# Data: with FINNHUB_API_KEY and SEC_USER_AGENT set (FRED_API_KEY optional), the stocks in config/site_tickers.txt
# are recorded from the live APIs and replayed in the browser; otherwise the site runs on the synthetic market.
# SKIP_BACKTEST=1 skips the synthetic backtest (faster build, empty track record).
# Output: apps/web/out. Needs network access to PyPI and uv's Python downloads (and the providers, for real data).
set -euo pipefail

WEB="$(cd "$(dirname "$0")/.." && pwd)"
ROOT="$(cd "$WEB/../.." && pwd)"
ENGINE="$ROOT/services/engine"
if [ ! -f "$ENGINE/pyproject.toml" ]; then
  echo "error: the engine (services/engine) is not part of this build." >&2
  echo "On Vercel: Project Settings → Build and Deployment → enable 'Include files outside the root directory'." >&2
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
rm -rf "$WEB/public/data" "$WEB/public/engine"

cd "$ENGINE"
export UV_PYTHON=3.12
uv sync --frozen --no-dev --quiet
run() { uv run --frozen --no-dev python -m "$@"; }

if [ -n "${FINNHUB_API_KEY:-}" ] && [ -n "${SEC_USER_AGENT:-}" ]; then
  echo "Real data for config/site_tickers.txt"
  (
    export DATA_MODE=record DATA_TIER=free PRICE_SOURCE=finnhub RECORD_SET=recorded
    export FIXTURES_DIR="$WORK/fixtures" DATABASE_URL="sqlite:///$WORK/site.db"
    run engine.tools.export_static --tickers "@$ROOT/config/site_tickers.txt" --no-backtest --out "$WEB/public/data"
    run engine.tools.build_browser_bundle --db "$WORK/site.db" --fixtures "$WORK/fixtures/recorded" \
      --out "$WEB/public/engine"
  )
else
  echo "Synthetic data (set FINNHUB_API_KEY and SEC_USER_AGENT for real stocks)"
  (
    export DATA_MODE=mock FIXTURE_SET=synthetic DATABASE_URL="sqlite:///$WORK/site.db"
    backtest=()
    [ "${SKIP_BACKTEST:-}" = "1" ] && backtest=(--no-backtest)
    run engine.tools.export_static --out "$WEB/public/data" ${backtest[@]+"${backtest[@]}"}
    run engine.tools.build_browser_bundle --db "$WORK/site.db" --out "$WEB/public/engine"
  )
fi

cd "$WEB"
STATIC_DEMO=1 NEXT_PUBLIC_STATIC_DEMO=1 NEXT_PUBLIC_BROWSER_ENGINE=1 NEXT_TELEMETRY_DISABLED=1 \
  NEXT_PUBLIC_BASE_PATH="${NEXT_PUBLIC_BASE_PATH:-}" npx next build
echo "Static site in $WEB/out"
