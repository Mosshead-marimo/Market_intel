from __future__ import annotations

from collections.abc import Iterable

from tradesentinel.platform.capabilities import RegisteredCapability
from tradesentinel.platform.contracts import CommandDescriptor, IntentDescriptor, WorkflowDefinition
from tradesentinel.platform.errors import RegistryError


class CapabilityRegistry:
    def __init__(self) -> None:
        self._items: dict[str, RegisteredCapability] = {}

    def register(self, capability: RegisteredCapability) -> None:
        name = capability.descriptor.name
        if name in self._items:
            raise RegistryError(f"duplicate capability: {name}")
        self._items[name] = capability

    def get(self, name: str) -> RegisteredCapability:
        try:
            return self._items[name]
        except KeyError as exc:
            raise RegistryError(f"unknown capability: {name}") from exc

    def list(self) -> tuple[RegisteredCapability, ...]:
        return tuple(self._items[name] for name in sorted(self._items))

    def restore(self, items: Iterable[RegisteredCapability]) -> None:
        self._items = {item.descriptor.name: item for item in items}

    def validate(self) -> None:
        names = set(self._items)
        for capability in self._items.values():
            missing = set(capability.descriptor.dependencies) - names
            if missing:
                raise RegistryError(
                    f"capability {capability.descriptor.name} has missing dependencies",
                    {"dependencies": sorted(missing)},
                )
        self._assert_acyclic(
            {name: set(item.descriptor.dependencies) for name, item in self._items.items()},
            "capability",
        )

    @staticmethod
    def _assert_acyclic(graph: dict[str, set[str]], kind: str) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise RegistryError(f"{kind} dependency cycle detected at {node}")
            if node in visited:
                return
            visiting.add(node)
            for dependency in graph.get(node, set()):
                visit(dependency)
            visiting.remove(node)
            visited.add(node)

        for node in sorted(graph):
            visit(node)


class CommandRegistry:
    def __init__(self) -> None:
        self._items: dict[str, CommandDescriptor] = {}

    def register(self, command: CommandDescriptor) -> None:
        if command.name in self._items:
            raise RegistryError(f"duplicate command: {command.name}")
        self._items[command.name] = command

    def get(self, name: str) -> CommandDescriptor:
        try:
            return self._items[name]
        except KeyError as exc:
            raise RegistryError(f"unknown command: {name}") from exc

    def list(self) -> tuple[CommandDescriptor, ...]:
        return tuple(self._items[name] for name in sorted(self._items))

    def restore(self, items: Iterable[CommandDescriptor]) -> None:
        self._items = {item.name: item for item in items}


class IntentRegistry:
    def __init__(self) -> None:
        self._items: dict[str, IntentDescriptor] = {}

    def register(self, intent: IntentDescriptor) -> None:
        if intent.name in self._items:
            raise RegistryError(f"duplicate intent: {intent.name}")
        self._items[intent.name] = intent

    def get(self, name: str) -> IntentDescriptor:
        try:
            return self._items[name]
        except KeyError as exc:
            raise RegistryError(f"unknown intent: {name}") from exc

    def list(self) -> tuple[IntentDescriptor, ...]:
        return tuple(self._items[name] for name in sorted(self._items))

    def restore(self, items: Iterable[IntentDescriptor]) -> None:
        self._items = {item.name: item for item in items}


class WorkflowRegistry:
    def __init__(self, capabilities: CapabilityRegistry) -> None:
        self._capabilities = capabilities
        self._items: dict[str, WorkflowDefinition] = {}

    def register(self, workflow: WorkflowDefinition) -> None:
        if workflow.name in self._items:
            raise RegistryError(f"duplicate workflow: {workflow.name}")
        step_ids = {step.id for step in workflow.steps}
        graph = {step.id: set(step.depends_on) for step in workflow.steps}
        if set().union(*graph.values(), set()) - step_ids:
            raise RegistryError(f"workflow {workflow.name} has unknown step dependencies")
        CapabilityRegistry._assert_acyclic(graph, "workflow")
        for step in workflow.steps:
            self._capabilities.get(step.capability)
        self._items[workflow.name] = workflow

    def get(self, name: str) -> WorkflowDefinition:
        try:
            return self._items[name]
        except KeyError as exc:
            raise RegistryError(f"unknown workflow: {name}") from exc

    def list(self) -> tuple[WorkflowDefinition, ...]:
        return tuple(self._items[name] for name in sorted(self._items))

    def restore(self, items: Iterable[WorkflowDefinition]) -> None:
        self._items = {item.name: item for item in items}

    def register_many(self, workflows: Iterable[WorkflowDefinition]) -> None:
        for workflow in workflows:
            self.register(workflow)
