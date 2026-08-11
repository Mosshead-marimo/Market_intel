from __future__ import annotations

from typing import cast
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel

from tradesentinel.api.dependencies import ContainerDependency
from tradesentinel.domain.technical import (
    AdxOutput,
    AtrOutput,
    EmaOutput,
    LevelOutput,
    MacdOutput,
    MomentumOutput,
    RsiOutput,
    SmaOutput,
    TechnicalAnalysisRequest,
    TechnicalSnapshot,
    TrendOutput,
    VolatilityOutput,
)
from tradesentinel.platform.contracts import (
    ExecutionContext,
    WorkflowExecutionRequest,
    WorkflowResult,
)
from tradesentinel.platform.errors import DomainError
from tradesentinel.providers.contracts import ProviderKind
from tradesentinel.providers.errors import ProviderNotConfiguredError

router = APIRouter(prefix="/api/v1/technical", tags=["technical analysis"])


def _context(request: Request) -> ExecutionContext:
    return ExecutionContext(
        request_id=UUID(request.state.request_id), principal_id=request.state.principal_id
    )


def _ensure_succeeded(result: WorkflowResult) -> None:
    if result.status != "failed":
        return
    codes = {warning.code for step in result.steps.values() for warning in step.warnings}
    if "PROVIDER_NOT_CONFIGURED" in codes:
        raise ProviderNotConfiguredError(ProviderKind.MARKET_DATA)
    if "TECHNICAL_INSUFFICIENT_HISTORY" in codes:
        raise DomainError(
            "TECHNICAL_INSUFFICIENT_HISTORY",
            "The indicator does not have enough observations for its warm-up period.",
            status_code=422,
        )
    raise DomainError(
        "TECHNICAL_EXECUTION_FAILED",
        "The technical calculation could not be completed.",
        status_code=422,
    )


async def _workflow[OutputT: BaseModel](
    name: str,
    body: TechnicalAnalysisRequest,
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


@router.post("/snapshot", response_model=TechnicalSnapshot)
async def snapshot(
    body: TechnicalAnalysisRequest, request: Request, container: ContainerDependency
) -> TechnicalSnapshot:
    return await _workflow(
        "technical.snapshot.request", body, TechnicalSnapshot, request, container
    )


@router.post("/rsi", response_model=RsiOutput)
async def rsi(
    body: TechnicalAnalysisRequest, request: Request, container: ContainerDependency
) -> RsiOutput:
    return await _workflow("technical.rsi.request", body, RsiOutput, request, container)


@router.post("/macd", response_model=MacdOutput)
async def macd(
    body: TechnicalAnalysisRequest, request: Request, container: ContainerDependency
) -> MacdOutput:
    return await _workflow("technical.macd.request", body, MacdOutput, request, container)


@router.post("/ema", response_model=EmaOutput)
async def ema(
    body: TechnicalAnalysisRequest, request: Request, container: ContainerDependency
) -> EmaOutput:
    return await _workflow("technical.ema.request", body, EmaOutput, request, container)


@router.post("/sma", response_model=SmaOutput)
async def sma(
    body: TechnicalAnalysisRequest, request: Request, container: ContainerDependency
) -> SmaOutput:
    return await _workflow("technical.sma.request", body, SmaOutput, request, container)


@router.post("/atr", response_model=AtrOutput)
async def atr(
    body: TechnicalAnalysisRequest, request: Request, container: ContainerDependency
) -> AtrOutput:
    return await _workflow("technical.atr.request", body, AtrOutput, request, container)


@router.post("/adx", response_model=AdxOutput)
async def adx(
    body: TechnicalAnalysisRequest, request: Request, container: ContainerDependency
) -> AdxOutput:
    return await _workflow("technical.adx.request", body, AdxOutput, request, container)


@router.post("/support", response_model=LevelOutput)
async def support(
    body: TechnicalAnalysisRequest, request: Request, container: ContainerDependency
) -> LevelOutput:
    return await _workflow("technical.support.request", body, LevelOutput, request, container)


@router.post("/resistance", response_model=LevelOutput)
async def resistance(
    body: TechnicalAnalysisRequest, request: Request, container: ContainerDependency
) -> LevelOutput:
    return await _workflow("technical.resistance.request", body, LevelOutput, request, container)


@router.post("/trend", response_model=TrendOutput)
async def trend(
    body: TechnicalAnalysisRequest, request: Request, container: ContainerDependency
) -> TrendOutput:
    return await _workflow("technical.trend.request", body, TrendOutput, request, container)


@router.post("/momentum", response_model=MomentumOutput)
async def momentum(
    body: TechnicalAnalysisRequest, request: Request, container: ContainerDependency
) -> MomentumOutput:
    return await _workflow("technical.momentum.request", body, MomentumOutput, request, container)


@router.post("/volatility", response_model=VolatilityOutput)
async def volatility(
    body: TechnicalAnalysisRequest, request: Request, container: ContainerDependency
) -> VolatilityOutput:
    return await _workflow(
        "technical.volatility.request", body, VolatilityOutput, request, container
    )
