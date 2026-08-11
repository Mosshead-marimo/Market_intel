from __future__ import annotations

from typing import TYPE_CHECKING

from tradesentinel.platform.commands import CommandParser
from tradesentinel.platform.contracts import (
    CommandDescriptor,
    CommandExecutionRequest,
    ExecutionContext,
    ExecutionOutcome,
)
from tradesentinel.platform.errors import CommandSyntaxError, InternalExecutionError
from tradesentinel.platform.registries import CommandRegistry

if TYPE_CHECKING:
    from tradesentinel.platform.pipeline import ExecutionPipeline


class ExecutionGateway:
    """Domain-neutral, late-bound access to planner-safe registered commands."""

    def __init__(self, commands: CommandRegistry) -> None:
        self._commands = commands
        self._pipeline: ExecutionPipeline | None = None

    def bind(self, pipeline: ExecutionPipeline) -> None:
        if self._pipeline is not None:
            raise InternalExecutionError()
        self._pipeline = pipeline

    def planner_commands(self) -> tuple[CommandDescriptor, ...]:
        return tuple(
            command
            for command in self._commands.list()
            if command.planner_enabled and command.side_effect == "read"
        )

    def validate_planned(self, command: str) -> None:
        parsed = CommandParser(self._commands).parse(command)
        name = command.split(maxsplit=1)[0]
        descriptor = self._commands.get(name)
        if not descriptor.planner_enabled or descriptor.side_effect != "read":
            raise CommandSyntaxError(
                "The command is not available to the conversation planner.",
                {"command": name},
            )
        del parsed

    async def execute(self, command: str, context: ExecutionContext) -> ExecutionOutcome:
        if self._pipeline is None:
            raise InternalExecutionError()
        return await self._pipeline.execute(CommandExecutionRequest(command=command), context)
