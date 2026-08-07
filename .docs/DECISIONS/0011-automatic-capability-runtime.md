# ADR 0011: Manifest-Owned Automatic Capability Runtime

## Status

Accepted

## Context

The initial foundation required each module to provide a plugin factory that repeated capability, command, and workflow registration already represented by its manifest. It also left command, workflow, and direct capability execution on separate paths.

## Decision

Make strict manifests the sole registration source. Each capability declaration names a concrete capability class entrypoint. The loader recursively discovers manifests, constructs classes through typed dependency resolution, validates all capability/command/intent/workflow/event targets in staging registries, and commits atomically.

All command, exact-intent, direct capability, workflow, and event-triggered requests use one transport-neutral execution pipeline. Scoped contexts, permissions, safe retries, persistence, lifecycle events, error normalization, and deterministic text/component rendering apply consistently.

## Consequences

Adding a feature requires no core edits or plugin factory, registration metadata cannot drift between Python and YAML, and execution behavior is consistent across transports. Startup is intentionally strict: malformed manifests, invalid classes, unresolved constructor dependencies, or graph errors prevent the application from starting. Manifest class entrypoints are trusted local code; external content is never used for imports or execution.
