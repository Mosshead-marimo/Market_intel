from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from support.fake_market_provider import DeterministicMarketDataProvider
from tradesentinel.domain.instruments import InstrumentRef
from tradesentinel.domain.market_data import (
    BenchmarkComparisonInput,
    CacheDisposition,
    FiveYearPerformanceInput,
    MarketInterval,
    StockComparisonInput,
    StockHistoryInput,
    StockPerformanceInput,
    StockQuoteInput,
)
from tradesentinel.modules.instrument_resolution.seed import SEED_INSTRUMENTS
from tradesentinel.modules.stock_market_data.errors import InsufficientHistoryError
from tradesentinel.modules.stock_market_data.service import StockMarketDataService
from tradesentinel.platform.cache import CacheStore, InMemoryCacheStore
from tradesentinel.platform.config import Settings
from tradesentinel.platform.contracts import ExecutionContext
from tradesentinel.providers.contracts import MarketQuote, PriceBar, ProviderContext, QuoteRequest
from tradesentinel.providers.errors import ProviderNotConfiguredError, ProviderUnavailableError


def _instrument(symbol: str, exchange: str = "NSE") -> InstrumentRef:
    return next(
        item.to_ref()
        for item in SEED_INSTRUMENTS
        if item.symbol == symbol and item.exchange == exchange
    )


def _service(
    provider: DeterministicMarketDataProvider | None = None,
) -> StockMarketDataService:
    return StockMarketDataService(
        provider or DeterministicMarketDataProvider(),
        InMemoryCacheStore(),
        Settings(market_data_providers=("test-market",)),
    )


def _range() -> tuple[datetime, datetime]:
    return datetime(2025, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC)


def test_contracts_reject_invalid_ranges_duplicates_and_unadjusted_bars() -> None:
    instrument = _instrument("TCS")
    start, end = _range()
    with pytest.raises(ValidationError, match="start must be before end"):
        StockHistoryInput(instrument=instrument, start=end, end=start)
    with pytest.raises(ValidationError, match="unique"):
        StockComparisonInput(instruments=(instrument, instrument), start=start, end=end)
    with pytest.raises(ValidationError, match="adjusted_close"):
        PriceBar.model_validate(
            {
                "timestamp": start,
                "open": "10",
                "high": "11",
                "low": "9",
                "close": "10",
            }
        )


async def test_quote_is_structured_and_cached() -> None:
    DeterministicMarketDataProvider.quote_calls = 0
    service = _service()
    request = StockQuoteInput(instrument=_instrument("TCS"))
    first = await service.quote(ExecutionContext(), request)
    second = await service.quote(ExecutionContext(), request)
    assert first.price == Decimal("110")
    assert first.change == Decimal("10")
    assert first.change_percent == Decimal("0.1")
    assert first.cache.disposition == CacheDisposition.MISS
    assert second.cache.disposition == CacheDisposition.HIT
    assert DeterministicMarketDataProvider.quote_calls == 1


class CorruptCache(CacheStore):
    def __init__(self) -> None:
        self.value: bytes | None = b"not-json"

    async def get(self, key: str) -> bytes | None:
        del key
        return self.value

    async def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        del key, ttl_seconds
        self.value = value

    async def delete(self, key: str) -> None:
        del key
        self.value = None


async def test_corrupt_cache_is_evicted_and_provider_failures_are_not_cached() -> None:
    cache = CorruptCache()
    service = StockMarketDataService(
        DeterministicMarketDataProvider(),
        cache,
        Settings(market_data_providers=("test-market",)),
    )
    result = await service.quote(ExecutionContext(), StockQuoteInput(instrument=_instrument("TCS")))
    assert result.cache.disposition == CacheDisposition.MISS
    assert cache.value is not None and cache.value != b"not-json"

    class UnavailableProvider(DeterministicMarketDataProvider):
        async def get_quote(self, context: ProviderContext, request: QuoteRequest) -> MarketQuote:
            del context, request
            raise ProviderUnavailableError("test-market")

    empty_cache = InMemoryCacheStore()
    unavailable = StockMarketDataService(
        UnavailableProvider(),
        empty_cache,
        Settings(market_data_providers=("test-market",)),
    )
    with pytest.raises(ProviderUnavailableError):
        await unavailable.quote(ExecutionContext(), StockQuoteInput(instrument=_instrument("TCS")))


async def test_performance_uses_adjusted_prices_and_is_deterministic() -> None:
    start, end = _range()
    result = await _service().performance(
        ExecutionContext(),
        StockPerformanceInput(
            instrument=_instrument("TCS"),
            start=start,
            end=end,
            interval=MarketInterval.DAILY,
        ),
    )
    assert result.metrics.total_return == Decimal("0.21")
    assert result.metrics.maximum_drawdown == Decimal("-0.1")
    assert result.metrics.observations == 3
    assert [point.value for point in result.series] == [
        Decimal("100"),
        Decimal("90.0"),
        Decimal("121.00"),
    ]
    assert result.metrics.cagr > Decimal("0.20")
    assert result.metrics.annualized_volatility > 0


async def test_comparison_and_benchmark_use_canonical_order_and_overlap() -> None:
    start, end = _range()
    service = _service()
    comparison = await service.compare(
        ExecutionContext(),
        StockComparisonInput(
            instruments=(_instrument("TCS"), _instrument("INFY")),
            start=start,
            end=end,
        ),
    )
    assert [item.instrument.symbol for item in comparison.items] == ["TCS", "INFY"]

    benchmark = await service.benchmark_comparison(
        ExecutionContext(),
        BenchmarkComparisonInput(
            instrument=_instrument("TCS"),
            benchmark=_instrument("INFY"),
            start=start,
            end=end,
        ),
    )
    assert benchmark.overlapping_observations == 3
    assert benchmark.excess_total_return == 0
    assert benchmark.excess_cagr == 0


