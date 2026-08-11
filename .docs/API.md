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
GET /api/v1/instruments/autocomplete
GET /api/v1/instruments/resolve
GET /api/v1/instruments/{symbol}/quote
GET /api/v1/instruments/{symbol}/history
POST /api/v1/market-data/quote
POST /api/v1/market-data/history
POST /api/v1/market-data/performance
POST /api/v1/market-data/comparison
POST /api/v1/market-data/corporate-actions
POST /api/v1/market-data/five-year-performance
POST /api/v1/market-data/benchmark-comparison

POST /api/v1/technical/snapshot
POST /api/v1/technical/rsi
POST /api/v1/technical/macd
POST /api/v1/technical/ema
POST /api/v1/technical/sma
POST /api/v1/technical/atr
POST /api/v1/technical/adx
POST /api/v1/technical/support
POST /api/v1/technical/resistance
POST /api/v1/technical/trend
POST /api/v1/technical/momentum
POST /api/v1/technical/volatility
```

### Research

```text
GET  /api/v1/research/news
POST /api/v1/research/timeline
POST /api/v1/research/reports
GET  /api/v1/research/events/{event_id}/evidence

POST /api/v1/sentiment/analyze
POST /api/v1/sentiment/discussions/collect
POST /api/v1/sentiment/spam/remove
POST /api/v1/sentiment/companies/detect
POST /api/v1/sentiment/sources/weight
POST /api/v1/sentiment/aggregate
POST /api/v1/sentiment/narratives
POST /api/v1/sentiment/trend
POST /api/v1/sentiment/shift
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

`POST /api/v1/chat` returns HTTP 202 with a durable turn and per-turn stream URL. The stream replays after `Last-Event-ID`, sends heartbeats every 15 seconds, and closes on `complete` or `error`. Session operations are scoped to the anonymous browser principal. Instrument, market-data, deterministic research, and public-sentiment routes are installed; prediction routes continue to return typed HTTP 501 `CAPABILITY_NOT_INSTALLED` responses. With no configured sentiment provider, public-sentiment invocation returns typed HTTP 503 `PROVIDER_NOT_CONFIGURED`.

Every response includes `X-Request-ID`. Domain errors include the same UUID in the response body. The additional foundation endpoint `POST /api/v1/workflows/{workflow_name}/execute` executes a registered declarative workflow.

Command and workflow routes delegate to the shared execution pipeline. Their response retains the typed raw result and adds the deterministic rendered response with text, components, warnings, sources, status, trace, and run metadata.

Instrument endpoints accept `q`, optional `exchange` and `asset_type`, and bounded `limit` where applicable. Resolve returns HTTP 200 with `resolved`, `ambiguous`, or `not_found`; ambiguity is data rather than a transport error.

Symbol quote/history routes resolve the instrument through manifest workflows. `/market-data` POST routes accept canonical references and return typed contracts. Comparison accepts two to ten instruments; benchmark comparison always requires an explicit benchmark.

When no market-data adapter is configured, discovery and readiness remain available. Market-data execution returns HTTP 503 with `PROVIDER_NOT_CONFIGURED` and `details.kind: market_data`; no synthetic or stale value is substituted.

Technical POST endpoints accept a query, optional exchange, interval and formula overrides. An omitted range defaults to one calendar year ending at `as_of` or current UTC time; explicit `start` and `end` must be supplied together. The endpoints execute manifest workflows and inherit canonical ambiguity, provider-unconfigured, invalid-history, and insufficient-history errors. Snapshot responses preserve partial calculations instead of converting missing sections into transport failures.

Research search accepts free-text `q`, optional UTC `start`/`end`, and a bounded `limit`. Reports run the manifest workflow and return coverage, duplicate groups, events, source-backed claims, sources, and warnings. Missing news configuration returns HTTP 503 with `details.kind: news`.

## Fundamentals

Pipeline-backed POST routes under `/api/v1/fundamentals` expose snapshot, revenue, profit, cash-flow, debt, margins, ROE, ROCE, valuation, growth, and peer comparison. Bodies accept `query`, optional `exchange`/`as_of`, annual and quarterly limits, and explicit peers where applicable. Missing fundamentals providers return `503 PROVIDER_NOT_CONFIGURED`; missing quotes return successful partial valuation.
