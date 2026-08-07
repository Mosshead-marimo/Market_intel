from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import JsonValue

from tradesentinel.platform.context import ExecutionContextManager
from tradesentinel.platform.contracts import (
    CapabilityResult,
    CapabilityWarning,
    ExecutionContext,
    RunMetadata,
    RunStatus,
    WorkflowDefinition,
    WorkflowResult,
    WorkflowStep,
)
from tradesentinel.platform.errors import DomainError, WorkflowCompilationError
from tradesentinel.platform.execution import CapabilityExecutor
from tradesentinel.platform.persistence import RunRepository
from tradesentinel.platform.registries import WorkflowRegistry


class WorkflowEngine:
    def compile(self, definition: WorkflowDefinition) -> tuple[tuple[WorkflowStep, ...], ...]:
        pending = {step.id: step for step in definition.steps}
        compiled: set[str] = set()
        layers: list[tuple[WorkflowStep, ...]] = []
        while pending:
            ready = tuple(
                step
                for step in definition.steps
                if step.id in pending and set(step.depends_on) <= compiled
            )
            if not ready:
                raise WorkflowCompilationError(
                    f"Workflow '{definition.name}' contains an unresolved dependency cycle."
                )
            layers.append(ready)
            for step in ready:
                pending.pop(step.id)
                compiled.add(step.id)
        return tuple(layers)


class WorkflowExecutor:
    def __init__(
        self,
        workflows: WorkflowRegistry,
        engine: WorkflowEngine,
        capabilities: CapabilityExecutor,
        contexts: ExecutionContextManager,
        runs: RunRepository,
    ) -> None:
        self._workflows = workflows
        self._engine = engine
        self._capabilities = capabilities
        self._contexts = contexts
        self._runs = runs

    async def execute(
        self,
        name: str,
        context: ExecutionContext,
        payload: dict[str, JsonValue],
    ) -> WorkflowResult:
        definition = self._workflows.get(name)
        layers = self._engine.compile(definition)
        run_id = uuid4()
        started = datetime.now(UTC)
        results: dict[str, CapabilityResult] = {}
        warnings: list[CapabilityWarning] = []

        async with self._contexts.workflow_scope(context, name, run_id) as workflow_context:
            for layer in layers:
                runnable: list[WorkflowStep] = []
                for step in layer:
                    failed_dependencies = [
                        dependency
                        for dependency in step.depends_on
                        if results[dependency].status in {RunStatus.FAILED, RunStatus.SKIPPED}
                    ]
                    if failed_dependencies:
                        now = datetime.now(UTC)
                        results[step.id] = CapabilityResult(
                            capability=step.capability,
                            status=RunStatus.SKIPPED,
                            warnings=(
                                CapabilityWarning(
                                    code="DEPENDENCY_FAILED",
                                    message="A required dependency did not complete.",
                                    details={"dependencies": failed_dependencies},
                                ),
                            ),
                            metadata=RunMetadata(started_at=now, completed_at=now, duration_ms=0),
                        )
                    else:
                        runnable.append(step)
                completed = await asyncio.gather(
                    *(
                        self._execute_step(step, workflow_context, payload, results)
                        for step in runnable
                    )
                )
                for step_id, result, required in completed:
                    results[step_id] = result
                    if result.status == RunStatus.FAILED:
                        warnings.append(
                            CapabilityWarning(
                                code=(
                                    "REQUIRED_STEP_FAILED" if required else "OPTIONAL_STEP_FAILED"
                                ),
                                message=f"Workflow step '{step_id}' failed.",
                            )
                        )

        ordered_results = {step.id: results[step.id] for step in definition.steps}
        required_failed = any(
            ordered_results[step.id].status in {RunStatus.FAILED, RunStatus.SKIPPED}
            for step in definition.steps
            if step.required
        )
        any_failed = any(
            result.status in {RunStatus.FAILED, RunStatus.SKIPPED}
            for result in ordered_results.values()
        )
        status = (
            RunStatus.FAILED
            if required_failed
            else RunStatus.PARTIAL
            if any_failed
            else RunStatus.COMPLETED
        )
        outcome = WorkflowResult(
            workflow=name,
            run_id=run_id,
            status=status,
            steps=ordered_results,
            warnings=tuple(warnings),
            started_at=started,
            completed_at=datetime.now(UTC),
        )
        await self._runs.save_workflow(outcome)
        return outcome

    async def _execute_step(
        self,
        step: WorkflowStep,
        context: ExecutionContext,
        workflow_input: dict[str, JsonValue],
        results: dict[str, CapabilityResult],
    ) -> tuple[str, CapabilityResult, bool]:
        dependency_data = {key: results[key].data for key in step.depends_on}
        raw_payload = {**workflow_input, "dependencies": dependency_data}
        try:
            result = await self._capabilities.execute(step.capability, context, raw_payload)
        except DomainError as exc:
            now = datetime.now(UTC)
            result = CapabilityResult(
                capability=step.capability,
                status=RunStatus.FAILED,
                warnings=(
                    CapabilityWarning(
                        code=exc.code,
                        message="The workflow step could not be completed.",
                        retryable=exc.retryable,
                    ),
                ),
                metadata=RunMetadata(started_at=now, completed_at=now, duration_ms=0),
            )
        return step.id, result, step.required
