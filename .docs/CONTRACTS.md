# Shared Contracts

## InstrumentRef

```json
{
  "instrument_id": "00000000-0000-4000-8000-000000000001",
  "symbol": "TCS",
  "name": "Tata Consultancy Services Limited",
  "exchange": "NSE",
  "asset_type": "equity",
  "currency": "INR",
  "aliases": ["Tata Consultancy Services", "Tata Consultancy"]
}
```

`InstrumentMatch` adds `confidence`, `matched_on`, and `matched_value`. Confidence is an auditable deterministic text-match score, never an LLM or prediction probability. `InstrumentResolveOutput` has a `resolved`, `ambiguous`, or `not_found` discriminator; ambiguous results include at least two ranked candidates and no selected match.

## Structured Market Data

Market outputs use `Decimal`, canonical `InstrumentRef`, UTC timestamps, provider metadata, explicit freshness, and cache provenance. History requires `adjusted_close` and declares `price_basis: adjusted`. Performance includes total return, CAGR, annualized log-return volatility, maximum drawdown, observation bounds, and rebased-to-100 series. These values are deterministic calculations, not probabilities or LLM output.

`StockComparisonOutput` preserves input order for two to ten unique same-currency instruments. `BenchmarkComparisonOutput` records the explicit benchmark, overlapping observation count, and excess total return/CAGR. Corporate actions use a closed normalized type enum and retain provider metadata.

## EvidenceSource

```json
{
  "source_id": "source_123",
  "provider": "approved_provider",
  "title": "Source title",
  "url": "https://example.com",
  "published_at": "ISO-8601",
  "retrieved_at": "ISO-8601",
  "source_type": "news",
  "reliability_weight": 0.85
}
```

## CapabilityResult

```json
{
  "capability": "sentiment.public",
  "status": "completed",
  "data": {},
  "summary": "",
  "sources": [],
  "warnings": [],
  "metadata": {
    "started_at": "ISO-8601",
    "completed_at": "ISO-8601"
  }
}
```

## SentimentSnapshot

```json
{
  "instrument": {
    "symbol": "TCS",
    "exchange": "NSE"
  },
  "window": "7d",
  "positive": 0.56,
  "neutral": 0.29,
  "negative": 0.15,
  "sentiment_change": 0.11,
  "discussion_volume_change": 0.27,
  "confidence": 0.71,
  "observed_at": "ISO-8601"
}
```

## PredictionResult

```json
{
  "prediction_id": "pred_123",
  "instrument": {
    "symbol": "TCS",
    "exchange": "NSE"
  },
  "generated_at": "ISO-8601",
  "data_cutoff": "ISO-8601",
  "horizon": "20d",
  "direction": "moderate_rise",
  "probabilities": {
    "rise": 0.61,
    "sideways": 0.24,
    "decline": 0.15
  },
  "confidence": 0.67,
  "model_version": "direction_nse_20d_v1"
}
```

## ResponseComponent

Supported types:

- summary_card
- metric_grid
- price_chart
- sentiment_chart
- news_timeline
- prediction_card
- scenario_table
- comparison_table
- risk_card
- source_list
- warning_banner

## Contract Governance

Backend Pydantic models are immutable, reject unknown fields, and version the API schema. Capability results use `completed`, `partial`, `failed`, or `skipped` lifecycle states; warnings are structured and evidence remains attached to the originating result. Execution context carries request, session, principal, workflow, capability, correlation, causation, locale, timezone, permission, and timestamp metadata.

The committed `packages/contracts/openapi.json` and generated TypeScript declarations are derived from FastAPI. Runtime Zod schemas validate every response component before presentation. `pnpm contracts:check` detects schema drift.

## Execution Contracts

`ExecutionRequest` is a discriminated union with `command`, `intent`, `capability`, and `workflow` variants. Each resolves to an `ExecutionTarget` and produces one `ExecutionOutcome` containing the raw capability/workflow result plus a `RenderedResponse`.

`RenderedResponse` contains deterministic plain text, ordered validated components, first-seen source deduplication, structured warnings, overall status, generation timestamp, run ID, and capability trace. `RetryPolicy` records bounded attempts, exponential delay, maximum delay, and jitter; additional attempts apply only to manifest-declared idempotent capabilities.

## Chat Contracts

`ChatSession`, `ChatMessage`, and `ChatTurn` are immutable records. Turns progress through `queued`, `planning`, `executing`, `rendering`, and a terminal `completed`, `partial`, or `failed` state. Assistant messages persist the complete `RenderedResponse`.

`ChatStreamEvent` is a versioned discriminated union with request, session, turn, correlation, run, sequence, and event identifiers. Variants are `status`, `typing`, `progress`, `response`, `component`, `warning`, `complete`, and `error`.
