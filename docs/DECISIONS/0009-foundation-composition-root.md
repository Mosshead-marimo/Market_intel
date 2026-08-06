# ADR 0009: Foundation Workspace and Composition Root

## Status

Accepted

## Context

The modular monolith needs strict boundaries while remaining runnable as an API and worker from one codebase.

## Decision

Use a uv-managed Python package in `apps/api`, a pnpm-managed Next.js application in `apps/web`, and a single typed composition root. The root constructs infrastructure adapters, repositories, registries, the loader, and executor; transport handlers receive them through dependency injection. Modules are discovered from validated manifests and cannot be imported by the platform layer.

## Consequences

The runtime is easy to test with in-memory adapters and deploy with PostgreSQL/Redis adapters. Boundary discipline is automatically testable. Startup intentionally fails on invalid plugin graphs rather than accepting a partially registered application.
