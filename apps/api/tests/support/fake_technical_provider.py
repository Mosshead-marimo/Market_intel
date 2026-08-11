from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from tradesentinel.platform.config import Settings
from tradesentinel.providers.contracts import (
    PriceBar,
    PriceHistory,
    PriceHistoryRequest,
    ProviderContext,
)

from support.fake_market_provider import DeterministicMarketDataProvider, metadata


class TechnicalMarketDataProvider(DeterministicMarketDataProvider):
    async def get_history(
        self, context: ProviderContext, request: PriceHistoryRequest
    ) -> PriceHistory:
        del context
        interval_days = {"1d": 1, "1wk": 7, "1mo": 30}[request.interval]
        timestamps = []
        current = request.start
        while current <= request.end:
            timestamps.append(current)
            current += timedelta(days=interval_days)
        if timestamps[-1] != request.end:
            timestamps.append(request.end)
        bars = tuple(
            PriceBar(
                timestamp=timestamp,
                open=(value := Decimal("100") + Decimal(index) / Decimal("5")),
                high=value + Decimal("1.5"),
                low=value - Decimal("1.5"),
                close=value + Decimal(index % 5) / Decimal("10"),
                adjusted_close=value + Decimal(index % 5) / Decimal("10"),
                volume=Decimal(1000 + index),
            )
            for index, timestamp in enumerate(timestamps)
        )
        currency = "USD" if request.instrument.exchange in {"NASDAQ", "NYSE"} else "INR"
        return PriceHistory(
            instrument=request.instrument,
            interval=request.interval,
            currency=currency,
            bars=bars,
            metadata=metadata("technical-history", request.end),
        )


def technical_test_settings() -> Settings:
    tests_root = Path(__file__).parents[1]
    api_root = tests_root.parent
    return Settings(
        environment="test",
        persistence_backend="memory",
        event_backend="memory",
        cache_backend="memory",
        market_data_providers=("technical-market",),
        module_roots=(
            api_root / "src" / "tradesentinel" / "modules",
            tests_root / "fixtures" / "technical_provider",
        ),
    )
