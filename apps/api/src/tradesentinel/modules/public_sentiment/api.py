from __future__ import annotations

from typing import cast
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel

from tradesentinel.api.dependencies import ContainerDependency
from tradesentinel.domain.sentiment import (
    AggregateSentimentInput,
    CollectDiscussionsInput,
    CollectedDiscussions,
    CompanyDetectionInput,
    CompanyDetectionOutput,
    NarrativeExtractionInput,
    NarrativeList,
    PublicSentimentAnalysis,
    SentimentAnalysisInput,
    SentimentShift,
    SentimentSnapshot,
    SentimentTrend,
    ShiftDetectionInput,
    SourceWeightInput,
    SourceWeightOutput,
    SpamRemovalInput,
    SpamRemovalOutput,
    TrendDetectionInput,
)
from tradesentinel.platform.contracts import (
    CapabilityExecutionRequest,
    ExecutionContext,
    WorkflowExecutionRequest,
    WorkflowResult,
)
from tradesentinel.platform.errors import DomainError
from tradesentinel.providers.contracts import ProviderKind
from tradesentinel.providers.errors import ProviderNotConfiguredError

router = APIRouter(prefix="/api/v1/sentiment", tags=["public sentiment"])


def _context(request: Request) -> ExecutionContext:
    return ExecutionContext(
        request_id=UUID(request.state.request_id), principal_id=request.state.principal_id
    )


async def _execute[OutputT: BaseModel](
    name: str,
    body: BaseModel,
    model: type[OutputT],
    request: Request,
    container: ContainerDependency,
) -> OutputT:
    outcome = await container.pipeline.execute(
        CapabilityExecutionRequest(capability=name, payload=body.model_dump(mode="json")),
        _context(request),
    )
    return model.model_validate(outcome.result.model_dump()["data"])


def _ensure_workflow_succeeded(result: WorkflowResult) -> None:
    if result.status != "failed":
        return
    codes = {warning.code for step in result.steps.values() for warning in step.warnings}
    if "PROVIDER_NOT_CONFIGURED" in codes:
        raise ProviderNotConfiguredError(ProviderKind.SENTIMENT)
    raise DomainError(
        "SENTIMENT_EXECUTION_FAILED",
        "The public sentiment analysis could not be completed.",
        status_code=503,
    )


@router.post("/analyze", response_model=PublicSentimentAnalysis)
async def analyze(
    body: SentimentAnalysisInput, request: Request, container: ContainerDependency
) -> PublicSentimentAnalysis:
    outcome = await container.pipeline.execute(
        WorkflowExecutionRequest(
            workflow="sentiment.public.request", payload=body.model_dump(mode="json")
        ),
        _context(request),
    )
    workflow = cast(WorkflowResult, outcome.result)
    _ensure_workflow_succeeded(workflow)
    return PublicSentimentAnalysis(
        snapshot=SentimentSnapshot.model_validate(workflow.steps["aggregate"].data["snapshot"]),
        narratives=NarrativeList.model_validate(workflow.steps["narratives"].data),
        trend=SentimentTrend.model_validate(workflow.steps["trend"].data),
        shift=SentimentShift.model_validate(workflow.steps["shift"].data),
    )


@router.post("/discussions/collect", response_model=CollectedDiscussions)
async def collect(
    body: CollectDiscussionsInput, request: Request, container: ContainerDependency
) -> CollectedDiscussions:
    return await _execute(
        "sentiment.discussions.collect", body, CollectedDiscussions, request, container
    )


@router.post("/spam/remove", response_model=SpamRemovalOutput)
async def remove_spam(
    body: SpamRemovalInput, request: Request, container: ContainerDependency
) -> SpamRemovalOutput:
    return await _execute("sentiment.spam.remove", body, SpamRemovalOutput, request, container)


@router.post("/companies/detect", response_model=CompanyDetectionOutput)
async def detect(
    body: CompanyDetectionInput, request: Request, container: ContainerDependency
) -> CompanyDetectionOutput:
    return await _execute(
        "sentiment.companies.detect", body, CompanyDetectionOutput, request, container
    )


@router.post("/sources/weight", response_model=SourceWeightOutput)
async def weight(
    body: SourceWeightInput, request: Request, container: ContainerDependency
) -> SourceWeightOutput:
    return await _execute("sentiment.sources.weight", body, SourceWeightOutput, request, container)


@router.post("/aggregate", response_model=SentimentSnapshot)
async def aggregate(
    body: AggregateSentimentInput, request: Request, container: ContainerDependency
) -> SentimentSnapshot:
    outcome = await container.pipeline.execute(
        CapabilityExecutionRequest(
            capability="sentiment.aggregate", payload=body.model_dump(mode="json")
        ),
        _context(request),
    )
    return SentimentSnapshot.model_validate(outcome.result.model_dump()["data"]["snapshot"])


@router.post("/narratives", response_model=NarrativeList)
async def narratives(
    body: NarrativeExtractionInput, request: Request, container: ContainerDependency
) -> NarrativeList:
    return await _execute("sentiment.narratives.extract", body, NarrativeList, request, container)


@router.post("/trend", response_model=SentimentTrend)
async def trend(
    body: TrendDetectionInput, request: Request, container: ContainerDependency
) -> SentimentTrend:
    return await _execute("sentiment.trend.detect", body, SentimentTrend, request, container)


@router.post("/shift", response_model=SentimentShift)
async def shift(
    body: ShiftDetectionInput, request: Request, container: ContainerDependency
) -> SentimentShift:
    return await _execute("sentiment.shift.detect", body, SentimentShift, request, container)
