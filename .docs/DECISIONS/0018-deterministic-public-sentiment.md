# ADR 0018: Deterministic public sentiment analysis

## Status

Accepted.

## Context

Public discussions are untrusted, noisy, privacy-sensitive, and may contain either a complete provider-produced sentiment signal or text alone. TradeSentinel needs auditable descriptive analysis without turning provider data, engagement, or language-model output into a prediction.

## Decision

The manifest-discovered `public_sentiment` module owns eight independently executable capabilities and one orchestration workflow. It obtains targets and the complete active catalog through public instrument capabilities. It never imports instrument-module internals.

A provider signal is accepted only as a complete, label-consistent label/score/confidence triple. Otherwise a versioned lexicon with three-token negation produces a deterministic score; unmatched text is `unknown` and excluded. Spam filtering runs before weighting. Weight is configured provider weight multiplied by configured source-type weight and an engagement factor capped at 1.5.

Snapshots compare equal adjacent windows. Narratives use a closed taxonomy and distinct-discussion n-grams. Trends use daily linear slopes. Shift combines observed score change and volume change using the documented bounded formula. These values describe evidence and never imply future price direction.

Normalized bounded excerpts and derived artifacts are persisted in the module-owned `sentiment` schema with deterministic identifiers. Author identifiers are hashed before persistence. Raw provider payloads and unrestricted text are not retained. No configured provider is a valid startup state; invocation fails with `PROVIDER_NOT_CONFIGURED`.

## Consequences

Every output is repeatable and independently testable, and configuration can change source weights without code changes. Lexicon results are intentionally less expressive than learned models and are disclosed by method/version. Full-catalog matching costs more than target-only matching but avoids hidden module coupling and preserves explicit cross-listing/co-mention evidence.
