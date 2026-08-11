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
from tradesentinel.platform.errors import (
    DomainError,
    WorkflowCompilationError,
    WorkflowInputBindingError,
)
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
            presentation=definition.presentation,
        )
        await self._runs.save_workflow(outcome)
        if (
            definition.presentation is not None
            and definition.presentation.completion_event is not None
        ):
            section_statuses: dict[str, JsonValue] = {}
            section_counts: dict[str, JsonValue] = {}
            for section in definition.presentation.sections:
                section_results = tuple(outcome.steps[step_id] for step_id in section.steps)
                section_statuses[section.id] = (
                    "error"
                    if any(
                        item.status in {RunStatus.FAILED, RunStatus.SKIPPED}
                        for item in section_results
                    )
                    else "partial"
                    if any(item.status == RunStatus.PARTIAL for item in section_results)
                    else "ready"
                )
                section_counts[section.id] = sum(
                    item.status in {RunStatus.COMPLETED, RunStatus.PARTIAL}
                    for item in section_results
                )
            cutoffs = tuple(
                item.metadata.data_cutoff
                for item in outcome.steps.values()
                if item.metadata.data_cutoff is not None
            )
            await self._contexts.emit(
                workflow_context,
                definition.presentation.completion_event,
                "platform.workflow",
                {
                    "workflow": name,
                    "run_id": str(run_id),
                    "request_id": str(workflow_context.request_id),
                    "status": status.value,
                    "sections": {key: value for key, value in section_statuses.items()},
                    "section_counts": {key: value for key, value in section_counts.items()},
                    "data_cutoff": max(cutoffs).isoformat() if cutoffs else None,
                },
            )
        return outcome

    async def _execute_step(
        self,
        step: WorkflowStep,
        context: ExecutionContext,
        workflow_input: dict[str, JsonValue],
        results: dict[str, CapabilityResult],
    ) -> tuple[str, CapabilityResult, bool]:
        dependency_data: dict[str, JsonValue] = {key: results[key].data for key in step.depends_on}
        if step.input_bindings:
            raw_payload: dict[str, JsonValue] = {}
            step_values: dict[str, JsonValue] = {
                key: {"data": value} for key, value in dependency_data.items()
            }
            roots: dict[str, JsonValue] = {
                "input": workflow_input,
                "steps": step_values,
            }
            for destination, binding in step.input_bindings.items():
                found, value = self._resolve_binding(roots, binding.source)
                if found:
                    self._set_destination(raw_payload, destination, value, step.id)
                elif binding.required:
                    raise WorkflowInputBindingError(step.id, destination, binding.source)
        else:
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

    @staticmethod
    def _resolve_binding(root: dict[str, JsonValue], source: str) -> tuple[bool, JsonValue]:
        current: JsonValue = root
        for part in source.split("."):
            if not isinstance(current, dict) or part not in current:
                return False, None
            current = current[part]
        return True, current

    @staticmethod
    def _set_destination(
        root: dict[str, JsonValue], destination: str, value: JsonValue, step_id: str
    ) -> None:
        parts = destination.split(".")
        current: dict[str, JsonValue] = root
        for index, part in enumerate(parts[:-1]):
            next_part = parts[index + 1]
            existing = current.get(part)
            if next_part.isdigit():
                if existing is None:
                    existing = []
                    current[part] = existing
                if not isinstance(existing, list):
                    raise WorkflowInputBindingError(step_id, destination, destination)
                position = int(next_part)
                while len(existing) <= position:
                    existing.append(None)
                if index + 1 == len(parts) - 1:
                    existing[position] = value
                    return
                raise WorkflowInputBindingError(step_id, destination, destination)
            if existing is None:
                nested: dict[str, JsonValue] = {}
                current[part] = nested
                current = nested
            elif isinstance(existing, dict):
                current = existing
            else:
                raise WorkflowInputBindingError(step_id, destination, destination)
        current[parts[-1]] = value
