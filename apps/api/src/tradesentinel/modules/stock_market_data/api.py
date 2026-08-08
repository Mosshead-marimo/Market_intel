from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel, JsonValue

from tradesentinel.api.dependencies import ContainerDependency
from tradesentinel.domain.market_data import (
    BenchmarkComparisonInput,
    BenchmarkComparisonOutput,
    FiveYearPerformanceInput,
    FiveYearPerformanceOutput,
    MarketInterval,
    StockComparisonInput,
    StockComparisonOutput,
    StockCorporateActionsInput,
    StockCorporateActionsOutput,
    StockHistoryInput,
    StockHistoryOutput,
    StockPerformanceInput,
    StockPerformanceOutput,
    StockQuoteInput,
    StockQuoteOutput,
)
from tradesentinel.platform.contracts import (
    CapabilityExecutionRequest,
    ExecutionContext,
    WorkflowExecutionRequest,
    WorkflowResult,
)

router = APIRouter(tags=["market-data"])


def _context(request: Request) -> ExecutionContext:
    return ExecutionContext(
        request_id=UUID(request.state.request_id),
        principal_id=request.state.principal_id,
    )


async def _capability[OutputT: BaseModel](
    name: str,
    payload: BaseModel,
    output_type: type[OutputT],
    request: Request,
    container: ContainerDependency,
) -> OutputT:
    outcome = await container.pipeline.execute(
        CapabilityExecutionRequest(capability=name, payload=payload.model_dump(mode="json")),
        _context(request),
    )
    return output_type.model_validate(outcome.result.model_dump()["data"])


async def _workflow[OutputT: BaseModel](
    name: str,
    payload: dict[str, JsonValue],
    final_step: str,
    output_type: type[OutputT],
    request: Request,
    container: ContainerDependency,
) -> OutputT:
    outcome = await container.pipeline.execute(
        WorkflowExecutionRequest(workflow=name, payload=payload),
        _context(request),
    )
    result = cast(WorkflowResult, outcome.result)
    return output_type.model_validate(result.steps[final_step].data)


@router.post("/api/v1/market-data/quote", response_model=StockQuoteOutput)
async def quote(
    body: StockQuoteInput, request: Request, container: ContainerDependency
) -> StockQuoteOutput:
    return await _capability("stock.quote", body, StockQuoteOutput, request, container)


@router.post("/api/v1/market-data/history", response_model=StockHistoryOutput)
async def history(
    body: StockHistoryInput, request: Request, container: ContainerDependency
) -> StockHistoryOutput:
    return await _capability("stock.history", body, StockHistoryOutput, request, container)


@router.post("/api/v1/market-data/performance", response_model=StockPerformanceOutput)
async def performance(
    body: StockPerformanceInput, request: Request, container: ContainerDependency
) -> StockPerformanceOutput:
    return await _capability("stock.performance", body, StockPerformanceOutput, request, container)


@router.post("/api/v1/market-data/comparison", response_model=StockComparisonOutput)
async def comparison(
    body: StockComparisonInput, request: Request, container: ContainerDependency
) -> StockComparisonOutput:
    return await _capability("stock.comparison", body, StockComparisonOutput, request, container)


@router.post("/api/v1/market-data/corporate-actions", response_model=StockCorporateActionsOutput)
async def corporate_actions(
    body: StockCorporateActionsInput, request: Request, container: ContainerDependency
) -> StockCorporateActionsOutput:
    return await _capability(
        "stock.corporate_actions", body, StockCorporateActionsOutput, request, container
    )


@router.post(
    "/api/v1/market-data/five-year-performance",
    response_model=FiveYearPerformanceOutput,
)
async def five_year_performance(
    body: FiveYearPerformanceInput, request: Request, container: ContainerDependency
) -> FiveYearPerformanceOutput:
    return await _capability(
        "stock.performance.five_year", body, FiveYearPerformanceOutput, request, container
    )


@router.post(
    "/api/v1/market-data/benchmark-comparison",
    response_model=BenchmarkComparisonOutput,
)
async def benchmark_comparison(
    body: BenchmarkComparisonInput, request: Request, container: ContainerDependency
) -> BenchmarkComparisonOutput:
    return await _capability(
        "stock.benchmark.comparison", body, BenchmarkComparisonOutput, request, container
    )


@router.get("/api/v1/instruments/{symbol}/quote", response_model=StockQuoteOutput)
async def quote_by_symbol(
    symbol: str,
    request: Request,
    container: ContainerDependency,
    exchange: str | None = None,
) -> StockQuoteOutput:
    return await _workflow(
        "stock.quote.request",
        {"query": symbol, "exchange": exchange},
        "quote",
        StockQuoteOutput,
        request,
        container,
    )


@router.get("/api/v1/instruments/{symbol}/history", response_model=StockHistoryOutput)
async def history_by_symbol(
    symbol: str,
    start: datetime,
    end: datetime,
    request: Request,
    container: ContainerDependency,
    exchange: str | None = None,
    interval: MarketInterval = MarketInterval.DAILY,
) -> StockHistoryOutput:
    return await _workflow(
        "stock.history.request",
        {
            "query": symbol,
            "exchange": exchange,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "interval": interval.value,
        },
        "history",
        StockHistoryOutput,
        request,
        container,
    )
