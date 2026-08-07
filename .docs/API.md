# API Specification

## Core Endpoints

### Chat

```text
POST /api/v1/chat
GET  /api/v1/chat/sessions
GET  /api/v1/chat/sessions/{session_id}
```

### Commands

```text
POST /api/v1/commands/execute
GET  /api/v1/commands
GET  /api/v1/capabilities
```

### Runs

```text
GET /api/v1/runs/{run_id}
GET /api/v1/runs/{run_id}/sources
```

### Instruments

```text
GET /api/v1/instruments/search
GET /api/v1/instruments/{symbol}/quote
GET /api/v1/instruments/{symbol}/history
```

### Predictions

```text
POST /api/v1/predictions
GET  /api/v1/predictions/{prediction_id}
GET  /api/v1/predictions/{prediction_id}/evaluation
```

## Streaming

Use Server-Sent Events for chat progress and response streaming.

Example event types:

- status
- component
- warning
- response
- complete
- error

## Error Format

```json
{
  "error": {
    "code": "PROVIDER_UNAVAILABLE",
    "message": "Public sentiment is temporarily unavailable.",
    "retryable": true,
    "details": {}
  }
}
```

## Foundation Behavior

`GET /health/live`, `GET /health/ready`, command/capability discovery, `/ping` execution, system workflow execution, run inspection, and SSE contract exposure are active. All documented market, chat, and prediction routes are registered but return HTTP 501 with `CAPABILITY_NOT_INSTALLED` until their owning module is installed. This is a stable product boundary, not a placeholder response.

Every response includes `X-Request-ID`. Domain errors include the same UUID in the response body. The additional foundation endpoint `POST /api/v1/workflows/{workflow_name}/execute` executes a registered declarative workflow.

Command and workflow routes delegate to the shared execution pipeline. Their response retains the typed raw result and adds the deterministic rendered response with text, components, warnings, sources, status, trace, and run metadata.
