from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from time import perf_counter
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import JsonValue
from sqlalchemy import text

from tradesentinel import __version__
from tradesentinel.api.dependencies import ContainerDependency
from tradesentinel.api.schemas import (
    ChatRequest,
    ChatSessionCreateRequest,
    ChatSessionUpdateRequest,
    CommandRequest,
    CommandResponse,
    RunSourcesResponse,
    WorkflowRequest,
    WorkflowResponse,
)
from tradesentinel.platform.contracts import (
    CapabilityDescriptor,
    ChatSession,
    ChatSessionDetail,
    ChatSessionPage,
    ChatStreamEvent,
    ChatTurn,
    ChatTurnAccepted,
    ChatTurnStatus,
    CommandExecutionRequest,
    DependencyHealth,
    ExecutionContext,
    HealthResult,
    WorkflowExecutionRequest,
)
from tradesentinel.platform.errors import (
    CapabilityNotInstalledError,
    ChatStreamExpiredError,
    RateLimitError,
)

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
    context = ExecutionContext(request_id=request_id, session_id=body.session_id)
    outcome = await container.pipeline.execute(
        CommandExecutionRequest(command=body.command), context
    )
    return CommandResponse(request_id=request_id, result=outcome.result, response=outcome.response)


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
    outcome = await container.pipeline.execute(
        WorkflowExecutionRequest(workflow=workflow_name, payload=body.input), context
    )
    if not hasattr(outcome.result, "workflow"):
        raise RuntimeError("workflow pipeline returned a capability result")
    return WorkflowResponse(request_id=request_id, result=outcome.result, response=outcome.response)


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


@router.post("/api/v1/chat/sessions", response_model=ChatSession, tags=["chat"])
async def create_chat_session(
    body: ChatSessionCreateRequest, request: Request, container: ContainerDependency
) -> ChatSession:
    return await container.chat_repository.create_session(
        request.state.principal_id, body.title.strip()
    )


@router.get("/api/v1/chat/sessions", response_model=ChatSessionPage, tags=["chat"])
async def chat_sessions(
    request: Request,
    container: ContainerDependency,
    archived: bool = False,
    cursor: str | None = None,
    limit: int = 30,
) -> ChatSessionPage:
    return await container.chat_repository.list_sessions(
        request.state.principal_id,
        archived=archived,
        cursor=cursor,
        limit=min(max(limit, 1), 100),
    )


@router.get(
    "/api/v1/chat/sessions/{session_id}",
    response_model=ChatSessionDetail,
    tags=["chat"],
)
async def chat_session(
    session_id: UUID, request: Request, container: ContainerDependency
) -> ChatSessionDetail:
    return await container.chat_repository.get_session(request.state.principal_id, session_id)


@router.patch("/api/v1/chat/sessions/{session_id}", response_model=ChatSession, tags=["chat"])
async def update_chat_session(
    session_id: UUID,
    body: ChatSessionUpdateRequest,
    request: Request,
    container: ContainerDependency,
) -> ChatSession:
    return await container.chat_repository.update_session(
        request.state.principal_id,
        session_id,
        title=body.title.strip() if body.title is not None else None,
        archived=body.archived,
    )


@router.post("/api/v1/chat", response_model=ChatTurnAccepted, status_code=202, tags=["chat"])
async def chat(
    body: ChatRequest, request: Request, container: ContainerDependency
) -> ChatTurnAccepted:
    request_id = UUID(request.state.request_id)
    allowed, retry_after = await container.rate_limiter.allow(
        f"chat:{request.state.principal_id}", container.settings.request_rate_limit
    )
    if not allowed:
        raise RateLimitError(retry_after)
    acceptance = await container.chat.accept(
        request.state.principal_id,
        session_id=body.session_id,
        client_message_id=body.client_message_id,
        message=body.message,
        request_id=request_id,
        correlation_id=uuid4(),
    )
    if acceptance.created:
        container.tasks.start(container.chat.dispatch_pending_once())
    return ChatTurnAccepted(
        session_id=acceptance.turn.session_id,
        turn_id=acceptance.turn.id,
        user_message_id=acceptance.turn.user_message_id,
        status=acceptance.turn.status,
        stream_url=f"/api/v1/chat/turns/{acceptance.turn.id}/events",
    )


@router.get("/api/v1/chat/turns/{turn_id}", response_model=ChatTurn, tags=["chat"])
async def get_chat_turn(
    turn_id: UUID, request: Request, container: ContainerDependency
) -> ChatTurn:
    return await container.chat_repository.get_turn(request.state.principal_id, turn_id)


@router.get("/api/v1/chat/turns/{turn_id}/events", tags=["chat"])
async def chat_turn_events(
    turn_id: UUID, request: Request, container: ContainerDependency
) -> StreamingResponse:
    turn = await container.chat_repository.get_turn(request.state.principal_id, turn_id)
    after = request.headers.get("Last-Event-ID")
    if (
        after
        and not await container.chat_streams.exists(turn_id)
        and turn.status
        in {
            ChatTurnStatus.COMPLETED,
            ChatTurnStatus.PARTIAL,
            ChatTurnStatus.FAILED,
        }
    ):
        raise ChatStreamExpiredError()

    async def stream() -> AsyncIterator[str]:
        cursor = after
        while True:
            records = await container.chat_streams.read(turn_id, cursor, block_ms=15_000)
            if not records:
                yield ": heartbeat\n\n"
                continue
            for record in records:
                cursor = record.cursor
                event: ChatStreamEvent = record.event
                yield (
                    f"id: {record.cursor}\nevent: {event.type}\ndata: {event.model_dump_json()}\n\n"
                )
                if event.type in {"complete", "error"}:
                    return

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
