from typing import cast
from uuid import UUID

from fastapi import APIRouter, Request

from tradesentinel.api.dependencies import ContainerDependency
from tradesentinel.domain.stock_overview import StockOverviewRequest
from tradesentinel.platform.contracts import (
    ExecutionContext,
    RenderedResponse,
    RunStatus,
    WorkflowExecutionRequest,
    WorkflowResult,
)
from tradesentinel.platform.errors import DomainError
from tradesentinel.providers.contracts import ProviderKind
from tradesentinel.providers.errors import ProviderNotConfiguredError

router = APIRouter(tags=["stock-overview"])


@router.post("/api/v1/stock-overview", response_model=RenderedResponse)
async def stock_overview(
    body: StockOverviewRequest,
    request: Request,
    container: ContainerDependency,
) -> RenderedResponse:
    outcome = await container.pipeline.execute(
        WorkflowExecutionRequest(workflow="stock.overview", payload=body.model_dump(mode="json")),
        ExecutionContext(
            request_id=UUID(request.state.request_id),
            principal_id=request.state.principal_id,
        ),
    )
    result = cast(WorkflowResult, outcome.result)
    if result.status == RunStatus.FAILED:
        codes = {warning.code for step in result.steps.values() for warning in step.warnings}
        if "PROVIDER_NOT_CONFIGURED" in codes:
            raise ProviderNotConfiguredError(ProviderKind.MARKET_DATA)
        raise DomainError(
            "STOCK_OVERVIEW_CORE_FAILED",
            "The required market or technical overview could not be completed.",
            status_code=422,
            details={"codes": sorted(codes)},
        )
    return outcome.response
