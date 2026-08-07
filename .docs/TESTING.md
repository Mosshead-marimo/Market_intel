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
