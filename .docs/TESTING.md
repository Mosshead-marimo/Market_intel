# Testing Strategy

## LLM assistant

Tests use deterministic fake providers and never call vendors. Coverage includes planner constraints, command execution, failover, evidence extraction and policy enforcement, repair and partial behavior, audit privacy, provider-free failure, SSE ordering, citation rendering, and clickable follow-ups.

Stock-overview tests verify leap-day five-year windows, strict YAML presentation references, duplicate-section rejection, deterministic DAG layers, branch concurrency, one-time resolution, input reuse, required/optional failure behavior, command/API execution, ordered reusable components, completion-event metadata, and provider-free typed errors. Architecture tests reject overview names/order in platform and central API code and prohibit external I/O, AI libraries, persistence, and private cross-module imports in the composition module.

## Test Layers

- Unit tests
- Contract tests
- Capability tests
- Workflow tests
- Provider adapter tests
- Repository tests
- Integration tests
- End-to-end tests
- Model tests
- Prompt safety tests
- Security tests

## Capability Test Requirements

Every capability must test:

- Valid input
- Invalid input
- Missing required data
- Stale data
- Provider failure
- Partial provider response
- Output schema validation
- Source propagation
- Warning propagation

## Workflow Tests

Test:

- Correct dependency order
- Optional-step failure
- Required-step failure
- Retry behavior
- Partial-success rendering
- Run tracking

## Prediction Tests

Test:

- No future leakage
- Probability sum validation
- Model-version persistence
- Confidence threshold behavior
- Calibration calculations
- Outcome evaluation

## Foundation Test Commands

`uv run pytest` covers strict manifest parsing, recursive discovery, class imports, typed autowiring, atomic loading, registries, command/intent resolution, context restoration, retries, event handling, workflow layers and failure policy, deterministic rendering, all execution request variants, API behavior, persistence ports, and architecture rules. Architecture tests forbid plugin factories, manual API dispatch, platform-to-module imports, and module-specific core conditionals.

`pnpm test` covers runtime response validation and rendering. Strict mypy, Ruff, ESLint, TypeScript, OpenAPI drift, Next.js production build, Alembic offline generation, and Docker Compose validation form the remaining foundation gates. PostgreSQL/Redis integration tests run against the Compose services in environments with Docker available.

Chat coverage includes planner routing, fallback selection, bounded context, ownership, idempotency, active-turn enforcement, archive behavior, outbox delivery, stream ordering/replay, safe errors, reducer deduplication, typing/progress states, session restoration, and Docker execution through the Redis worker.

Provider coverage validates all five interface mappings, strict normalized contracts, manifest class imports, class-kind compatibility, deterministic and duplicate-safe registration, configuration-only selection, dependency injection, atomic rollback, ordered fallback, timeouts, rate limits, exhaustion, permanent failures, invalid output, and cancellation. Architecture checks prevent external clients outside adapter directories and prevent provider-domain imports from entering the platform package.

Instrument coverage validates Unicode normalization, exact/prefix/fuzzy score tiers, aliases, partial names, typo tolerance, stable ordering, exchange and asset filters, typed ambiguity, not-found results, memory/PostgreSQL seed parity, commands, automatic router discovery, HTTP contracts, and reversible migration behavior.

Stock market-data coverage uses a deterministic test-only provider. Tests cover adjusted-history validation, Decimal calculations, cache adapters and TTLs, comparison order, benchmark overlap, leap-day five-year windows, lazy missing-provider behavior, all seven commands, structured endpoints, and architecture boundaries. Production code contains no synthetic adapter.

Research coverage uses a deterministic test-only news provider. Tests cover evidence invariants, URL/title deduplication, all confidence tiers, conditional provider-affine document retrieval, unmatched sources, partial failures, persistence/evidence lookup, automatic discovery, workflows, commands, HTTP contracts, and provider-free HTTP 503 behavior. Production contains no news adapter or LLM dependency.
Public-sentiment unit tests exercise each deterministic stage, including provider/lexicon precedence, negation, explicit unknown values, every spam rule, privacy hashing, full-catalog detection, capped engagement weighting, empty and partial aggregation, taxonomy and n-gram narratives, trend regression, shift bounds, automatic discovery, and provider-free HTTP 503 behavior. PostgreSQL migration checks must upgrade and downgrade revision `0006_public_sentiment`.

Technical-analysis tests use fixed rising, falling, flat, gapped, volatile, and adjustment-aware histories. They cover seeded EMA/MACD alignment, Wilder RSI/ATR/ADX, ROC, annualization, percentile regimes, rolling extrema, pivot clustering, warm-up failures, partial/empty snapshots, leap-day windows, manifest discovery, every route/command boundary, provider-free HTTP 503, OpenAPI drift, strict Zod validation, and architecture prohibitions on AI, external I/O, provider SDKs, databases, and private market-module imports.

Fundamentals tests cover fiscal contracts, provider normalization, cache hits/validation, accounting formulas, TTM and annual fallback, partial/empty states, current/reported valuation separation, explicit and automatic peers, medians/percentiles, manifest discovery, routes, lazy 503 behavior, generated/Zod contracts, and architecture boundaries. Deterministic adapters remain test-only.
