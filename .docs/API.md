# API Specification

## Core Endpoints

### Chat

```text
POST /api/v1/chat
POST /api/v1/chat/sessions
GET  /api/v1/chat/sessions
GET  /api/v1/chat/sessions/{session_id}
PATCH /api/v1/chat/sessions/{session_id}
GET  /api/v1/chat/turns/{turn_id}
GET  /api/v1/chat/turns/{turn_id}/events
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
- typing
- progress
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

`POST /api/v1/chat` returns HTTP 202 with a durable turn and per-turn stream URL. The stream replays after `Last-Event-ID`, sends heartbeats every 15 seconds, and closes on `complete` or `error`. Session operations are scoped to the anonymous browser principal. Market and prediction routes continue to return typed HTTP 501 `CAPABILITY_NOT_INSTALLED` responses.

Every response includes `X-Request-ID`. Domain errors include the same UUID in the response body. The additional foundation endpoint `POST /api/v1/workflows/{workflow_name}/execute` executes a registered declarative workflow.

Command and workflow routes delegate to the shared execution pipeline. Their response retains the typed raw result and adds the deterministic rendered response with text, components, warnings, sources, status, trace, and run metadata.
