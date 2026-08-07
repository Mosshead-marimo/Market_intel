# ADR 0002: Plugin Capability System

## Status

Accepted

## Context

New market-analysis features must be easy to add.

## Decision

Every feature is a registered capability with a manifest, typed contracts, dependencies, events, and tests.

## Consequences

Positive:

- Independent feature development
- Automatic command discovery
- Configurable workflows
- Better testability

Negative:

- Additional framework code
- Contract version management
