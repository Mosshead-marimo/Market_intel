"""Typed external-provider ports and runtime selection."""

from tradesentinel.providers.interfaces import (
    EconomicDataProvider,
    FundamentalsProvider,
    MarketDataProvider,
    NewsProvider,
    SentimentProvider,
)

__all__ = [
    "EconomicDataProvider",
    "FundamentalsProvider",
    "MarketDataProvider",
    "NewsProvider",
    "SentimentProvider",
]
