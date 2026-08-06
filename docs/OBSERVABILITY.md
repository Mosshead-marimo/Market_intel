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
