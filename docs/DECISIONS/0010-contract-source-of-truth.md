# ADR 0010: Pydantic as Cross-Language Contract Source

## Status

Accepted

## Context

Python capabilities and the TypeScript web client must agree on evolving response and error shapes, including runtime validation.

## Decision

Pydantic models generate FastAPI OpenAPI and committed TypeScript declarations. The contracts workspace also exposes Zod validators at the frontend trust boundary. CI regenerates OpenAPI and fails on drift.

## Consequences

Backend contract changes are visible and reviewable, TypeScript consumers receive strict types, and malformed external data is rejected before rendering. Generated declarations must not be manually edited, and runtime Zod schemas must be updated alongside deliberate component-contract changes.
