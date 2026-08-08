# ADR 0015: Provider-Backed Structured Market Data

> Amended by ADR 0016: missing provider configuration now fails at capability invocation rather than application startup.

## Status

Accepted

## Decision

Market-data capabilities depend on normalized `MarketDataProvider`. No live or synthetic production adapter is bundled. Quotes, adjusted history, and corporate actions use a generic cache-aside port with memory and Redis implementations. Performance calculations remain module business logic and require adjusted closes.

Commands resolve canonical instruments through declarative workflow input bindings. Benchmarks are explicit and comparisons never infer an exchange or index. Capabilities return structured data only; generic execution envelopes remain transport concerns.

## Consequences

Provider replacement remains configuration-only and vendor code stays outside capabilities. Missing configuration remains explicit through a typed execution error while unrelated application features stay available. Cached data retains provider timestamps, invalid entries are evicted, and stale values are not used as an availability fallback.
