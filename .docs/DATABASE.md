# Database Design

## Assistant schema

Migration `0007_llm_audit` owns `assistant.generations`. It is a metadata ledger rather than a prompt archive. Chat messages remain the authoritative approved response.

## Primary Store

PostgreSQL is the primary database. TimescaleDB may be used for time-series workloads and pgvector for semantic retrieval.

## Schemas

- `core`
- `market`
- `research`
- `sentiment`
- `technical`
- `fundamental`
- `prediction`
- `portfolio`
- `audit`

## Core Tables

- users
- chat_sessions
- chat_messages
- capability_runs
- workflow_runs

## Market Tables

- instruments
- instrument_aliases
- exchanges
- prices
- corporate_actions
- benchmark_memberships

## Research Tables

- sources
- documents
- events
- claims

## Sentiment Tables

- documents
- snapshots
- topics
- narratives
- source_scores

## Prediction Tables

- model_versions
- predictions
- prediction_features
- prediction_scenarios
- prediction_outcomes
- model_metrics

## Ownership Rule

A module may write only to its assigned schema. Cross-module access should use repositories, capability calls, events, or approved read models.

## Migration Rule

- Use Alembic.
- Migrations must be reversible where practical.
- Data-destructive migrations require explicit approval.
- Module migrations remain in the module directory but execute through the central migration runner.

## Foundation Migration

Revision `0001_platform_core` creates only `core` and `audit`. It includes chat/session records, workflow and capability runs, workflow step state, event-delivery idempotency records, and dead letters. No financial-domain schema is created. API routes use repository interfaces; SQLAlchemy models and sessions remain in the persistence adapter.

Revision `0002_chat_runtime` adds ordered message state, rendered assistant responses, archive metadata, durable chat turns, one-active-turn enforcement, and the transactional chat outbox. PostgreSQL retains final history while Redis retains short-lived SSE replay data.

Revision `0003_chat_worker_leases` adds attempt counters and renewable worker leases. An abandoned non-terminal turn becomes claimable after its lease expires, so Redis at-least-once delivery cannot leave a session permanently blocked.

Revision `0004_instrument_catalog` creates the module-owned `market.exchanges`, `market.instruments`, and `market.instrument_aliases` tables with normalized lookup indexes and canonical uniqueness constraints. It seeds 16 explicitly labeled `builtin_seed_v1` equity listings across NSE, BSE, NASDAQ, and NYSE. The migration is reversible and removes only the instrument catalog schema it creates.

Revision `0005_research_events` creates module-owned `research.sources`, `research.documents`, `research.events`, `research.event_sources`, and `research.claims`. Deterministic identifiers and uniqueness constraints make extraction idempotent. Documents retain metadata and hashes, while claims retain bounded excerpts and complete source/provider/timestamp/confidence provenance.

Revision `0006_public_sentiment` creates the module-owned `sentiment` tables for bounded normalized discussions, spam decisions, company mentions, source weights, snapshots, narratives, trends, and shifts. Provider/source identifiers and deterministic UUIDs make retries idempotent. Author identifiers are SHA-256 hashed before persistence and unrestricted provider payloads are never stored.

Technical analysis is intentionally stateless and adds no migration or `technical` tables. It reuses cached normalized market history and standard platform run records; calculated indicators are returned in run results rather than written through a module repository.

Fundamentals is cache-only and adds no migration or schema. Profiles, statements, and facts use bounded TTL caches; calculated sections are returned through normal run results. Durable financial-statement storage remains outside this increment.
