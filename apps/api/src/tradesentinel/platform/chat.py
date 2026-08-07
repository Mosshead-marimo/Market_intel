from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Coroutine
from typing import Any
from uuid import UUID

import structlog

from tradesentinel.platform.chat_persistence import ChatAcceptance, ChatRepository
from tradesentinel.platform.chat_streams import ChatStreamStore
from tradesentinel.platform.contracts import (
    ApiErrorDetail,
    ChatCompleteEvent,
    ChatComponentEvent,
    ChatErrorEvent,
    ChatProgressEvent,
    ChatResponseEvent,
    ChatStatusEvent,
    ChatTurn,
    ChatTurnStatus,
    ChatTypingEvent,
    ChatWarningEvent,
    CommandExecutionRequest,
    EventEnvelope,
    ExecutionContext,
    ExecutionPlan,
    ExecutionRequest,
    IntentExecutionRequest,
)
from tradesentinel.platform.errors import ChatQueueError, DomainError
from tradesentinel.platform.events import EventBus
from tradesentinel.platform.pipeline import ExecutionPipeline


class ConversationPlanner:
    def request_for(self, message: str) -> ExecutionRequest:
        stripped = message.strip()
        if stripped.startswith("/"):
            return CommandExecutionRequest(command=stripped)
        return IntentExecutionRequest(text=stripped)

    async def plan(
        self, message: str, context: ExecutionContext, pipeline: ExecutionPipeline
    ) -> ExecutionPlan:
        return await pipeline.plan(self.request_for(message), context)


def response_chunks(value: str, max_characters: int = 48) -> tuple[str, ...]:
    if not value:
        return ()
    tokens = re.findall(r"\S+\s*", value)
    chunks: list[str] = []
    current = ""
    for token in tokens:
        if current and len(current) + len(token) > max_characters:
            chunks.append(current)
            current = token
        else:
            current += token
    if current:
        chunks.append(current)
    return tuple(chunks)


class BackgroundTaskRunner:
    def __init__(self) -> None:
        self._tasks: set[asyncio.Task[object]] = set()

    def start(self, operation: Coroutine[Any, Any, object]) -> None:
        task = asyncio.create_task(operation)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)


