FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv PATH=/opt/venv/bin:$PATH
RUN pip install --no-cache-dir uv==0.8.17
WORKDIR /app/services/engine
COPY services/engine/pyproject.toml ./
RUN uv sync --no-dev --no-install-project
COPY services/engine/ ./
COPY config/ /app/config/
COPY fixtures/ /app/fixtures/
RUN uv sync --no-dev
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn engine.api.main:app --host 0.0.0.0 --port 8000"]
