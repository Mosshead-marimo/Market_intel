# Observability

## Identifiers

Every request should include:

- request_id
- session_id
- workflow_run_id
- capability_run_id
- prediction_id where applicable

## Logs

Use structured JSON logs with:

- timestamp
- level
- service
- module
- capability
- duration
- status
- provider
- error code

## Metrics

- chat_request_duration
- capability_execution_duration
- provider_failure_count
- provider_latency
- workflow_partial_success_count
- prediction_generation_count
- prediction_calibration_error
- sentiment_pipeline_failure_count
- research_source_count
- llm_token_usage
- analysis_cost

## Tracing

Trace:

- API request
- Workflow plan
- Capability steps
- Provider calls
- Database operations
- LLM calls
- Response rendering

## Foundation Implementation

HTTP middleware propagates or generates UUID request IDs and binds them through context variables. Logs are structured JSON and redact keys associated with authorization, tokens, API keys, passwords, and secrets. Workflow and capability lifecycle events carry correlation and causation IDs; persisted runs retain timestamps, status, warnings, and evidence metadata.

Chat logs and stream envelopes carry session, turn, request, correlation, and run identifiers. Observable turn stages are queued, planning, executing, rendering, and terminal status. Outbox and worker failures log typed codes and identifiers rather than message history or browser cookies.

Provider facades log `provider_call_completed`, `provider_call_unavailable`, or `provider_call_failed` with provider kind, configured provider name, operation, duration, request ID, capability run ID, and safe error code. Provider request bodies, normalized records, raw vendor responses, and credentials are deliberately excluded.

## Market Data Cache

Market-data cache logs record only operation and hit/miss/invalid outcome. Cache keys, request payloads, provider responses, symbols, and credentials are not logged. Structured output metadata carries provider, retrieval, freshness, cache time, and expiry for request-level inspection.

## Research Evidence

Research lifecycle events report source, duplicate, event, persistence, and report counts with request/run correlation. Provider calls retain the standard safe metadata. Article titles, summaries, documents, excerpts, URLs, and query payloads are excluded from structured logs.