class ChatOrchestrator:
    def __init__(
        self,
        repository: ChatRepository,
        streams: ChatStreamStore,
        events: EventBus,
        pipeline: ExecutionPipeline,
        *,
        context_message_limit: int = 20,
    ) -> None:
        self.repository = repository
        self.streams = streams
        self.events = events
        self.pipeline = pipeline
        self.planner = ConversationPlanner()
        self.context_message_limit = context_message_limit

    async def accept(
        self,
        principal_id: str,
        *,
        session_id: UUID | None,
        client_message_id: UUID,
        message: str,
        request_id: UUID,
        correlation_id: UUID,
    ) -> ChatAcceptance:
        return await self.repository.accept_turn(
            principal_id,
            session_id=session_id,
            client_message_id=client_message_id,
            content=message,
            request_id=request_id,
            correlation_id=correlation_id,
        )

    async def dispatch_pending_once(self) -> int:
        published = 0
        for pending in await self.repository.pending_events():
            try:
                await self.events.publish(
                    EventEnvelope(
                        event_id=pending.id,
                        name="chat.turn.requested",
                        correlation_id=pending.correlation_id,
                        producer="platform.chat",
                        payload={
                            "turn_id": str(pending.turn_id),
                            "principal_id": pending.principal_id,
                            "request_id": str(pending.request_id),
                        },
                    )
                )
            except Exception as exc:
                structlog.get_logger().warning(
                    "chat_outbox_publish_failed",
                    turn_id=str(pending.turn_id),
                    error_type=type(exc).__name__,
                )
                raise ChatQueueError() from exc
            await self.repository.mark_published(pending.id)
            published += 1
        return published

    async def dispatch_forever(self) -> None:
        while True:
            try:
                await self.dispatch_pending_once()
            except ChatQueueError:
                await asyncio.sleep(1)
            else:
                await asyncio.sleep(0.25)

    async def handle_requested(self, event: EventEnvelope) -> None:
        turn_id = UUID(str(event.payload["turn_id"]))
        principal_id = str(event.payload["principal_id"])
        claimed = await self.repository.claim_turn(principal_id, turn_id)
        if claimed is None:
            return
        await self._execute(principal_id, claimed)

    async def _emit(self, chat_turn: ChatTurn, event_type: type[Any], **values: Any) -> None:
        sequence = await self.streams.next_sequence(chat_turn.id)
        event = event_type(
            sequence=sequence,
            session_id=chat_turn.session_id,
            turn_id=chat_turn.id,
            request_id=chat_turn.request_id,
            correlation_id=chat_turn.correlation_id,
            run_id=values.pop("run_id", chat_turn.run_id),
            **values,
        )
        await self.streams.append(chat_turn.id, event)

    async def _execute(self, principal_id: str, turn: ChatTurn) -> None:
        try:
            await self._emit(
                turn,
                ChatStatusEvent,
                status=ChatTurnStatus.PLANNING,
                message="Planning the request",
            )
            await self._emit(turn, ChatTypingEvent, active=True)
            context_snapshot = await self.repository.get_context(
                principal_id,
                turn.session_id,
                turn.id,
                self.context_message_limit,
            )
            message = context_snapshot.messages[-1].content
            context = ExecutionContext(
                request_id=turn.request_id,
                session_id=turn.session_id,
                principal_id=principal_id,
                correlation_id=turn.correlation_id,
                conversation=context_snapshot,
            )
            plan = await self.planner.plan(message, context, self.pipeline)
            await self._emit(
                turn,
                ChatProgressEvent,
                stage="planning",
                label=f"Selected {plan.target.kind.value} {plan.target.name}",
                current=1,
                total=1,
            )
            turn = await self.repository.set_turn_status(
                principal_id, turn.id, ChatTurnStatus.EXECUTING
            )
            await self._emit(
                turn,
                ChatStatusEvent,
                status=ChatTurnStatus.EXECUTING,
                message="Executing registered capabilities",
            )
            outcome = await self.pipeline.execute_plan(plan, context)
            await self._emit(
                turn,
                ChatProgressEvent,
                stage="execution",
                label=f"Completed {plan.target.name}",
                current=1,
                total=1,
                run_id=outcome.response.run_id,
            )
            turn = await self.repository.set_turn_status(
                principal_id, turn.id, ChatTurnStatus.RENDERING
            )
            await self._emit(
                turn,
                ChatStatusEvent,
                status=ChatTurnStatus.RENDERING,
                message="Rendering the response",
                run_id=outcome.response.run_id,
            )
            for chunk in response_chunks(outcome.response.text):
                await self._emit(
                    turn,
                    ChatResponseEvent,
                    delta=chunk,
                    run_id=outcome.response.run_id,
                )
            for component in outcome.response.components:
                await self._emit(
                    turn,
                    ChatComponentEvent,
                    component=component,
                    run_id=outcome.response.run_id,
                )
            for warning in outcome.response.warnings:
                await self._emit(
                    turn,
                    ChatWarningEvent,
                    warning=warning,
                    run_id=outcome.response.run_id,
                )
            completed, assistant = await self.repository.complete_turn(
                principal_id, turn.id, outcome.response
            )
            await self._emit(
                completed,
                ChatTypingEvent,
                active=False,
                run_id=outcome.response.run_id,
            )
            await self._emit(
                completed,
                ChatCompleteEvent,
                turn=completed,
                message=assistant,
                run_id=outcome.response.run_id,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            if isinstance(exc, DomainError):
                error = ApiErrorDetail(
                    code=exc.code,
                    message=exc.message,
                    retryable=exc.retryable,
                    details=exc.details,
                )
            else:
                structlog.get_logger().exception(
                    "chat_turn_failed",
                    turn_id=str(turn.id),
                    error_type=type(exc).__name__,
                )
                error = ApiErrorDetail(
                    code="EXECUTION_FAILED",
                    message="The message could not be completed.",
                )
            failed = await self.repository.fail_turn(principal_id, turn.id, error)
            await self._emit(failed, ChatTypingEvent, active=False)
            await self._emit(failed, ChatErrorEvent, error=error)


async def run_operations(*operations: Awaitable[object]) -> None:
    await asyncio.gather(*operations)
