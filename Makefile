# One-command local development. `make dev` runs the engine and the web app with no API keys
# (mock mode). Use `docker compose up` for the containerized stack with PostgreSQL.
SHELL := /bin/bash
ENGINE := services/engine
WEB := apps/web
PY := $(ENGINE)/.venv/bin/python

.PHONY: setup dev engine web test test-engine test-web lint fmt typecheck migrate record-fixtures score-analysts backtest score-outcomes recalibrate clean

setup:
	cd $(ENGINE) && uv venv --python 3.12 -q .venv && uv sync -q
	cd $(WEB) && npm install --no-audit --no-fund

dev: ## engine on :8000 and web on :3000
	@test -d $(ENGINE)/.venv || $(MAKE) setup
	@trap 'kill 0' EXIT; \
	(cd $(ENGINE) && .venv/bin/uvicorn engine.api.main:app --host 127.0.0.1 --port 8000 --reload) & \
	(cd $(WEB) && npx next dev -p 3000) & \
	wait

engine:
	cd $(ENGINE) && .venv/bin/uvicorn engine.api.main:app --host 127.0.0.1 --port 8000 --reload

web:
	cd $(WEB) && npx next dev -p 3000

test: lint typecheck test-engine test-web

test-engine:
	cd $(ENGINE) && .venv/bin/python -m pytest -q

test-web:
	cd $(WEB) && npx vitest run

lint:
	cd $(ENGINE) && .venv/bin/ruff check engine tests && .venv/bin/ruff format --check engine tests
	cd $(WEB) && npx eslint . && npx prettier --check "app/**/*.{ts,tsx}" "components/**/*.{ts,tsx}" "lib/**/*.ts"

typecheck:
	cd $(WEB) && npx tsc --noEmit

fmt:
	cd $(ENGINE) && .venv/bin/ruff check --fix engine tests && .venv/bin/ruff format engine tests
	cd $(WEB) && npx prettier --write "app/**/*.{ts,tsx}" "components/**/*.{ts,tsx}" "lib/**/*.ts"

migrate:
	cd $(ENGINE) && .venv/bin/alembic upgrade head

record-fixtures: ## needs network + keys: DATA_TIER=starter FMP_API_KEY=... make record-fixtures
	DATA_MODE=record $(PY) scripts/record_fixtures.py

score-analysts: ## run the nightly analyst ingestion + scoring job once
	cd $(ENGINE) && .venv/bin/python -c "from engine.jobs.tasks import score_analysts; import logging; logging.basicConfig(level=logging.INFO); score_analysts()"

backtest: ## walk-forward point-in-time backtest (ARGS="--tickers A,B --start 2019-03-29 --every-months 3")
	cd $(ENGINE) && .venv/bin/python -m engine.track.backtest --recalibrate $(ARGS)

score-outcomes: ## grade snapshots whose 12-month horizon has passed
	cd $(ENGINE) && .venv/bin/python -c "from engine.jobs.tasks import score_outcomes; import logging; logging.basicConfig(level=logging.INFO); score_outcomes()"

recalibrate: ## refit and log the track-record recalibration
	cd $(ENGINE) && .venv/bin/python -c "from engine.jobs.tasks import recalibrate; import logging; logging.basicConfig(level=logging.INFO); recalibrate()"

clean:
	rm -rf $(WEB)/.next $(ENGINE)/.pytest_cache $(ENGINE)/dev.db*
