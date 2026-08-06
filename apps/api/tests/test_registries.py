from datetime import UTC, datetime

import pytest
from pydantic import BaseModel
from tradesentinel.platform.capabilities import Capability
from tradesentinel.platform.contracts import (
    CapabilityDescriptor,
    CapabilityResult,
    ExecutionContext,
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
    registry.register(FakeCapability("one"))
    with pytest.raises(RegistryError, match="duplicate"):
        registry.register(FakeCapability("one"))


def test_registry_rejects_cycles() -> None:
    registry = CapabilityRegistry()
    registry.register(FakeCapability("one", ("two",)))
    registry.register(FakeCapability("two", ("one",)))
    with pytest.raises(RegistryError, match="cycle"):
        registry.validate()


def test_command_parser_handles_options() -> None:
    from tradesentinel.platform.contracts import CommandDescriptor

    registry = CommandRegistry()
    registry.register(CommandDescriptor(name="/ping", description="Ping", capability="system.ping"))
    parsed = registry.parse("/ping --message hello")
    assert parsed.options == {"message": "hello"}
