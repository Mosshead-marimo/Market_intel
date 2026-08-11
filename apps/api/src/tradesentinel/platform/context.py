from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import UUID

from pydantic import JsonValue

from tradesentinel.platform.contracts import EventEnvelope, ExecutionContext
from tradesentinel.platform.errors import DomainError
from tradesentinel.platform.events import EventBus
from tradesentinel.platform.logging import request_id_var, run_id_var


class ExecutionContextManager:
    def __init__(self, events: EventBus) -> None:
        self._events = events

    def create(self, **values: object) -> ExecutionContext:
        return ExecutionContext.model_validate(values)

    async def emit(
        self,
        context: ExecutionContext,
        name: str,
        producer: str,
        payload: dict[str, JsonValue],
    ) -> None:
        await self._events.publish(
            EventEnvelope(
                name=name,
                correlation_id=context.correlation_id,
                causation_id=context.causation_id,
                producer=producer,
                payload=payload,
            )
        )

    @asynccontextmanager
    async def workflow_scope(
        self, context: ExecutionContext, workflow: str, run_id: UUID
    ) -> AsyncIterator[ExecutionContext]:
        child = context.model_copy(update={"workflow_run_id": run_id})
        async with self._scope(child, "workflow", workflow, run_id, 1):
            yield child

    @asynccontextmanager
    async def capability_scope(
        self,
        context: ExecutionContext,
        capability: str,
        run_id: UUID,
        attempt: int,
    ) -> AsyncIterator[ExecutionContext]:
        child = context.model_copy(update={"capability_run_id": run_id})
        async with self._scope(child, "capability", capability, run_id, attempt):
            yield child

    @asynccontextmanager
    async def _scope(
        self,
        context: ExecutionContext,
        kind: str,
        name: str,
        run_id: UUID,
        attempt: int,
    ) -> AsyncIterator[None]:
        request_token = request_id_var.set(str(context.request_id))
        run_token = run_id_var.set(str(run_id))
        await self._events.publish(
            EventEnvelope(
                name=f"{kind}.started",
                correlation_id=context.correlation_id,
                causation_id=context.causation_id,
                producer="platform.execution",
                payload={kind: name, "run_id": str(run_id), "attempt": attempt},
            )
        )
        try:
            yield
        except BaseException as exc:
            error_code = exc.code if isinstance(exc, DomainError) else "INTERNAL_ERROR"
            await self._events.publish(
                EventEnvelope(
                    name=f"{kind}.failed",
                    correlation_id=context.correlation_id,
                    causation_id=context.causation_id,
                    producer="platform.execution",
                    payload={
                        kind: name,
                        "run_id": str(run_id),
                        "attempt": attempt,
                        "error_code": error_code,
                    },
                )
            )
            raise
        else:
            await self._events.publish(
                EventEnvelope(
                    name=f"{kind}.completed",
                    correlation_id=context.correlation_id,
                    causation_id=context.causation_id,
                    producer="platform.execution",
                    payload={kind: name, "run_id": str(run_id), "attempt": attempt},
                )
            )
        finally:
            run_id_var.reset(run_token)
            request_id_var.reset(request_token)
