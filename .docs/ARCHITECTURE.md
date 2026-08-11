# Architecture

## Evidence-grounded assistant

`llm_assistant` is a feature module, not part of the domain-neutral platform. Its manifest declares both vendor adapters, six assistant capabilities, and the natural-language fallback. A late-bound execution gateway exposes only registry-derived, planner-enabled read-only commands and routes validated calls through the normal pipeline. Vendor output is buffered until schema and evidence validation pass. See ADR 0022.

## Architecture Principle

TradeSentinel uses a modular monolith with plugin-style capability registration.

The platform core understands only:

- Commands
- Intents
- Capabilities
- Workflows
- Events
- Execution context
- Evidence
- Results
- Response components

Financial concepts remain inside modules.

## High-Level Flow

```text
Web Chat
   ↓
API Gateway
   ↓
Conversation Orchestrator
   ↓
Command Registry + Capability Registry
   ↓
Workflow Engine
   ↓
Feature Modules
   ↓
Provider Adapters + Shared Infrastructure
   ↓
Evidence Guard + Response Renderer
```

## Main Layers

### User Interface Layer

Supports web chat first, with future REST, mobile, CLI, and messaging clients.

### API Gateway

Responsibilities:

- Authentication
- Authorization
- Session handling
- Rate limiting
- Request validation
- Streaming
- Request IDs
- API versioning

### Conversation Orchestrator

Responsibilities:

- Parse commands
- Detect intent
- Resolve context
- Select workflows
- Invoke capabilities
- Merge results
- Handle follow-up questions

### Capability Registry

Discovers capabilities by:

- Name
- Command
- Intent
- Provided output
- Dependency
- Version

### Workflow Engine

Executes declarative dependency graphs, tracks step state, supports partial failure, and records run metadata.

### Modules

Each module owns its business logic, schemas, repositories, providers, tests, and migrations.

### Shared Platform

Includes:

- PostgreSQL
- Redis
- Object storage
- Event bus
- Logging
- Metrics
- Tracing
- Configuration
- Security services

## Failure Isolation

One module failure must not fail the complete response where partial output remains useful.

Example:

```text
Market data: completed
News: completed
Public sentiment: failed
Prediction: skipped
Response: completed with warning
```

## Deployment Strategy

Start as a modular monolith:

- Next.js frontend
- FastAPI backend
- Worker process
- PostgreSQL
- Redis

Split services only when scale, ownership, or reliability requires it.

## Implemented Foundation

The modular monolith uses one Python package and composition root. Platform code defines contracts and ports; modules supply capabilities through manifests; API handlers call application services through typed dependencies. The worker is a second process using the same codebase and Redis Streams adapter, not a separate service boundary.

Module startup is atomic: recursively discovered manifests and capability class entrypoints are validated in staging registries before registrations are committed. Duplicate registry keys, unresolved constructor dependencies, missing capabilities, and cycles fail startup. Capability constructors receive annotated platform ports or recursively constructed module-private services from the typed dependency resolver; no plugin factory or manual registration function exists.

All execution enters a transport-neutral pipeline through a typed command, intent, capability, or workflow request. The pipeline resolves a target, creates scoped execution contexts, applies permissions and retry policy, executes capabilities or compiled workflow layers, persists run state, and renders deterministic text plus response components. Exact manifest examples provide the initial intent resolver without embedding domain knowledge in the core.

Workflow steps receive only original input and explicitly declared dependency results. Independent steps run concurrently, optional failures become warnings, and required failures skip dependent steps. Context scopes bind and restore request/run identifiers and emit lifecycle events for every attempt.

Pydantic is the wire-contract source of truth. OpenAPI output generates TypeScript declarations, while Zod validators protect the rendering boundary. LangGraph remains uninstalled because the current DAG executor covers foundation behavior without coupling capability contracts to an orchestration framework.

## Conversation Runtime

Chat submission persists the session, user message, queued turn, and outbox record in one PostgreSQL transaction. The Redis worker claims each turn idempotently, builds a bounded conversation context, plans a command or intent, and invokes only registered targets. Memory mode uses the same orchestrator through a local background task.

Per-turn Redis Streams retain typed status, typing, progress, response-delta, component, warning, completion, and error events for 24 hours. SSE reconnects use `Last-Event-ID`; PostgreSQL remains authoritative after stream expiry. Anonymous browser UUID cookies isolate sessions until authentication is installed.

## Structured Market Data

`stock_market_data` depends only on normalized `MarketDataProvider`, the generic cache port, shared instrument contracts, and execution context. Provider calls are cache-aside; calculations always run in the module service over validated adjusted observations. Redis is the deployed cache adapter and memory is the deterministic test adapter. Provider failures never fall back to expired cache data.

