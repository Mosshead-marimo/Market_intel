# ADR 0019: Deterministic technical analysis

## Status

Accepted.

## Decision

TradeSentinel implements technical indicators in a manifest-discovered, stateless `technical_analysis` module. The module consumes the shared `StockHistoryOutput` contract through explicit workflow bindings to `stock.history`; it does not import the market-data module, provider ports, HTTP clients, or database adapters. Whole-result workflow binding is supported so validated shared contracts can cross capability boundaries without lossy field-by-field mapping.

All calculations use Python `Decimal` and adjusted OHLC derived with `adjusted_close / close`. Defaults are versioned as `technical-v1` and can be overridden through validated inputs. RSI, ATR, and ADX use Wilder smoothing; EMA and MACD use SMA seeding. Support and resistance combine rolling extrema with local pivots clustered at one-half ATR by default. Trend, momentum, and volatility labels describe observed history and are never forecasts or recommendations.

Direct indicator capabilities fail with `TECHNICAL_INSUFFICIENT_HISTORY`. The aggregate snapshot catches only that typed condition, leaves unavailable sections null, and returns explicit partial/empty status and warnings. Invalid normalized data and provider failures remain terminal and are never hidden by partial rendering.

## Consequences

- Formula behavior is reproducible, independently testable, and independent of AI or vendor implementations.
- Provider and cache provenance crosses the history contract into every aggregate snapshot.
- The module adds no persistence schema; recomputation is deterministic over cached normalized history.
- More observations are returned because full indicator series are part of the public snapshot contract.
