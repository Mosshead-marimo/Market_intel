from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from pydantic import BaseModel, JsonValue

from tradesentinel.domain.market_data import (
    BenchmarkComparisonInput,
    FiveYearPerformanceInput,
    FiveYearPerformanceOutput,
    StockComparisonInput,
    StockCorporateActionsInput,
    StockCorporateActionsOutput,
    StockHistoryInput,
    StockHistoryOutput,
    StockPerformanceInput,
    StockQuoteBatchInput,
    StockQuoteBatchOutput,
    StockQuoteInput,
    StockQuoteOutput,
)
from tradesentinel.modules.stock_market_data.service import StockMarketDataService
from tradesentinel.platform.capabilities import Capability
from tradesentinel.platform.contracts import (
    CapabilityResult,
    CapabilityWarning,
    ChartPoint,
    ChartSeries,
    ComponentStatus,
    EventTimeline,
    EventTimelineItem,
    ExecutionContext,
    MetricGrid,
    MetricItem,
    PriceChart,
    ResponseComponent,
    RunMetadata,
    RunStatus,
)


def _components(output: BaseModel) -> tuple[ResponseComponent, ...]:
    if isinstance(output, StockQuoteOutput):
        quote_metrics = [
            MetricItem(label="Price", value=str(output.price), detail=output.currency),
        ]
        if output.change is not None:
            quote_metrics.append(MetricItem(label="Change", value=str(output.change)))
        if output.change_percent is not None:
            quote_metrics.append(
                MetricItem(label="Change percent", value=str(output.change_percent))
            )
        if output.volume is not None:
            quote_metrics.append(MetricItem(label="Volume", value=str(output.volume)))
        return (
            MetricGrid(
                id="market-quote",
                title="Current quote",
                metrics=tuple(quote_metrics),
            ),
        )
    if isinstance(output, StockHistoryOutput):
        return (
            PriceChart(
                id="market-adjusted-history",
                title="Five-year adjusted price history",
                status=ComponentStatus.EMPTY if not output.bars else ComponentStatus.READY,
                series=(
                    ChartSeries(
                        name=f"{output.instrument.symbol} adjusted close",
                        points=tuple(
                            ChartPoint(timestamp=bar.timestamp, value=float(bar.adjusted_close))
                            for bar in output.bars
                        ),
                    ),
                ),
            ),
        )
    if isinstance(output, FiveYearPerformanceOutput):
        performance = output.performance.metrics
        return (
            MetricGrid(
                id="market-five-year-performance",
                title="Five-year performance",
                metrics=(
                    MetricItem(label="Total return", value=str(performance.total_return)),
                    MetricItem(label="CAGR", value=str(performance.cagr)),
                    MetricItem(
                        label="Annualized volatility",
                        value=str(performance.annualized_volatility),
                    ),
                    MetricItem(
                        label="Maximum drawdown",
                        value=str(performance.maximum_drawdown),
                    ),
                ),
            ),
        )
    if isinstance(output, StockCorporateActionsOutput):
        return (
            EventTimeline(
                id="market-corporate-actions",
                title="Corporate actions",
                status=ComponentStatus.EMPTY if not output.actions else ComponentStatus.READY,
                items=tuple(
                    EventTimelineItem(
                        occurred_at=action.effective_at,
                        label=action.action_type.value.replace("_", " ").title(),
                        description=(
                            f"{action.amount} {action.currency}"
                            if action.amount is not None and action.currency is not None
                            else f"Ratio {action.ratio}"
                            if action.ratio is not None
                            else None
                        ),
                        category=action.action_type.value,
                        source_id=action.provider.source_id,
                    )
                    for action in output.actions
                ),
            ),
        )
    return ()


def _result(output: BaseModel, started: datetime) -> CapabilityResult:
    completed = datetime.now(UTC)
    return CapabilityResult(
        capability="pending",
        status=RunStatus.COMPLETED,
        data=cast(dict[str, JsonValue], output.model_dump(mode="json")),
        components=_components(output),
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


class QuoteBatchCapability(Capability[StockQuoteBatchInput]):
    input_model = StockQuoteBatchInput

    def __init__(self, service: StockMarketDataService) -> None:
        self._service = service

    async def execute(
        self, context: ExecutionContext, payload: StockQuoteBatchInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        output: StockQuoteBatchOutput = await self._service.quote_batch(context, payload)
        result = _result(output, started)
        if not output.failures:
            return result
        return result.model_copy(
            update={
                "status": RunStatus.PARTIAL,
                "warnings": tuple(
                    CapabilityWarning(
                        code=item.code,
                        message=item.message,
                        retryable=item.retryable,
                        details={"instrument_id": str(item.instrument.instrument_id)},
                    )
                    for item in output.failures
                ),
            }
        )


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
