# Data Sources and Provider Ports

The stock overview introduces no data source or provider adapter. It composes configured market-data, news, sentiment, and fundamentals facades through existing public capabilities. A provider-chain failure remains explicit in the affected section; data is never substituted across categories or synthesized by the overview.

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

No production adapters or credentials are included. Installed market-data and research modules are discoverable without adapters, but provider-backed executions fail safely with `PROVIDER_NOT_CONFIGURED` until external adapter manifests are discovered and selected.

News document requests carry the provider that produced the search result. The facade routes the request only to that adapter, preventing provider-local source identifiers from being sent to another vendor. Research stores normalized metadata, hashes, and bounded evidence excerpts rather than unrestricted article bodies.

Validated quote, history, and corporate-action responses are cached behind `CacheStore`. Default TTLs are 15 seconds, six hours, and 24 hours. Versioned cache keys include the normalized request and provider-chain fingerprint. Failures are never cached, invalid entries are evicted, and expired values are not served after provider failure.
## Public discussions

Public sentiment reads exclusively through `SentimentProvider`. Adapters normalize vendor observations; they do not aggregate, reinterpret, predict, or rank them. A complete provider-produced signal is retained with provider model metadata. Text-only or incomplete observations use the module's disclosed lexicon fallback. Provider/source weights are configuration, and chain failover retains the provider runtime's existing one-success semantics.
## Technical-analysis provenance

Technical calculations consume only the normalized output of `stock.history`. Provider identity, observation/retrieval timestamps, freshness, and cache hit/miss metadata propagate unchanged into `TechnicalSnapshot`. Raw OHLC is scaled by `adjusted_close / close`; invalid or missing adjustment data is rejected. The module never calls a provider or external API directly and never substitutes synthetic observations.

## Fundamentals provenance

`FundamentalsProvider` supplies normalized profiles, annual/quarterly statements, and dated facts. Adapters map vendor concepts to canonical identifiers and preserve unknown identifiers for disclosure. Profiles cache for 24 hours; statements/facts cache for 6 hours using provider-chain fingerprints. Current quotes remain a separate market-data capability. No production fundamentals adapter is bundled.
