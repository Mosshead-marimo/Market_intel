from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import JsonValue
from sqlalchemy import text

from tradesentinel import __version__
from tradesentinel.api.dependencies import ContainerDependency
from tradesentinel.api.schemas import (
    CommandRequest,
    CommandResponse,
    RunSourcesResponse,
    WorkflowRequest,
    WorkflowResponse,
)
from tradesentinel.platform.contracts import (
    CapabilityDescriptor,
    DependencyHealth,
    ExecutionContext,
    HealthResult,
)
from tradesentinel.platform.errors import CapabilityNotInstalledError, RateLimitError

router = APIRouter()


@router.get("/health/live", response_model=HealthResult, tags=["health"])
async def liveness() -> HealthResult:
    return HealthResult(version=__version__, status="healthy", checked_at=datetime.now(UTC))


@router.get("/health/ready", response_model=HealthResult, tags=["health"])
async def readiness(container: ContainerDependency) -> HealthResult:
    dependencies: list[DependencyHealth] = []
    if container.settings.persistence_backend == "postgres":
        started = perf_counter()
        try:
            async with container.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            dependencies.append(
                DependencyHealth(
                    name="postgres",
                    status="healthy",
                    latency_ms=int((perf_counter() - started) * 1000),
                )
            )
        except Exception:
            dependencies.append(DependencyHealth(name="postgres", status="unhealthy"))
    else:
        dependencies.append(DependencyHealth(name="postgres", status="disabled"))
    if container.settings.event_backend == "redis":
        started = perf_counter()
        try:
            await container.redis.ping()
            dependencies.append(
                DependencyHealth(
                    name="redis",
                    status="healthy",
                    latency_ms=int((perf_counter() - started) * 1000),
                )
            )
        except Exception:
            dependencies.append(DependencyHealth(name="redis", status="unhealthy"))
    else:
        dependencies.append(DependencyHealth(name="redis", status="disabled"))
    unhealthy = any(item.status == "unhealthy" for item in dependencies)
    return HealthResult(
        version=__version__,
        status="unhealthy" if unhealthy else "healthy",
        checked_at=datetime.now(UTC),
        dependencies=tuple(dependencies),
    )


@router.get("/api/v1/capabilities", response_model=list[CapabilityDescriptor], tags=["registry"])
async def list_capabilities(container: ContainerDependency) -> list[CapabilityDescriptor]:
    return [item.descriptor for item in container.capabilities.list()]


@router.get("/api/v1/commands", tags=["registry"])
async def list_commands(container: ContainerDependency) -> list[dict[str, JsonValue]]:
    return [item.model_dump(mode="json") for item in container.commands.list()]


@router.post("/api/v1/commands/execute", response_model=CommandResponse, tags=["commands"])
async def execute_command(
    body: CommandRequest, request: Request, container: ContainerDependency
) -> CommandResponse:
    request_id = UUID(request.state.request_id)
    allowed, retry_after = await container.rate_limiter.allow(
        f"command:{request.client.host if request.client else 'unknown'}",
        container.settings.command_rate_limit,
    )
    if not allowed:
        raise RateLimitError(retry_after)
    parsed = container.commands.parse(body.command)
    descriptor = container.commands.get(parsed.name)
    context = ExecutionContext(request_id=request_id, session_id=body.session_id)
    raw_payload: dict[str, object] = dict(parsed.options)
    if parsed.arguments:
        raw_payload["arguments"] = parsed.arguments
    result = await container.capabilities.get(descriptor.capability).invoke(context, raw_payload)
    return CommandResponse(request_id=request_id, result=result)


@router.post(
    "/api/v1/workflows/{workflow_name}/execute",
    response_model=WorkflowResponse,
    tags=["workflows"],
)
async def execute_workflow(
    workflow_name: str,
    body: WorkflowRequest,
    request: Request,
    container: ContainerDependency,
) -> WorkflowResponse:
    request_id = UUID(request.state.request_id)
    context = ExecutionContext(request_id=request_id, session_id=body.session_id)
    result = await container.executor.execute(workflow_name, context, body.input)
    return WorkflowResponse(request_id=request_id, result=result)


@router.get("/api/v1/runs/{run_id}", tags=["runs"])
async def get_run(run_id: UUID, container: ContainerDependency) -> object:
    result = await container.runs.get_workflow(run_id)
    if result is None:
        from tradesentinel.platform.errors import DomainError

        raise DomainError("RUN_NOT_FOUND", "The requested run was not found.", status_code=404)
    return result


@router.get("/api/v1/runs/{run_id}/sources", response_model=RunSourcesResponse, tags=["runs"])
async def get_run_sources(run_id: UUID, container: ContainerDependency) -> RunSourcesResponse:
    result = await container.runs.get_workflow(run_id)
    if result is None:
        from tradesentinel.platform.errors import DomainError

        raise DomainError("RUN_NOT_FOUND", "The requested run was not found.", status_code=404)
    sources = tuple(source for step in result.steps.values() for source in step.sources)
    return RunSourcesResponse(run_id=run_id, sources=sources)


def unavailable(capability: str) -> None:
    raise CapabilityNotInstalledError(capability)


@router.post("/api/v1/chat", tags=["future"])
async def chat() -> None:
    unavailable("conversation.chat")


@router.get("/api/v1/chat/sessions", tags=["future"])
async def chat_sessions() -> None:
    unavailable("conversation.sessions")


@router.get("/api/v1/chat/sessions/{session_id}", tags=["future"])
async def chat_session(session_id: UUID) -> None:
    del session_id
    unavailable("conversation.sessions")


@router.get("/api/v1/instruments/search", tags=["future"])
async def instrument_search() -> None:
    unavailable("instrument.search")


@router.get("/api/v1/instruments/{symbol}/quote", tags=["future"])
async def instrument_quote(symbol: str) -> None:
    del symbol
    unavailable("instrument.quote")


@router.get("/api/v1/instruments/{symbol}/history", tags=["future"])
async def instrument_history(symbol: str) -> None:
    del symbol
    unavailable("instrument.history")


@router.post("/api/v1/predictions", tags=["future"])
async def create_prediction() -> None:
    unavailable("prediction.create")


@router.get("/api/v1/predictions/{prediction_id}", tags=["future"])
async def get_prediction(prediction_id: UUID) -> None:
    del prediction_id
    unavailable("prediction.read")


@router.get("/api/v1/predictions/{prediction_id}/evaluation", tags=["future"])
async def get_prediction_evaluation(prediction_id: UUID) -> None:
    del prediction_id
    unavailable("prediction.evaluate")


@router.get("/api/v1/events/stream", tags=["events"])
async def event_stream() -> StreamingResponse:
    async def unavailable_stream() -> AsyncIterator[str]:
        yield (
            'event: error\ndata: {"code":"CAPABILITY_NOT_INSTALLED",'
            '"capability":"conversation.chat"}\n\n'
        )

    return StreamingResponse(unavailable_stream(), media_type="text/event-stream")
