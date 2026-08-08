# Data Sources and Provider Ports

## Boundaries

- Capabilities and services call typed provider interfaces; they never call external APIs directly.
- Vendor SDKs and HTTP clients are permitted only in module-local `providers/adapters` directories.
- Adapters validate and normalize vendor payloads and perform no analysis, ranking, scoring, recommendation, or aggregation.
- Raw provider responses never cross the adapter boundary.
- Retrieved news and social content is always marked untrusted.

## Interfaces

- `MarketDataProvider`: instrument search, quotes, price history, and corporate actions.
- `NewsProvider`: article search and full-document retrieval.
- `SentimentProvider`: source mention collection and vendor-produced sentiment observations. TradeSentinel does not calculate sentiment in this layer.
- `EconomicDataProvider`: economic-series search and dated observations.
- `FundamentalsProvider`: company profiles, reported statements, and reported facts.

Requests and results are immutable Pydantic contracts. Numeric market, economic, and fundamental values use `Decimal`; currency, unit, period, interval, exchange, and timestamps are explicit. Every returned record includes provider/source identity, observation and retrieval timestamps, timezone where relevant, license classification, and freshness.

## Configuration and Failover

The following environment settings accept ordered JSON arrays of manifest provider names:

```text
TRADESENTINEL_MARKET_DATA_PROVIDERS=[]
TRADESENTINEL_NEWS_PROVIDERS=[]
TRADESENTINEL_SENTIMENT_PROVIDERS=[]
TRADESENTINEL_ECONOMIC_DATA_PROVIDERS=[]
TRADESENTINEL_FUNDAMENTALS_PROVIDERS=[]
```

Empty categories receive a typed unavailable facade so modules remain discoverable and application startup succeeds. Invoking a capability that needs an empty category returns `PROVIDER_NOT_CONFIGURED` with HTTP 503. Unknown configured names still fail startup. Each configured adapter is attempted once. Availability, connection, timeout, and provider-rate-limit errors advance to the next configured name; permanent and invalid-output failures stop immediately.

No production adapters or credentials are included. The installed market-data module is discoverable without one, but its executions fail safely with `PROVIDER_NOT_CONFIGURED` until an external adapter manifest is discovered and selected.

Validated quote, history, and corporate-action responses are cached behind `CacheStore`. Default TTLs are 15 seconds, six hours, and 24 hours. Versioned cache keys include the normalized request and provider-chain fingerprint. Failures are never cached, invalid entries are evicted, and expired values are not served after provider failure.
