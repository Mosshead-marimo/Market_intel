FROM ghcr.io/astral-sh/uv:0.12.2 AS uv
FROM python:3.13-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
RUN groupadd --system app && useradd --system --gid app --home /app app
WORKDIR /app
COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock* alembic.ini ./
COPY apps/api ./apps/api
RUN uv sync --frozen --no-dev
USER app
EXPOSE 8000
CMD ["uvicorn", "tradesentinel.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
