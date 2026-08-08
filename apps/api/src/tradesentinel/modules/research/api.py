from __future__ import annotations

from datetime import datetime
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Request
from pydantic import BaseModel

from tradesentinel.api.dependencies import ContainerDependency
from tradesentinel.domain.research import (
    NewsSearchInput,
    NewsSearchOutput,
    ResearchEvidenceOutput,
    ResearchReportOutput,
    ResearchTimelineInput,
    ResearchTimelineOutput,
)
from tradesentinel.platform.contracts import (
    CapabilityExecutionRequest,
    ExecutionContext,
    WorkflowExecutionRequest,
    WorkflowResult,
)

router = APIRouter(prefix="/api/v1/research", tags=["research"])


def _context(request: Request) -> ExecutionContext:
    return ExecutionContext(
        request_id=UUID(request.state.request_id),
        principal_id=request.state.principal_id,
    )


async def _capability[OutputT: BaseModel](
    name: str,
    payload: BaseModel | dict[str, object],
    output_type: type[OutputT],
    request: Request,
    container: ContainerDependency,
) -> OutputT:
    raw = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    outcome = await container.pipeline.execute(
        CapabilityExecutionRequest(capability=name, payload=raw), _context(request)
    )
    return output_type.model_validate(outcome.result.model_dump()["data"])


@router.get("/news", response_model=NewsSearchOutput)
async def search_news(
    request: Request,
    container: ContainerDependency,
    q: str,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int | None = None,
) -> NewsSearchOutput:
    return await _capability(
        "research.news.search",
        NewsSearchInput(query=q, start=start, end=end, limit=limit),
        NewsSearchOutput,
        request,
        container,
    )


@router.post("/timeline", response_model=ResearchTimelineOutput)
async def create_timeline(
    body: ResearchTimelineInput, request: Request, container: ContainerDependency
) -> ResearchTimelineOutput:
    return await _capability("research.timeline", body, ResearchTimelineOutput, request, container)


@router.post("/reports", response_model=ResearchReportOutput)
async def create_report(
    body: NewsSearchInput, request: Request, container: ContainerDependency
) -> ResearchReportOutput:
    outcome = await container.pipeline.execute(
        WorkflowExecutionRequest(
            workflow="research.report.request", payload=body.model_dump(mode="json")
        ),
        _context(request),
    )
    workflow = cast(WorkflowResult, outcome.result)
    return ResearchReportOutput.model_validate(workflow.steps["report"].data)


@router.get("/events/{event_id}/evidence", response_model=ResearchEvidenceOutput)
async def get_event_evidence(
    event_id: UUID, request: Request, container: ContainerDependency
) -> ResearchEvidenceOutput:
    return await _capability(
        "research.evidence",
        {"event_id": str(event_id)},
        ResearchEvidenceOutput,
        request,
        container,
    )
