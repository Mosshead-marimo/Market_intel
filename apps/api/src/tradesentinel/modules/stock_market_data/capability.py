from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from pydantic import BaseModel, JsonValue

from tradesentinel.domain.market_data import (
    BenchmarkComparisonInput,
    FiveYearPerformanceInput,
    StockComparisonInput,
    StockCorporateActionsInput,
    StockHistoryInput,
    StockPerformanceInput,
    StockQuoteInput,
)
from tradesentinel.modules.stock_market_data.service import StockMarketDataService
from tradesentinel.platform.capabilities import Capability
from tradesentinel.platform.contracts import (
    CapabilityResult,
    ExecutionContext,
    RunMetadata,
    RunStatus,
)


def _result(output: BaseModel, started: datetime) -> CapabilityResult:
    completed = datetime.now(UTC)
    return CapabilityResult(
        capability="pending",
        status=RunStatus.COMPLETED,
        data=cast(dict[str, JsonValue], output.model_dump(mode="json")),
        metadata=RunMetadata(started_at=started, completed_at=completed),
    )


class QuoteCapability(Capability[StockQuoteInput]):
    input_model = StockQuoteInput

    def __init__(self, service: StockMarketDataService) -> None:
        self._service = service

    async def execute(
        self, context: ExecutionContext, payload: StockQuoteInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        return _result(await self._service.quote(context, payload), started)


class HistoryCapability(Capability[StockHistoryInput]):
    input_model = StockHistoryInput

    def __init__(self, service: StockMarketDataService) -> None:
        self._service = service

    async def execute(
        self, context: ExecutionContext, payload: StockHistoryInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        return _result(await self._service.history(context, payload), started)


class PerformanceCapability(Capability[StockPerformanceInput]):
    input_model = StockPerformanceInput

    def __init__(self, service: StockMarketDataService) -> None:
        self._service = service

    async def execute(
        self, context: ExecutionContext, payload: StockPerformanceInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        return _result(await self._service.performance(context, payload), started)


class ComparisonCapability(Capability[StockComparisonInput]):
    input_model = StockComparisonInput

    def __init__(self, service: StockMarketDataService) -> None:
        self._service = service

    async def execute(
        self, context: ExecutionContext, payload: StockComparisonInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        return _result(await self._service.compare(context, payload), started)


class CorporateActionsCapability(Capability[StockCorporateActionsInput]):
    input_model = StockCorporateActionsInput

    def __init__(self, service: StockMarketDataService) -> None:
        self._service = service

    async def execute(
        self, context: ExecutionContext, payload: StockCorporateActionsInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        return _result(await self._service.corporate_actions(context, payload), started)


class FiveYearPerformanceCapability(Capability[FiveYearPerformanceInput]):
    input_model = FiveYearPerformanceInput

    def __init__(self, service: StockMarketDataService) -> None:
        self._service = service

    async def execute(
        self, context: ExecutionContext, payload: FiveYearPerformanceInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        return _result(await self._service.five_year_performance(context, payload), started)


class BenchmarkComparisonCapability(Capability[BenchmarkComparisonInput]):
    input_model = BenchmarkComparisonInput

    def __init__(self, service: StockMarketDataService) -> None:
        self._service = service

    async def execute(
        self, context: ExecutionContext, payload: BenchmarkComparisonInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        return _result(await self._service.benchmark_comparison(context, payload), started)
