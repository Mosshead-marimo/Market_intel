# Database Design

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
