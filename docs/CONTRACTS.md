# Shared Contracts

## InstrumentRef

```json
{
  "symbol": "TCS",
  "exchange": "NSE",
  "asset_type": "equity",
  "currency": "INR"
}
```

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
