from __future__ import annotations

from typing import cast
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel

from tradesentinel.api.dependencies import ContainerDependency
from tradesentinel.domain.fundamentals import (
    FundamentalAnalysisRequest,
    FundamentalGrowthOutput,
    FundamentalPeerComparisonOutput,
    FundamentalSectionOutput,
    FundamentalSnapshot,
    FundamentalValuationOutput,
)
from tradesentinel.platform.contracts import (
    ExecutionContext,
    WorkflowExecutionRequest,
    WorkflowResult,
)
from tradesentinel.platform.errors import DomainError
from tradesentinel.providers.contracts import ProviderKind
from tradesentinel.providers.errors import ProviderNotConfiguredError

router = APIRouter(prefix="/api/v1/fundamentals", tags=["fundamentals"])


def _context(request: Request) -> ExecutionContext:
    return ExecutionContext(
        request_id=UUID(request.state.request_id), principal_id=request.state.principal_id
    )


def _ensure_succeeded(result: WorkflowResult) -> None:
    if result.status != "failed":
        return
    codes = {warning.code for step in result.steps.values() for warning in step.warnings}
    if "PROVIDER_NOT_CONFIGURED" in codes:
        raise ProviderNotConfiguredError(ProviderKind.FUNDAMENTALS)
    raise DomainError(
        "FUNDAMENTAL_EXECUTION_FAILED",
        "The fundamental analysis could not be completed.",
        status_code=422,
    )


async def _workflow[OutputT: BaseModel](
    name: str,
    body: FundamentalAnalysisRequest,
    output_type: type[OutputT],
    request: Request,
    container: ContainerDependency,
) -> OutputT:
    outcome = await container.pipeline.execute(
        WorkflowExecutionRequest(workflow=name, payload=body.model_dump(mode="json")),
        _context(request),
    )
    result = cast(WorkflowResult, outcome.result)
    _ensure_succeeded(result)
    return output_type.model_validate(result.steps["result"].data)


@router.post("/snapshot", response_model=FundamentalSnapshot)
async def snapshot(
    body: FundamentalAnalysisRequest, request: Request, container: ContainerDependency
) -> FundamentalSnapshot:
    return await _workflow(
        "fundamental.snapshot.request", body, FundamentalSnapshot, request, container
    )


def _section_route(path: str, workflow: str) -> None:
    async def endpoint(
        body: FundamentalAnalysisRequest,
        request: Request,
        container: ContainerDependency,
    ) -> FundamentalSectionOutput:
        return await _workflow(workflow, body, FundamentalSectionOutput, request, container)

    endpoint.__name__ = f"fundamental_{path.replace('-', '_')}"
    router.add_api_route(
        f"/{path}", endpoint, methods=["POST"], response_model=FundamentalSectionOutput
    )


for _path, _workflow_name in (
    ("revenue", "fundamental.revenue.request"),
    ("profit", "fundamental.profit.request"),
    ("cash-flow", "fundamental.cash_flow.request"),
    ("debt", "fundamental.debt.request"),
    ("margins", "fundamental.margins.request"),
    ("roe", "fundamental.roe.request"),
    ("roce", "fundamental.roce.request"),
):
    _section_route(_path, _workflow_name)


@router.post("/valuation", response_model=FundamentalValuationOutput)
async def valuation(
    body: FundamentalAnalysisRequest, request: Request, container: ContainerDependency
) -> FundamentalValuationOutput:
    return await _workflow(
        "fundamental.valuation.request",
        body,
        FundamentalValuationOutput,
        request,
        container,
    )


@router.post("/growth", response_model=FundamentalGrowthOutput)
async def growth(
    body: FundamentalAnalysisRequest, request: Request, container: ContainerDependency
) -> FundamentalGrowthOutput:
    return await _workflow(
        "fundamental.growth.request", body, FundamentalGrowthOutput, request, container
    )


@router.post("/peer-comparison", response_model=FundamentalPeerComparisonOutput)
async def peer_comparison(
    body: FundamentalAnalysisRequest, request: Request, container: ContainerDependency
) -> FundamentalPeerComparisonOutput:
    return await _workflow(
        "fundamental.peer_comparison.request",
        body,
        FundamentalPeerComparisonOutput,
        request,
        container,
    )
