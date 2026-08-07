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
            target, payload = await self._resolve(request, execution_context)
            result: CapabilityResult | WorkflowResult
            if target.kind == TargetKind.CAPABILITY:
                result = await self._capabilities.execute(target.name, execution_context, payload)
            else:
                result = await self._workflows.execute(target.name, execution_context, payload)
            return ExecutionOutcome(
                target=target,
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
    ) -> tuple[ExecutionTarget, dict[str, JsonValue]]:
        if isinstance(request, CommandExecutionRequest):
            parsed = self._commands.parse(request.command)
            return parsed.target, parsed.payload
        if isinstance(request, IntentExecutionRequest):
            match = await self._intent_resolver.resolve(request.text, self._intents.list(), context)
            return match.target, dict(request.payload)
        if isinstance(request, CapabilityExecutionRequest):
            return (
                ExecutionTarget(kind=TargetKind.CAPABILITY, name=request.capability),
                dict(request.payload),
            )
        if isinstance(request, WorkflowExecutionRequest):
            return (
                ExecutionTarget(kind=TargetKind.WORKFLOW, name=request.workflow),
                dict(request.payload),
            )
        raise InternalExecutionError()
