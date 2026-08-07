# ADR 0012: Durable Chat Turns and Resumable Streaming

## Status

Accepted

## Decision

Persist chat acceptance and an outbox record atomically in PostgreSQL, execute accepted turns through the Redis worker, and expose a replayable SSE stream per turn. Use a backend-issued anonymous browser UUID cookie until authentication exists. Natural-language fallback selection remains manifest-owned.

## Rationale

A browser or request disconnect must not cancel execution or lose history. PostgreSQL provides authoritative state, Redis Streams provide bounded low-latency replay, and `Last-Event-ID` provides reconnect semantics without WebSocket state. The transactional outbox closes the database-to-queue loss window, while idempotent claims tolerate duplicate delivery.

Execution receives the latest 20 messages by default, preventing unbounded capability inputs while full history remains persisted. The mock fallback proves the complete flow without adding LLM or market behavior.

## Consequences

The worker and Redis are required for durable Docker execution; memory mode uses an equivalent background runner. Stream events expire after 24 hours, after which clients retrieve the persisted turn and assistant message. Only one turn is active per session.
