from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog
from pydantic import ValidationError

from tradesentinel.platform.context import ExecutionContextManager
from tradesentinel.platform.contracts import (
    CapabilityResult,
    CapabilityWarning,
    ExecutionContext,
    RunMetadata,
    RunStatus,
)
from tradesentinel.platform.errors import (
    CapabilityOutputError,
    DomainError,
    InternalExecutionError,
    PayloadValidationError,
    PermissionDeniedError,
)
from tradesentinel.platform.persistence import RunRepository
from tradesentinel.platform.registries import CapabilityRegistry
from tradesentinel.platform.retry import RetryStrategy


class CapabilityExecutor:
    def __init__(
        self,
        capabilities: CapabilityRegistry,
        contexts: ExecutionContextManager,
        retries: RetryStrategy,
        runs: RunRepository,
    ) -> None:
        self._capabilities = capabilities
        self._contexts = contexts
        self._retries = retries
        self._runs = runs

    async def execute(
        self,
        capability_name: str,
        context: ExecutionContext,
        raw_payload: object,
    ) -> CapabilityResult:
        registered = self._capabilities.get(capability_name)
        missing_permissions = sorted(
            set(registered.descriptor.permissions) - set(context.permissions)
        )
        if missing_permissions:
            raise PermissionDeniedError(missing_permissions)
        try:
            payload = registered.implementation.input_model.model_validate(raw_payload)
        except ValidationError as exc:
            raise PayloadValidationError(exc.errors(include_url=False)) from exc

        run_id = uuid4()
        started = datetime.now(UTC)
        policy = (
            registered.retry_policy
            if registered.descriptor.idempotent
            else registered.retry_policy.model_copy(update={"max_attempts": 1})
        )

        async def operation(attempt: int) -> CapabilityResult:
            async with self._contexts.capability_scope(
                context, capability_name, run_id, attempt
            ) as scoped_context:
                return await registered.implementation.execute(scoped_context, payload)

        try:
            result, attempts = await self._retries.execute(operation, policy)
        except DomainError as exc:
            await self._save_failure(capability_name, run_id, started, exc.code)
            raise
        except Exception as exc:
            structlog.get_logger().exception(
                "capability_execution_failed",
                capability=capability_name,
                error_type=type(exc).__name__,
            )
            await self._save_failure(capability_name, run_id, started, "EXECUTION_FAILED")
            raise InternalExecutionError() from exc

        if not isinstance(result, CapabilityResult):
            await self._save_failure(capability_name, run_id, started, "CAPABILITY_OUTPUT_INVALID")
            raise CapabilityOutputError()

        completed = datetime.now(UTC)
        metadata = result.metadata.model_copy(
            update={
                "run_id": run_id,
                "started_at": started,
                "completed_at": completed,
                "duration_ms": max(0, int((completed - started).total_seconds() * 1_000)),
                "attempts": attempts,
            }
        )
        normalized = result.model_copy(
            update={"capability": registered.descriptor.name, "metadata": metadata}
        )
        await self._runs.save_capability(run_id, normalized)
        return normalized

    async def _save_failure(
        self, capability_name: str, run_id: UUID, started: datetime, error_code: str
    ) -> None:
        completed = datetime.now(UTC)
        failed = CapabilityResult(
            capability=capability_name,
            status=RunStatus.FAILED,
            warnings=(
                CapabilityWarning(
                    code=error_code,
                    message="The capability execution failed.",
                ),
            ),
            metadata=RunMetadata(
                run_id=run_id,
                started_at=started,
                completed_at=completed,
                duration_ms=max(0, int((completed - started).total_seconds() * 1_000)),
            ),
        )
        await self._runs.save_capability(run_id, failed)
