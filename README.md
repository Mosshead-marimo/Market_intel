# TradeSentinel

TradeSentinel is a modular, capability-driven market-intelligence platform. This repository contains the domain-neutral platform foundation, typed provider ports, canonical instrument resolution, structured stock market data, deterministic evidence-first news research, public-sentiment analysis, technical analysis, fundamentals, and a YAML-composed stock overview. It ships no live vendor adapter, credentials, LLM market analysis, recommendations, or prediction implementation.

## Foundation

The workspace contains:

- `apps/api`: FastAPI API, Redis Streams worker, shared platform runtime, and the `platform.system` reference module.
- `apps/web`: Next.js platform console.
- `packages/contracts`: generated OpenAPI declarations and runtime Zod validators.
- `apps/api/migrations`: central Alembic runner and platform-owned migrations.
- `tests`: architecture-boundary tests.

Provider adapters are manifest declarations. Ordered provider chains are selected entirely through `TRADESENTINEL_*_PROVIDERS` JSON-array settings and injected by interface into capabilities. Chains are empty by default, so no external service is contacted. Capabilities remain discoverable without a provider and return typed HTTP 503 `PROVIDER_NOT_CONFIGURED` responses when invoked.

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

The API is available at `http://localhost:8000`, its OpenAPI UI at `/docs`, and the ChatGPT-style conversation UI at `http://localhost:3000`. Local settings use memory storage by default; Docker uses PostgreSQL, Redis worker execution, resumable SSE, and Redis caching.

Normal text uses the manifest-declared `conversation.mock` fallback workflow. `/echo "hello"` exercises command planning and `/ping` exercises the system capability. Replies are deterministic mocks; no LLM is installed.

`/search "Tata Consultancy"` searches the representative 16-listing catalog. `/resolve TCS` returns typed cross-exchange ambiguity, while `/resolve TCS --exchange NSE` returns one canonical `InstrumentRef`. Match confidence is a deterministic text score, not a probability.

The market-data manifest exposes `/quote`, `/history`, `/performance`, `/compare`, `/corporate-actions`, `/five-year-performance`, and `/benchmark-compare`. Commands resolve canonical instruments first. Direct `/api/v1/market-data/*` endpoints accept structured `InstrumentRef` payloads. Performance uses adjusted closes only and returns Decimal-backed contracts without generated commentary.

The research manifest exposes `/news`, `/research`, and `/sources`. It searches a configured `NewsProvider`, conservatively deduplicates articles, applies versioned phrase rules, stores normalized events and evidence, and returns timelines and evidence indexes. Confidence is extraction-rule strength rather than truth probability. Retrieved content remains untrusted and is never sent to an LLM.

The public-sentiment manifest exposes `/public-sentiment`, `/sentiment-trend`, `/narratives`, and `/sentiment-shift`. It resolves one canonical target, consumes the complete instrument catalog, filters spam, applies provider/source/engagement weights, and returns structured snapshots, narratives, trends, and descriptive shifts. Provider sentiment is preferred only when its label, score, and confidence are complete; otherwise the versioned lexicon is used. Unknown text is excluded rather than treated as neutral. No output is a forecast.

The technical-analysis manifest exposes `/technical`, `/rsi`, `/macd`, `/ema`, `/sma`, `/atr`, `/adx`, `/support`, `/resistance`, `/trend`, `/momentum`, and `/volatility`. Workflows resolve the instrument and one-year default window, then call the cached `stock.history` capability. The module scales OHLC by the adjusted-close ratio and calculates every output with pure Decimal arithmetic. Labels describe historical observations only; they are not predictions or recommendations.

`/overview TCS --exchange NSE` runs the manifest-declared `stock.overview` workflow. It resolves the instrument once, starts independent market, research, sentiment, and fundamentals branches concurrently, runs technical analysis from the already retrieved adjusted history, and renders sections in the order declared by YAML. Market data and technical analysis are required; unavailable research, sentiment, or fundamentals providers produce explicit partial sections.

Run the stack with `docker compose up --build`. The migration service upgrades PostgreSQL before the API and worker start. Market-data, research, and public-sentiment execution remain unavailable until their external provider modules are selected, but the API, worker, web application, and provider-free capabilities start normally.

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

The `.docs/` directory contains the source of truth for product, architecture, contracts, workflows, commands, security, compliance, testing, and implementation planning.

## Fundamentals

The manifest-discovered `fundamentals` module exposes deterministic revenue, profit, cash-flow, debt, margins, ROE, ROCE, valuation, growth, peer comparison, and aggregate snapshot capabilities. Annual and quarterly trends remain separate. Current calculated valuation is distinct from provider-reported multiples; missing quotes yield partial reported-only valuation. Example commands are `/fundamentals TCS --exchange NSE`, `/growth MSFT --exchange NASDAQ`, and `/peer-compare TCS --exchange NSE --peers "INFY@NSE,RELIANCE@NSE"`.
