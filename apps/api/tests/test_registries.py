from datetime import UTC, datetime

import pytest
from pydantic import BaseModel
from tradesentinel.platform.capabilities import Capability, RegisteredCapability
from tradesentinel.platform.commands import CommandParser
from tradesentinel.platform.contracts import (
    CapabilityDescriptor,
    CapabilityResult,
    ExecutionContext,
    RetryPolicy,
    RunMetadata,
    RunStatus,
)
from tradesentinel.platform.errors import RegistryError
from tradesentinel.platform.registries import CapabilityRegistry, CommandRegistry


class EmptyInput(BaseModel):
    pass


class FakeCapability(Capability[EmptyInput]):
    input_model = EmptyInput

    def __init__(self, name: str, dependencies: tuple[str, ...] = ()) -> None:
        self.descriptor = CapabilityDescriptor(
            name=name, version="1.0.0", description=name, dependencies=dependencies
        )

    async def execute(self, context: ExecutionContext, payload: EmptyInput) -> CapabilityResult:
        now = datetime.now(UTC)
        return CapabilityResult(
            capability=self.descriptor.name,
            status=RunStatus.COMPLETED,
            metadata=RunMetadata(started_at=now, completed_at=now),
        )


def test_registry_rejects_duplicates() -> None:
    registry = CapabilityRegistry()
    capability = FakeCapability("one")
    registered = RegisteredCapability(capability.descriptor, capability, RetryPolicy())
    registry.register(registered)
    with pytest.raises(RegistryError, match="duplicate"):
        registry.register(registered)


def test_registry_rejects_cycles() -> None:
    registry = CapabilityRegistry()
    first = FakeCapability("one", ("two",))
    second = FakeCapability("two", ("one",))
    registry.register(RegisteredCapability(first.descriptor, first, RetryPolicy()))
    registry.register(RegisteredCapability(second.descriptor, second, RetryPolicy()))
    with pytest.raises(RegistryError, match="cycle"):
        registry.validate()


def test_command_parser_handles_options() -> None:
    from tradesentinel.platform.contracts import (
        CommandDescriptor,
        CommandOption,
        ExecutionTarget,
        TargetKind,
    )

    registry = CommandRegistry()
    registry.register(
        CommandDescriptor(
            name="/ping",
            description="Ping",
            target=ExecutionTarget(kind=TargetKind.CAPABILITY, name="system.ping"),
            options=(CommandOption(name="message", destination="message"),),
        )
    )
    parsed = CommandParser(registry).parse('/ping --message "hello world"')
    assert parsed.payload == {"message": "hello world"}
