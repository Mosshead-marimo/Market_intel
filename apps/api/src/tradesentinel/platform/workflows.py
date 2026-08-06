from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from pydantic import JsonValue

from tradesentinel.platform.contracts import (
    CapabilityResult,
    CapabilityWarning,
    EventEnvelope,
    ExecutionContext,
    RunMetadata,
    RunStatus,
    WorkflowResult,
)
from tradesentinel.platform.events import EventBus
from tradesentinel.platform.persistence import RunRepository
from tradesentinel.platform.registries import CapabilityRegistry, WorkflowRegistry


class WorkflowExecutor:
    def __init__(
        self,
        workflows: WorkflowRegistry,
        capabilities: CapabilityRegistry,
        events: EventBus,
        runs: RunRepository,
    ) -> None:
        self.workflows = workflows
        self.capabilities = capabilities
        self.events = events
        self.runs = runs

    async def execute(
        self,
        name: str,
        context: ExecutionContext,
        payload: dict[str, JsonValue],
    ) -> WorkflowResult:
        definition = self.workflows.get(name)
        run_id = uuid4()
        started = datetime.now(UTC)
        context = context.model_copy(update={"workflow_run_id": run_id})
        await self.events.publish(
            EventEnvelope(
                name="workflow.started",
                correlation_id=context.correlation_id,
                causation_id=context.causation_id,
                producer="platform.workflow",
                payload={"workflow": name, "run_id": str(run_id)},
            )
        )
        pending = {step.id: step for step in definition.steps}
        results: dict[str, CapabilityResult] = {}
        warnings: list[CapabilityWarning] = []

        while pending:
            ready = [
                step
                for step in pending.values()
                if all(dependency in results for dependency in step.depends_on)
            ]
            if not ready:
                raise RuntimeError("workflow execution reached an invalid dependency state")

            runnable = []
            for step in ready:
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
                                message=(
                                    f"Skipped because dependencies failed: {failed_dependencies}"
                                ),
                            ),
                        ),
                        metadata=RunMetadata(started_at=now, completed_at=now, duration_ms=0),
                    )
                else:
                    runnable.append(step)
                pending.pop(step.id)

            executions = [
                self._execute_step(
                    step.id,
                    step.capability,
                    step.required,
                    step.depends_on,
                    context,
                    payload,
                    results,
                )
                for step in runnable
            ]
            if executions:
                completed = await asyncio.gather(*executions)
                for step_id, result, required in completed:
                    results[step_id] = result
                    if result.status == RunStatus.FAILED:
                        warnings.append(
                            CapabilityWarning(
                                code="REQUIRED_STEP_FAILED" if required else "OPTIONAL_STEP_FAILED",
                                message=f"Workflow step '{step_id}' failed.",
                            )
                        )

        required_failed = any(
            results[step.id].status in {RunStatus.FAILED, RunStatus.SKIPPED}
            for step in definition.steps
            if step.required
        )
        any_failed = any(
            result.status in {RunStatus.FAILED, RunStatus.SKIPPED} for result in results.values()
        )
        status = (
            RunStatus.FAILED
            if required_failed
            else RunStatus.PARTIAL
            if any_failed
            else RunStatus.COMPLETED
        )
        completed_at = datetime.now(UTC)
        workflow_result = WorkflowResult(
            workflow=name,
            run_id=run_id,
            status=status,
            steps=results,
            warnings=tuple(warnings),
            started_at=started,
            completed_at=completed_at,
        )
        await self.runs.save_workflow(workflow_result)
        await self.events.publish(
            EventEnvelope(
                name="workflow.completed",
                correlation_id=context.correlation_id,
                causation_id=context.causation_id,
                producer="platform.workflow",
                payload={"workflow": name, "run_id": str(run_id), "status": status.value},
            )
        )
        return workflow_result

    async def _execute_step(
        self,
        step_id: str,
        capability_name: str,
        required: bool,
        dependency_ids: tuple[str, ...],
        context: ExecutionContext,
        workflow_input: dict[str, JsonValue],
        results: dict[str, CapabilityResult],
    ) -> tuple[str, CapabilityResult, bool]:
        run_id = uuid4()
        step_context = context.model_copy(update={"capability_run_id": run_id})
        capability = self.capabilities.get(capability_name)
        dependencies = {key: results[key].data for key in dependency_ids}
        raw_payload = {**workflow_input, "dependencies": dependencies}
        try:
            result = await capability.invoke(step_context, raw_payload)
        except Exception as exc:
            now = datetime.now(UTC)
            result = CapabilityResult(
                capability=capability_name,
                status=RunStatus.FAILED,
                warnings=(CapabilityWarning(code="CAPABILITY_FAILED", message=str(exc)),),
                metadata=RunMetadata(started_at=now, completed_at=now, duration_ms=0),
            )
        await self.runs.save_capability(run_id, result)
        return step_id, result, required
