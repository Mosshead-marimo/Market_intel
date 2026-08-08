# TradeSentinel

TradeSentinel is a modular, capability-driven market-intelligence platform. This repository contains the domain-neutral platform foundation, typed provider ports, canonical instrument resolution, and provider-backed structured stock market data. It ships no live vendor adapter, credentials, research, LLM market analysis, recommendations, or prediction implementation.

## Foundation

The workspace contains:

- `apps/api`: FastAPI API, Redis Streams worker, shared platform runtime, and the `platform.system` reference module.
- `apps/web`: Next.js platform console.
- `packages/contracts`: generated OpenAPI declarations and runtime Zod validators.
- `apps/api/migrations`: central Alembic runner and platform-owned migrations.
- `tests`: architecture-boundary tests.

Provider adapters are manifest declarations. Ordered provider chains are selected entirely through `TRADESENTINEL_*_PROVIDERS` JSON-array settings and injected by interface into capabilities. Chains are empty by default, so no external service is contacted. Because `stock_market_data` requires `MarketDataProvider`, API and worker startup intentionally fail until an external adapter is discovered and selected.

Capabilities are loaded automatically from recursively discovered, strictly validated manifests. A new module needs a manifest and capability class—no plugin factory or manual registration. Commands, exact-example intents, direct capability calls, and declarative workflows use one framework-independent execution pipeline with scoped contexts, retries, events, persistence, and deterministic response rendering. Feature modules cannot be imported by the shared platform layer.

## Local development

Prerequisites are Python 3.13, [uv](https://docs.astral.sh/uv/), Node.js 22, pnpm 10, and optionally Docker Desktop.

```text
uv sync
corepack enable
pnpm install
uv run uvicorn tradesentinel.api.app:app --reload
pnpm dev
```

After a market-data adapter is configured, the API is available at `http://localhost:8000`, its OpenAPI UI at `/docs`, and the ChatGPT-style conversation UI at `http://localhost:3000`. Local settings use memory storage by default; Docker uses PostgreSQL, Redis worker execution, resumable SSE, and Redis caching.

Normal text uses the manifest-declared `conversation.mock` fallback workflow. `/echo "hello"` exercises command planning and `/ping` exercises the system capability. Replies are deterministic mocks; no LLM or market-research capability is installed.

`/search "Tata Consultancy"` searches the representative 16-listing catalog. `/resolve TCS` returns typed cross-exchange ambiguity, while `/resolve TCS --exchange NSE` returns one canonical `InstrumentRef`. Match confidence is a deterministic text score, not a probability.

The market-data manifest exposes `/quote`, `/history`, `/performance`, `/compare`, `/corporate-actions`, `/five-year-performance`, and `/benchmark-compare`. Commands resolve canonical instruments first. Direct `/api/v1/market-data/*` endpoints accept structured `InstrumentRef` payloads. Performance uses adjusted closes only and returns Decimal-backed contracts without generated commentary.

Build containers with `docker compose build`. `docker compose up` requires an external provider module and a matching `TRADESENTINEL_MARKET_DATA_PROVIDERS` selection. The migration service upgrades PostgreSQL before the API and worker start.

## Quality checks

```text
uv run ruff format --check .
uv run ruff check .
uv run mypy apps/api/src
uv run pytest
uv run lint-imports
pnpm format:check
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm contracts:check
docker compose config --quiet
```

Use `pnpm contracts:generate` after changing a Pydantic API contract. CI fails if committed OpenAPI output differs from the FastAPI schema.

## Product Goal

A user should be able to ask a question such as "How is TCS doing?" and receive a sourced report containing:

- Current market status
- Five-year performance
- Benchmark comparison
- Recent news and company events
- Public sentiment and narrative shifts
- Technical and fundamental analysis
- Market-shift score
- Probabilistic rise, sideways, and decline scenarios
- Key risks and supporting sources

## Architecture

TradeSentinel uses a modular, plugin-based architecture. New features are implemented as registered capabilities rather than hardcoded into the core application.

The platform core understands only:

- Commands
- Intents
- Capabilities
- Workflows
- Events
- Execution context
- Evidence
- Response components

Domain concepts such as RSI, sentiment, valuation, and prediction belong inside feature modules.

## Technology Stack

### Frontend

- Next.js
- TypeScript
- Tailwind CSS
- shadcn/ui
- TradingView Lightweight Charts or Apache ECharts

### Backend

- Python
- FastAPI
- Pydantic
- LangGraph
- PostgreSQL
- TimescaleDB
- pgvector
- Redis

### Machine Learning

- pandas or Polars
- scikit-learn
- LightGBM or XGBoost
- MLflow

### Infrastructure

- Docker
- AWS EC2 or ECS
- S3-compatible object storage
- OpenTelemetry
- Prometheus
- Grafana
- Sentry

## MVP Scope

- NSE equities
- Chat interface
- Natural-language questions
- Slash commands
- Five-year performance analysis
- News research
- Public sentiment analysis
- Market-shift score
- Technical and fundamental analysis
- Five-day and twenty-day probabilistic predictions
- Prediction history and evaluation
- Source citations and data timestamps

## Non-Goals for MVP

- Real-money trading
- Broker integration
- Options recommendations
- Intraday scalping
- Leverage recommendations
- Personalized investment allocation
- Guaranteed-return language

## Repository Documentation

The `docs/` directory contains the source of truth for product, architecture, contracts, workflows, commands, security, compliance, testing, and implementation planning.
