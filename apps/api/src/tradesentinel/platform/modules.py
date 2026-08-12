from __future__ import annotations

import importlib
import inspect
from pathlib import Path
from typing import Any

from tradesentinel.platform.background import BackgroundWorker
from tradesentinel.platform.capabilities import Capability, RegisteredCapability
from tradesentinel.platform.contracts import (
    CapabilityDescriptor,
    CapabilityExecutionRequest,
    CommandDescriptor,
    EventEnvelope,
    ExecutionContext,
    ExecutionTarget,
    IntentDescriptor,
    WorkflowExecutionRequest,
)
from tradesentinel.platform.dependencies import DependencyResolver
from tradesentinel.platform.errors import DiscoveryError, RegistryError
from tradesentinel.platform.events import EventBus
from tradesentinel.platform.manifest import ManifestParser, ModuleManifest
from tradesentinel.platform.registries import (
    CapabilityRegistry,
    CommandRegistry,
    IntentRegistry,
    WorkflowRegistry,
)


class ModuleLoader:
    def __init__(
        self,
        capabilities: CapabilityRegistry,
        commands: CommandRegistry,
        intents: IntentRegistry,
        workflows: WorkflowRegistry,
        events: EventBus,
        resolver: DependencyResolver,
        parser: ManifestParser | None = None,
    ) -> None:
        self.capabilities = capabilities
        self.commands = commands
        self.intents = intents
        self.workflows = workflows
        self.events = events
        self.resolver = resolver
        self.parser = parser or ManifestParser()
        self.loaded: tuple[ModuleManifest, ...] = ()
        self.background_workers: tuple[BackgroundWorker, ...] = ()

    def discover(self, roots: tuple[Path, ...]) -> tuple[ModuleManifest, ...]:
        paths = sorted(
            {path.resolve() for root in roots for path in root.resolve().rglob("manifest.yaml")},
            key=lambda path: path.as_posix().casefold(),
        )
        manifests = tuple(self.parser.parse(path) for path in paths)
        names = [manifest.name for manifest in manifests]
        if len(names) != len(set(names)):
            raise RegistryError("duplicate module names discovered")
        return manifests

    def load(self, roots: tuple[Path, ...]) -> tuple[ModuleManifest, ...]:
        manifests = self.discover(roots)
        return self.load_manifests(manifests)

    def load_manifests(self, manifests: tuple[ModuleManifest, ...]) -> tuple[ModuleManifest, ...]:
        staged_capabilities = CapabilityRegistry()
        staged_commands = CommandRegistry()
        staged_intents = IntentRegistry()
        staged_workflows = WorkflowRegistry(staged_capabilities)
        staged_background_workers: list[BackgroundWorker] = []

        for manifest in manifests:
            for capability_declaration in manifest.capabilities:
                capability_class = self._import_capability(capability_declaration.class_path)
                implementation = self.resolver.resolve(capability_class)
                staged_capabilities.register(
                    RegisteredCapability(
                        descriptor=CapabilityDescriptor(
                            name=capability_declaration.name,
                            version=capability_declaration.version or manifest.version,
                            description=capability_declaration.description,
                            dependencies=capability_declaration.dependencies,
                            permissions=capability_declaration.permissions,
                            provides=capability_declaration.provides,
                            idempotent=capability_declaration.idempotent,
                        ),
                        implementation=implementation,
                        retry_policy=capability_declaration.retry,
                    )
                )
        staged_capabilities.validate()

        for manifest in manifests:
            for declaration in manifest.background_workers:
                worker_class = self._import_background_worker(declaration.class_path)
                staged_background_workers.append(self.resolver.resolve(worker_class))

        for manifest in manifests:
            for command_declaration in manifest.commands:
                self._validate_target(command_declaration.target, staged_capabilities)
                staged_commands.register(
                    CommandDescriptor(
                        name=command_declaration.name,
                        description=command_declaration.description,
                        target=command_declaration.target,
                        arguments=command_declaration.arguments,
                        options=command_declaration.options,
                        examples=command_declaration.examples,
                        planner_enabled=command_declaration.planner_enabled,
                        side_effect=command_declaration.side_effect,
                    )
                )
            for intent_declaration in manifest.intents:
                self._validate_target(intent_declaration.target, staged_capabilities)
                staged_intents.register(IntentDescriptor(**intent_declaration.model_dump()))
            for workflow in manifest.workflows:
                staged_workflows.register(workflow)

        staged_intents.validate()

        for manifest in manifests:
            for command in manifest.commands:
                self._validate_final_target(command.target, staged_capabilities, staged_workflows)
            for intent in manifest.intents:
                self._validate_final_target(intent.target, staged_capabilities, staged_workflows)
            for consumer in manifest.events.consumes:
                self._validate_final_target(consumer.target, staged_capabilities, staged_workflows)

        self.capabilities.restore(staged_capabilities.list())
        self.commands.restore(staged_commands.list())
        self.intents.restore(staged_intents.list())
        self.workflows.restore(staged_workflows.list())
        self.loaded = manifests
        self.background_workers = tuple(staged_background_workers)
        return manifests

    def bind_event_consumers(self, pipeline: Any) -> None:
        for manifest in self.loaded:
            for consumer in manifest.events.consumes:
                target = consumer.target

                async def handler(event: EventEnvelope, target: ExecutionTarget = target) -> None:
                    context = ExecutionContext(
                        correlation_id=event.correlation_id,
                        causation_id=event.event_id,
                    )
                    request = (
                        CapabilityExecutionRequest(capability=target.name, payload=event.payload)
                        if target.kind.value == "capability"
                        else WorkflowExecutionRequest(workflow=target.name, payload=event.payload)
                    )
                    await pipeline.execute(request, context)

                self.events.subscribe(consumer.name, handler)

    @staticmethod
    def _import_capability(class_path: str) -> type[Capability[Any]]:
        module_name, separator, attribute = class_path.partition(":")
        if not separator:
            raise DiscoveryError("Capability class paths must use 'module:Class'.")
        try:
            candidate = getattr(importlib.import_module(module_name), attribute)
        except (ImportError, AttributeError) as exc:
            raise DiscoveryError(
                "A capability class could not be imported.", {"class_path": class_path}
            ) from exc
        if not inspect.isclass(candidate) or not issubclass(candidate, Capability):
            raise DiscoveryError(
                "A declared capability class does not implement Capability.",
                {"class_path": class_path},
            )
        if inspect.isabstract(candidate):
            raise DiscoveryError(
                "A declared capability class is abstract.", {"class_path": class_path}
            )
        return candidate

    @staticmethod
    def _import_background_worker(class_path: str) -> type[BackgroundWorker]:
        module_name, separator, attribute = class_path.partition(":")
        if not separator:
            raise DiscoveryError("Background worker class paths must use 'module:Class'.")
        try:
            candidate = getattr(importlib.import_module(module_name), attribute)
        except (ImportError, AttributeError) as exc:
            raise DiscoveryError(
                "A background worker class could not be imported.", {"class_path": class_path}
            ) from exc
        if not inspect.isclass(candidate) or not issubclass(candidate, BackgroundWorker):
            raise DiscoveryError(
                "A declared background worker does not implement BackgroundWorker.",
                {"class_path": class_path},
            )
        return candidate

    @staticmethod
    def _validate_target(target: ExecutionTarget, capabilities: CapabilityRegistry) -> None:
        if target.kind.value == "capability":
            capabilities.get(target.name)

    @staticmethod
    def _validate_final_target(
        target: ExecutionTarget,
        capabilities: CapabilityRegistry,
        workflows: WorkflowRegistry,
    ) -> None:
        if target.kind.value == "capability":
            capabilities.get(target.name)
        else:
            workflows.get(target.name)
