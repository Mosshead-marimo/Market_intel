from __future__ import annotations

import structlog
from pydantic import JsonValue

from tradesentinel.platform.commands import CommandParser
from tradesentinel.platform.context import ExecutionContextManager
from tradesentinel.platform.contracts import (
    CapabilityExecutionRequest,
    CapabilityResult,
    CommandExecutionRequest,
    ExecutionContext,
    ExecutionOutcome,
    ExecutionPlan,
    ExecutionRequest,
    ExecutionTarget,
    IntentExecutionRequest,
    TargetKind,
    WorkflowExecutionRequest,
    WorkflowResult,
)
from tradesentinel.platform.errors import DomainError, InternalExecutionError
from tradesentinel.platform.execution import CapabilityExecutor
from tradesentinel.platform.intents import IntentResolver
from tradesentinel.platform.registries import IntentRegistry
from tradesentinel.platform.rendering import ResponseRenderer
from tradesentinel.platform.workflows import WorkflowExecutor


class ExecutionPipeline:
    def __init__(
        self,
        commands: CommandParser,
        intents: IntentRegistry,
        intent_resolver: IntentResolver,
        capabilities: CapabilityExecutor,
        workflows: WorkflowExecutor,
        contexts: ExecutionContextManager,
        renderer: ResponseRenderer,
    ) -> None:
        self._commands = commands
        self._intents = intents
        self._intent_resolver = intent_resolver
        self._capabilities = capabilities
        self._workflows = workflows
        self._contexts = contexts
        self._renderer = renderer

    async def execute(
        self,
        request: ExecutionRequest,
        context: ExecutionContext | None = None,
    ) -> ExecutionOutcome:
        execution_context = context or self._contexts.create()
        try:
            plan = await self.plan(request, execution_context)
            return await self.execute_plan(plan, execution_context)
        except DomainError:
            raise
        except Exception as exc:
            structlog.get_logger().exception(
                "execution_pipeline_failed", error_type=type(exc).__name__
            )
            raise InternalExecutionError() from exc

    async def plan(self, request: ExecutionRequest, context: ExecutionContext) -> ExecutionPlan:
        target, payload, intent, confidence = await self._resolve(request, context)
        return ExecutionPlan(
            request=request,
            target=target,
            payload=payload,
            intent=intent,
            confidence=confidence,
        )

    async def execute_plan(
        self, plan: ExecutionPlan, context: ExecutionContext
    ) -> ExecutionOutcome:
        try:
            result: CapabilityResult | WorkflowResult
            if plan.target.kind == TargetKind.CAPABILITY:
                result = await self._capabilities.execute(plan.target.name, context, plan.payload)
            else:
                result = await self._workflows.execute(plan.target.name, context, plan.payload)
            return ExecutionOutcome(
                target=plan.target,
                result=result,
                response=self._renderer.render(result),
            )
        except DomainError:
            raise
        except Exception as exc:
            structlog.get_logger().exception(
                "execution_pipeline_failed", error_type=type(exc).__name__
            )
            raise InternalExecutionError() from exc

    async def _resolve(
        self, request: ExecutionRequest, context: ExecutionContext
    ) -> tuple[ExecutionTarget, dict[str, JsonValue], str | None, float | None]:
        if isinstance(request, CommandExecutionRequest):
            parsed = self._commands.parse(request.command)
            return parsed.target, parsed.payload, None, None
        if isinstance(request, IntentExecutionRequest):
            match = await self._intent_resolver.resolve(request.text, self._intents.list(), context)
            payload = dict(request.payload)
            payload[match.input_field] = request.text
            return match.target, payload, match.intent, match.confidence
        if isinstance(request, CapabilityExecutionRequest):
            return (
                ExecutionTarget(kind=TargetKind.CAPABILITY, name=request.capability),
                dict(request.payload),
                None,
                None,
            )
        if isinstance(request, WorkflowExecutionRequest):
            return (
                ExecutionTarget(kind=TargetKind.WORKFLOW, name=request.workflow),
                dict(request.payload),
                None,
                None,
            )
        raise InternalExecutionError()
