# ADR 0017: Deterministic Research Evidence

## Status

Accepted

## Context

TradeSentinel needs source-backed news events before an LLM or production news adapter exists. Retrieved content is untrusted, provider source identifiers may be local to one adapter, and confidence must not be confused with truth or prediction probability. Research events must remain inspectable and idempotently persisted.

## Decision

Implement research as a manifest-owned module using `NewsProvider`. Free-text searches are failover-based. Document retrieval carries provider affinity and occurs only when title and summary rules are insufficient, within a configured limit.

Use conservative deterministic deduplication and versioned phrase rules. Claims retain source, provider, evidence timestamp and basis, retrieval time, extraction confidence and basis, rule version, and a bounded excerpt. Unmatched articles remain source coverage but do not create generic events. Reports are structured evidence indexes without narrative generation.

Persist normalized sources, document hashes/metadata, events, event-source links, and claims in the module-owned `research` schema. Do not persist unrestricted document bodies.

## Consequences

Extraction is reproducible, auditable, safe to run without an LLM, and compatible with provider-free startup. Rule coverage is intentionally limited and surfaced through unmatched counts and warnings. Confidence measures rule strength only. Future statistical or LLM extractors must implement new versioned capabilities and preserve the same evidence invariants rather than silently changing `rules-v1` behavior.
