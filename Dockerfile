# The whole app in one container: the Python analysis engine and the Next.js web server, which forwards
# /api/engine/* to the engine inside the container. It fetches live data when API keys are set (see
# deploy/start.sh) and runs on the synthetic market otherwise.
# Runs on any Docker host: Hugging Face Spaces (.github/workflows/deploy.yml), Render (render.yaml), Railway,
# Fly.io or a VPS. Listens on $PORT (default 7860).

# ---- web: a standalone Next.js server build -------------------------------------------------------------------
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY apps/web/ ./
ENV NEXT_TELEMETRY_DISABLED=1 NEXT_OUTPUT=standalone ENGINE_URL=http://127.0.0.1:8000
RUN rm -rf public/data public/engine && npx next build

# ---- runtime: Python engine + the Node binary for the web server ------------------------------------------------
FROM python:3.12-slim-bookworm
COPY --from=web /usr/local/bin/node /usr/local/bin/node
RUN pip install --no-cache-dir uv==0.8.17 \
    && useradd --create-home --uid 1000 app
ENV PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy \
    PATH=/opt/venv/bin:$PATH NODE_ENV=production NEXT_TELEMETRY_DISABLED=1 PORT=7860
WORKDIR /app/services/engine
COPY services/engine/pyproject.toml services/engine/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY services/engine/ ./
COPY config/ /app/config/
RUN uv sync --frozen --no-dev && mkdir -p /app/fixtures
COPY --from=web /web/.next/standalone /app/web
COPY --from=web /web/.next/static /app/web/.next/static
COPY --from=web /web/public /app/web/public
COPY deploy/start.sh /app/start.sh
RUN chmod +x /app/start.sh && chown -R app:app /app/web/.next /app/fixtures
USER app
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s CMD ["node", "-e", "fetch('http://127.0.0.1:'+(process.env.PORT||7860)+'/api/engine/health').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))"]
CMD ["/app/start.sh"]
