from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, cast

import yaml
from pydantic import BaseModel, ConfigDict

from tradesentinel.platform.capabilities import Capability
from tradesentinel.platform.contracts import CommandDescriptor, WorkflowDefinition
from tradesentinel.platform.errors import RegistryError
from tradesentinel.platform.events import EventBus, EventHandler
from tradesentinel.platform.registries import CapabilityRegistry, CommandRegistry, WorkflowRegistry


class ModuleManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    name: str
    version: str
    description: str
    entrypoint: str
    capabilities: tuple[str, ...]
    commands: tuple[str, ...] = ()
    intents: tuple[str, ...] = ()
    dependencies: tuple[str, ...] = ()
    provides: tuple[str, ...] = ()
    events_consumes: tuple[str, ...] = ()
    events_produces: tuple[str, ...] = ()


@dataclass(frozen=True)
class EventSubscription:
    event_name: str
    handler: EventHandler


@dataclass(frozen=True)
class ModuleRegistration:
    capabilities: tuple[Capability[Any], ...]
    commands: tuple[CommandDescriptor, ...] = ()
    workflows: tuple[WorkflowDefinition, ...] = ()
    subscriptions: tuple[EventSubscription, ...] = ()


class ModuleFactory(Protocol):
    def __call__(self) -> ModuleRegistration: ...


class ModuleLoader:
    def __init__(
        self,
        capabilities: CapabilityRegistry,
        commands: CommandRegistry,
        workflows: WorkflowRegistry,
        events: EventBus,
    ) -> None:
        self.capabilities = capabilities
        self.commands = commands
        self.workflows = workflows
        self.events = events
        self.loaded: list[ModuleManifest] = []

    def discover(self, roots: tuple[Path, ...]) -> tuple[ModuleManifest, ...]:
        manifests = sorted(path for root in roots for path in root.glob("*/manifest.yaml"))
        parsed = [
            ModuleManifest.model_validate(yaml.safe_load(path.read_text())) for path in manifests
        ]
        names = [manifest.name for manifest in parsed]
        if len(names) != len(set(names)):
            raise RegistryError("duplicate module names discovered")
        return tuple(parsed)

    def load(self, roots: tuple[Path, ...]) -> tuple[ModuleManifest, ...]:
        manifests = self.discover(roots)
        registrations: list[tuple[ModuleManifest, ModuleRegistration]] = []
        for manifest in manifests:
            module_name, separator, attribute = manifest.entrypoint.partition(":")
            if not separator:
                raise RegistryError(f"invalid module entrypoint: {manifest.entrypoint}")
            factory = cast(ModuleFactory, getattr(importlib.import_module(module_name), attribute))
            registration = factory()
            actual = {item.descriptor.name for item in registration.capabilities}
            if actual != set(manifest.capabilities):
                raise RegistryError(
                    f"module {manifest.name} capability declarations do not match registration"
                )
            registrations.append((manifest, registration))

        capability_snapshot = self.capabilities.list()
        command_snapshot = self.commands.list()
        workflow_snapshot = self.workflows.list()
        try:
            for _, registration in registrations:
                for capability in registration.capabilities:
                    self.capabilities.register(capability)
                for command in registration.commands:
                    self.commands.register(command)
                for workflow in registration.workflows:
                    self.workflows.register(workflow)
            self.capabilities.validate()
        except Exception:
            self.capabilities.restore(capability_snapshot)
            self.commands.restore(command_snapshot)
            self.workflows.restore(workflow_snapshot)
            raise
        for manifest, registration in registrations:
            for subscription in registration.subscriptions:
                self.events.subscribe(subscription.event_name, subscription.handler)
            self.loaded.append(manifest)
        return tuple(self.loaded)
