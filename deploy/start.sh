#!/usr/bin/env bash
# Starts the engine (127.0.0.1:8000) and the web server ($PORT) in one container; if either exits, the
# container stops so the host restarts it.
#
# Data: live when SEC_USER_AGENT and a price source key (FINNHUB_API_KEY, TIINGO_API_KEY or FMP_API_KEY) are
# set; otherwise the synthetic market, labeled as such on every page. DATA_MODE, DATA_TIER and PRICE_SOURCE
# override the choice.
set -euo pipefail

if [ -z "${DATA_MODE:-}" ]; then
  if [ -n "${SEC_USER_AGENT:-}" ] && [ -n "${FINNHUB_API_KEY:-}${TIINGO_API_KEY:-}${FMP_API_KEY:-}" ]; then
    export DATA_MODE=live
  else
    export DATA_MODE=mock FIXTURE_SET=synthetic
    echo "No data keys set: running on the synthetic market (set SEC_USER_AGENT and FINNHUB_API_KEY for real stocks)"
  fi
fi
if [ -z "${DATA_TIER:-}" ]; then
  if [ -n "${FMP_API_KEY:-}" ]; then export DATA_TIER=starter; else export DATA_TIER=free; fi
fi
export PRICE_SOURCE="${PRICE_SOURCE:-auto}"
# The container's disk is not persistent on most free hosts; point DATABASE_URL at a volume to keep history.
export DATABASE_URL="${DATABASE_URL:-sqlite:////tmp/candor.db}"
echo "Data: mode=$DATA_MODE tier=$DATA_TIER price_source=$PRICE_SOURCE"

cd /app/services/engine
uvicorn engine.api.main:app --host 127.0.0.1 --port 8000 --timeout-keep-alive 75 &
engine=$!
# Open the public port only once the engine listens (after its startup), so a host waking the container routes
# the first visit to a working app rather than to "the engine isn't reachable". On a tenth of a CPU the engine's
# imports take most of a minute. The check is a bare TCP connect: spawning a process per try would cost more.
until (exec 3<>/dev/tcp/127.0.0.1/8000) 2>/dev/null; do
  kill -0 "$engine" 2>/dev/null || { echo "The engine exited during startup"; exit 1; }
  sleep 0.5
done
echo "Engine ready"
cd /app/web
HOSTNAME=0.0.0.0 node server.js &
wait -n
exit 1