The provider factory registers a category-specific unavailable facade for every empty provider chain. This keeps module loading atomic and capabilities discoverable while moving missing-provider failure to the invocation boundary as a typed HTTP 503 error. Explicitly configured but unknown provider names remain startup errors.

Command workflows resolve text through `instrument.resolve` using generic step input bindings. This preserves canonical cross-exchange identity without stock-aware branches in the platform or API composition root.

## Provider Runtime

Financially shaped provider ports live in `tradesentinel.providers`, beside rather than inside the domain-agnostic platform package. Module manifests may declare adapter class entrypoints; the provider bootstrap validates and stages these declarations before the ordinary capability loader constructs any capability. The application composition root is outside `platform` and is the only layer that joins provider selection to platform dependency injection.

Each category is configured as an ordered provider-name chain. A typed facade applies provider-scoped rate limits and timeouts, validates normalized Pydantic output, emits correlation-safe structured logs, and advances only after retryable availability failures. Permanent, authentication, configuration, licensing, invalid-output, and cancellation failures never trigger fallback. Provider failover makes one call per adapter; capability retry remains the outer idempotency boundary.

## Instrument Resolution

Canonical instrument contracts live outside both platform and the feature module, allowing future modules to exchange stable UUID-backed `InstrumentRef` values without private imports. The instrument module owns its repository and `market` catalog tables. A domain-neutral persistence resource lets its concrete repository factory select PostgreSQL or memory without composition-root knowledge of the feature.

Resolution normalizes text and applies fixed exact, prefix, and fuzzy similarity tiers. It surfaces tied cross-exchange matches as typed ambiguity rather than silently preferring an exchange. Module HTTP routers are optional manifest entrypoints loaded by a generic API adapter; the shared API and platform contain no instrument capability names.

## Deterministic Research

The `research` module depends only on `NewsProvider`, execution context, settings, and its module-owned repository. Its manifest owns six capabilities, `/news`, `/research`, `/sources`, two workflows, lifecycle events, and its API router. Empty news-provider configuration preserves startup and fails only at invocation with typed HTTP 503.

Articles remain untrusted. The module canonicalizes and deduplicates source metadata, conditionally retrieves documents from the originating provider, applies versioned phrase rules, and stores normalized events plus source-backed claims in the `research` schema. Reports are structured evidence indexes; there is no LLM, narrative synthesis, sentiment, recommendation, or inferred event date.

The `public_sentiment` module depends on the `SentimentProvider` port and the public `instrument.resolve` and `instrument.catalog` capabilities. Its manifest owns all eight processing capabilities, four commands, the complete workflow, lifecycle events, and its API router. No platform or central API code names a sentiment target. Empty sentiment-provider configuration preserves discovery and returns typed HTTP 503 only when collection is invoked.

## Deterministic technical analysis

`technical_analysis` is a stateless calculation module. Its manifest owns thirteen capabilities, twelve commands, twelve workflows, lifecycle events, and its API router. Resolution and cached market-history retrieval remain explicit workflow dependencies, so the module imports neither provider interfaces nor `stock_market_data` internals. Calculator methods are synchronous, side-effect-free, Decimal-based functions wrapped by async capabilities. The aggregate snapshot catches only typed insufficient-history failures and preserves all independently available sections as a partial response.

Workflow bindings may target either a nested result path or the complete `steps.<id>.data` object. Whole-result binding is required when a downstream capability consumes a validated shared contract such as `StockHistoryOutput`; the workflow executor still exposes only explicitly declared dependencies.

Each processing stage is a typed, independently executable service operation. Provider signal triples take precedence; incomplete or absent triples use a versioned deterministic lexicon. Spam removal precedes engagement weighting. Aggregation, narrative extraction, linear trend detection, and adjacent-window shift calculation are deterministic descriptions of observed discussions, never predictions.

## Deterministic fundamentals

`fundamentals` depends on public provider/domain contracts, the cache port, and execution contracts. Its manifest composes public instrument resolution/catalog and batch quote capabilities; Python code never imports their private implementations. Provider normalization, deterministic accounting calculations, capability wrappers, and thin routes remain separate. Missing fundamentals configuration is an execution-time 503, while missing market data preserves a partial reported-only valuation. See ADR 0020.

## YAML-driven stock overview

`stock_overview` is a composition module rather than a new analysis engine. Its manifest owns the dependency DAG, required/optional policy, command, route, lifecycle event, and ordered presentation sections. The platform compiles dependencies into concurrent layers and renders presentation metadata generically; neither platform nor central API code names an overview target or section order.

Instrument resolution, market retrieval, and technical calculation are required. Research, public sentiment, and fundamentals are optional branches whose typed failures become unavailable sections while usable core output is retained. Technical analysis consumes the same validated five-year history result, and fundamentals consumes the same quote result. See ADR 0021.
