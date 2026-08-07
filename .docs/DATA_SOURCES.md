# Data Sources

## Principles

- Use provider adapters.
- Do not expose raw provider responses.
- Every record must include provider and timestamp metadata.
- Licensing and redistribution rules must be reviewed before production use.
- Configure fallback providers where appropriate.

## Source Categories

- Market quotes
- Historical prices
- Corporate actions
- Company fundamentals
- Exchange announcements
- Financial news
- Public discussion
- Economic data
- Index and sector data

## Market Data Interface

```python
class MarketDataProvider:
    async def search_instruments(self, query: str): ...
    async def get_quote(self, instrument): ...
    async def get_history(self, instrument, period, interval): ...
    async def get_corporate_actions(self, instrument): ...
```

## News Interface

```python
class NewsProvider:
    async def search(self, instrument, start, end): ...
    async def get_document(self, source_id: str): ...
```

## Sentiment Interface

```python
class SentimentSourceProvider:
    async def collect_mentions(self, instrument, start, end): ...
```

## Required Metadata

- Provider name
- Original timestamp
- Retrieval timestamp
- Market timezone
- Symbol and exchange
- License or usage classification
- Freshness status
