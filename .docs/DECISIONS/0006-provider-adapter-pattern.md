# ADR 0006: Provider Adapter Pattern

## Status

Accepted

## Decision

All external data providers must implement internal interfaces. Provider SDKs remain isolated inside adapters.

## Rationale

This reduces vendor lock-in and simplifies fallback providers, testing, and licensing changes.