async def test_five_year_leap_day_and_insufficient_history() -> None:
    service = _service()
    result = await service.five_year_performance(
        ExecutionContext(),
        FiveYearPerformanceInput(
            instrument=_instrument("TCS"),
            as_of=datetime(2024, 2, 29, tzinfo=UTC),
        ),
    )
    assert result.effective_start == datetime(2019, 2, 28, tzinfo=UTC)

    with pytest.raises(InsufficientHistoryError):
        StockMarketDataService._calculate((), MarketInterval.DAILY)


async def test_market_data_capability_is_discoverable_without_a_provider() -> None:
    from tradesentinel.container import build_container
    from tradesentinel.platform.contracts import CapabilityExecutionRequest

    container = build_container(
        Settings(
            environment="test",
            persistence_backend="memory",
            event_backend="memory",
            cache_backend="memory",
        )
    )
    try:
        assert container.capabilities.get("stock.quote")
        with pytest.raises(ProviderNotConfiguredError):
            await container.pipeline.execute(
                CapabilityExecutionRequest(
                    capability="stock.quote",
                    payload={"instrument": _instrument("TCS").model_dump(mode="json")},
                )
            )
    finally:
        await container.close()


async def test_manifest_registers_every_capability_command_and_route(client: AsyncClient) -> None:
    capabilities = {item["name"] for item in (await client.get("/api/v1/capabilities")).json()}
    assert {
        "stock.quote",
        "stock.history",
        "stock.performance",
        "stock.comparison",
        "stock.corporate_actions",
        "stock.performance.five_year",
        "stock.benchmark.comparison",
    } <= capabilities
    commands = {item["name"] for item in (await client.get("/api/v1/commands")).json()}
    assert {
        "/quote",
        "/history",
        "/performance",
        "/compare",
        "/corporate-actions",
        "/five-year-performance",
        "/benchmark-compare",
    } <= commands

    openapi = (await client.get("/openapi.json")).json()
    assert "/api/v1/market-data/benchmark-comparison" in openapi["paths"]
    assert "/api/v1/instruments/{symbol}/quote" in openapi["paths"]


async def test_direct_structured_endpoints(client: AsyncClient) -> None:
    start, end = _range()
    instrument = _instrument("TCS").model_dump(mode="json")
    second = _instrument("INFY").model_dump(mode="json")
    period = {"start": start.isoformat(), "end": end.isoformat(), "interval": "1d"}

    requests = (
        ("/api/v1/market-data/quote", {"instrument": instrument}),
        ("/api/v1/market-data/history", {"instrument": instrument, **period}),
        ("/api/v1/market-data/performance", {"instrument": instrument, **period}),
        (
            "/api/v1/market-data/comparison",
            {"instruments": [instrument, second], **period},
        ),
        (
            "/api/v1/market-data/corporate-actions",
            {"instrument": instrument, "start": start.isoformat(), "end": end.isoformat()},
        ),
        (
            "/api/v1/market-data/five-year-performance",
            {"instrument": instrument, "as_of": end.isoformat()},
        ),
        (
            "/api/v1/market-data/benchmark-comparison",
            {"instrument": instrument, "benchmark": second, **period},
        ),
    )
    responses = [await client.post(path, json=payload) for path, payload in requests]
    assert [response.status_code for response in responses] == [200] * 7
    assert responses[0].json()["provider"]["provider"] == "test-market"
    assert responses[2].json()["metrics"]["total_return"] == "0.21"
    assert responses[4].json()["actions"][0]["action_type"] == "dividend"


async def test_commands_resolve_instruments_with_declarative_bindings(
    client: AsyncClient,
) -> None:
    start, end = _range()
    commands = (
        "/quote TCS --exchange NSE",
        f"/history TCS {start.isoformat()} {end.isoformat()} --exchange NSE",
        f"/performance TCS {start.isoformat()} {end.isoformat()} --exchange NSE",
        f"/compare TCS INFY {start.isoformat()} {end.isoformat()} --exchange NSE "
        "--comparison-exchange NSE",
        f"/corporate-actions TCS {start.isoformat()} {end.isoformat()} --exchange NSE",
        f"/five-year-performance TCS --exchange NSE --as-of {end.isoformat()}",
        f"/benchmark-compare TCS INFY {start.isoformat()} {end.isoformat()} --exchange NSE "
        "--benchmark-exchange NSE",
    )
    responses = [
        await client.post("/api/v1/commands/execute", json={"command": command})
        for command in commands
    ]
    assert [response.status_code for response in responses] == [200] * 7
    quote_steps = responses[0].json()["result"]["steps"]
    assert quote_steps["quote"]["data"]["instrument"]["exchange"] == "NSE"
    comparison_steps = responses[3].json()["result"]["steps"]
    assert len(comparison_steps["comparison"]["data"]["items"]) == 2


async def test_symbol_compatibility_routes_execute_workflows(client: AsyncClient) -> None:
    start, end = _range()
    quote = await client.get("/api/v1/instruments/TCS/quote?exchange=NSE")
    history = await client.get(
        "/api/v1/instruments/TCS/history",
        params={"exchange": "NSE", "start": start.isoformat(), "end": end.isoformat()},
    )
    assert quote.status_code == 200
    assert quote.json()["instrument"]["symbol"] == "TCS"
    assert history.status_code == 200
    assert history.json()["price_basis"] == "adjusted"
