# Testing Strategy

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
