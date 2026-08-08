# ADR 0016: Lazy Unconfigured Provider Facades

## Status

Accepted

## Context

Failing process startup when an installed capability required an empty provider category prevented the API, worker, chat, instrument catalog, and system capabilities from running in provider-free environments. The stock market-data module intentionally ships without a vendor adapter, making the default Docker configuration impossible to start.

## Decision

The provider factory registers a typed unavailable facade for each empty provider category. Modules and capabilities load normally. Calling any method on that facade raises `PROVIDER_NOT_CONFIGURED` with HTTP 503 and the missing category in safe details. Explicit configuration that names an unknown or incompatible adapter continues to fail startup atomically.

## Consequences

The default stack starts without external credentials or synthetic market data. Capability and command discovery remains accurate, and unavailable execution is explicit at the request boundary. Operators still receive fail-fast validation for configuration mistakes that claim a specific adapter exists.
