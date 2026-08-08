# ADR 0013: Manifest-Driven Provider Runtime

> Amended by ADR 0016: empty provider categories now use lazy unavailable facades instead of failing module startup.

## Status

Accepted

## Context

Capabilities need replaceable external data sources without importing vendor clients, duplicating selection logic, or adding financial concepts to the shared platform. Provider failures also need constrained fallback without hiding permanent configuration or data-quality problems.

## Decision

Place typed financial provider ports and normalized contracts in the sibling `tradesentinel.providers` package. Module manifests own adapter declarations. A provider bootstrap stages adapter imports, validates class-kind compatibility, resolves configuration-selected chains, registers typed facades with dependency injection, and then invokes the existing capability loader. Provider and capability registrations commit only after the complete startup graph succeeds.

Configuration supplies an ordered name chain for each of market data, news, sentiment, economic data, and fundamentals. Facades enforce per-adapter timeouts, rate limits, output validation, and correlation-safe logging. They advance only for typed retryable availability failures and never retry within an adapter. Capability retry remains the outer idempotent boundary.

## Consequences

Changing vendors or fallback order requires configuration and restart only. Capabilities depend exclusively on stable internal ports, vendor SDKs remain isolated in adapters, and normalized data cannot silently contain raw vendor structures. Empty categories allow the foundation to run without vendors, while a capability requiring an unconfigured port fails startup. The composition root must remain outside `platform` because it is the intentional boundary that knows both platform infrastructure and provider-domain ports.
