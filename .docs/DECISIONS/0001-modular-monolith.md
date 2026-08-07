# ADR 0001: Modular Monolith

## Status

Accepted

## Context

The project needs strong module boundaries without early microservice complexity.

## Decision

Use a modular monolith for the MVP.

## Consequences

Positive:

- Simpler deployment
- Easier local development
- Shared transactions
- Lower operational overhead

Negative:

- Boundaries require discipline
- Heavy modules may later require extraction
