from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import BaseModel
from support.fake_market_provider import market_test_settings
from tradesentinel.container import build_container
from tradesentinel.platform.capabilities import Capability, RegisteredCapability
from tradesentinel.platform.commands import CommandParser
from tradesentinel.platform.context import ExecutionContextManager
from tradesentinel.platform.contracts import (
    CapabilityExecutionRequest,
    CapabilityResult,
    CapabilityWarning,
    CommandExecutionRequest,
    ComponentStatus,
    EvidenceSource,
    ExecutionContext,
    ExecutionTarget,
    IntentDescriptor,
    IntentExecutionRequest,
    MetricGrid,
    MetricItem,
    RetryPolicy,
    RunMetadata,
    RunStatus,
    TargetKind,
    WorkflowDefinition,
    WorkflowExecutionRequest,
    WorkflowInputBinding,
    WorkflowStep,
)
from tradesentinel.platform.dependencies import DependencyResolver
from tradesentinel.platform.errors import (
    CommandSyntaxError,
    DependencyResolutionError,
    EventBusError,
    IntentAmbiguousError,
    IntentNotResolvedError,
    ManifestError,
    PermissionDeniedError,
    RetryExhaustedError,
    TransientPlatformError,
)
from tradesentinel.platform.events import InMemoryEventBus
from tradesentinel.platform.execution import CapabilityExecutor
from tradesentinel.platform.intents import ExactExampleIntentResolver
from tradesentinel.platform.logging import request_id_var, run_id_var
from tradesentinel.platform.modules import ModuleLoader
from tradesentinel.platform.persistence import InMemoryRunRepository
from tradesentinel.platform.registries import (
    CapabilityRegistry,
    CommandRegistry,
    IntentRegistry,
    WorkflowRegistry,
)
from tradesentinel.platform.rendering import ResponseRenderer
from tradesentinel.platform.retry import RetryStrategy
from tradesentinel.platform.workflows import WorkflowEngine, WorkflowExecutor


class StepInput(BaseModel):
    dependencies: dict[str, object] = {}


class SuccessfulCapability(Capability[StepInput]):
    input_model = StepInput

    async def execute(self, context: ExecutionContext, payload: StepInput) -> CapabilityResult:
        del context
        now = datetime.now(UTC)
        return CapabilityResult(
            capability="",
            status=RunStatus.COMPLETED,
            data={"dependency_count": len(payload.dependencies)},
            summary="completed",
            metadata=RunMetadata(started_at=now, completed_at=now),
        )


class FailingCapability(Capability[StepInput]):
    input_model = StepInput

    async def execute(self, context: ExecutionContext, payload: StepInput) -> CapabilityResult:
        del context, payload
        raise ValueError("private failure detail")


def _loader() -> tuple[ModuleLoader, CapabilityRegistry]:
    capabilities = CapabilityRegistry()
    commands = CommandRegistry()
    intents = IntentRegistry()
    workflows = WorkflowRegistry(capabilities)
    return (
        ModuleLoader(
            capabilities,
            commands,
            intents,
            workflows,
            InMemoryEventBus(),
            DependencyResolver(),
        ),
        capabilities,
    )


def _manifest(class_path: str) -> str:
    return f"""
name: example.module
version: 1.0.0
description: Automatic example
capabilities:
  - name: example.ping
    class_path: {class_path}
    description: Example capability
"""


def test_recursive_manifest_and_class_discovery_requires_no_plugin(tmp_path: Path) -> None:
    module = tmp_path / "nested" / "example"
    module.mkdir(parents=True)
    (module / "manifest.yaml").write_text(
        _manifest("tradesentinel.modules.system.capability:SystemPingCapability"),
        encoding="utf-8",
    )
    loader, capabilities = _loader()
    loaded = loader.load((tmp_path,))
    assert [item.name for item in loaded] == ["example.module"]
    assert capabilities.get("example.ping").implementation.__class__.__name__ == (
        "SystemPingCapability"
    )


def test_loader_is_atomic_when_any_class_is_invalid(tmp_path: Path) -> None:
    valid = tmp_path / "a"
    invalid = tmp_path / "b"
    valid.mkdir()
    invalid.mkdir()
    (valid / "manifest.yaml").write_text(
        _manifest("tradesentinel.modules.system.capability:SystemPingCapability"),
        encoding="utf-8",
    )
    (invalid / "manifest.yaml").write_text(
        _manifest("tradesentinel.modules.system.service:SystemService").replace(
            "example.module", "invalid.module"
        ),
        encoding="utf-8",
    )
    loader, capabilities = _loader()
    with pytest.raises(Exception, match="does not implement Capability"):
        loader.load((tmp_path,))
    assert capabilities.list() == ()


def test_manifest_parser_rejects_unknown_fields(tmp_path: Path) -> None:
    module = tmp_path / "bad"
    module.mkdir()
    (module / "manifest.yaml").write_text(
        _manifest("tradesentinel.modules.system.capability:SystemPingCapability")
        + "unknown: true\n",
        encoding="utf-8",
    )
    loader, _ = _loader()
    with pytest.raises(ManifestError):
        loader.discover((tmp_path,))


def test_dependency_resolver_rejects_untyped_required_constructor() -> None:
    class Untyped:
        def __init__(self, value):
            self.value = value

    with pytest.raises(DependencyResolutionError, match="could not be resolved"):
        DependencyResolver().resolve(Untyped)


async def test_exact_intent_resolution_and_ambiguity() -> None:
    resolver = ExactExampleIntentResolver()
    context = ExecutionContext()
    target = ExecutionTarget(kind=TargetKind.CAPABILITY, name="system.ping")
    intents = (
        IntentDescriptor(
            name="health.low",
            description="low",
            examples=("System   Health",),
            priority=0,
            target=target,
        ),
        IntentDescriptor(
            name="health.high",
            description="high",
            examples=("system health",),
            priority=1,
            target=target,
        ),
    )
    match = await resolver.resolve(" SYSTEM health ", intents, context)
    assert match.intent == "health.high"
    with pytest.raises(IntentNotResolvedError):
        await resolver.resolve("unmatched", intents, context)
    conflicting = (
        *intents,
        IntentDescriptor(
            name="health.other",
            description="other",
            examples=("system health",),
            priority=1,
            target=ExecutionTarget(kind=TargetKind.WORKFLOW, name="system.health"),
        ),
    )
    with pytest.raises(IntentAmbiguousError):
        await resolver.resolve("system health", conflicting, context)


async def test_retry_strategy_retries_transient_errors_with_bounded_delay() -> None:
    delays: list[float] = []
    attempts = 0

    async def sleep(delay: float) -> None:
        delays.append(delay)

    async def operation(attempt: int) -> str:
        nonlocal attempts
        attempts = attempt
        if attempt < 3:
            raise ConnectionError("temporary")
        return "ok"

    result, used_attempts = await RetryStrategy(sleep, lambda: 0.5).execute(
        operation,
        RetryPolicy(
            max_attempts=3,
            initial_delay_ms=100,
            multiplier=2,
            max_delay_ms=150,
            jitter_ratio=0,
        ),
    )
    assert result == "ok"
    assert used_attempts == attempts == 3
    assert delays == [0.1, 0.15]


async def test_retry_strategy_exhaustion_and_permanent_failure() -> None:
    async def transient(attempt: int) -> None:
        del attempt
        raise TransientPlatformError("temporary")

    with pytest.raises(RetryExhaustedError):
        await RetryStrategy(sleep=lambda _: _completed()).execute(
            transient, RetryPolicy(max_attempts=2, initial_delay_ms=0)
        )

    calls = 0

    async def permanent(attempt: int) -> None:
        nonlocal calls
        calls = attempt
        raise ValueError("permanent")

    with pytest.raises(ValueError):
        await RetryStrategy().execute(permanent, RetryPolicy(max_attempts=3))
    assert calls == 1

    cancellations = 0

    async def cancelled(attempt: int) -> None:
        nonlocal cancellations
        cancellations = attempt
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await RetryStrategy().execute(cancelled, RetryPolicy(max_attempts=3))
    assert cancellations == 1


async def _completed() -> None:
    return None


async def test_context_scope_restores_logging_context_and_emits_events() -> None:
    bus = InMemoryEventBus()
    manager = ExecutionContextManager(bus)
    context = ExecutionContext()
    request_token = request_id_var.set("outer-request")
    run_token = run_id_var.set("outer-run")
    try:
        run_id = context.capability_run_id or context.request_id
        async with manager.capability_scope(context, "example", run_id, 1):
            assert request_id_var.get() == str(context.request_id)
            assert run_id_var.get() == str(run_id)
        assert request_id_var.get() == "outer-request"
        assert run_id_var.get() == "outer-run"
    finally:
        request_id_var.reset(request_token)
        run_id_var.reset(run_token)
    assert [event.name for event in bus.events] == [
        "capability.started",
        "capability.completed",
    ]


def test_response_renderer_orders_text_components_and_deduplicates_sources() -> None:
    now = datetime.now(UTC)
    source = EvidenceSource(
        source_id="source-1",
        provider="test",
        title="Test",
        url="https://example.com",
        retrieved_at=now,
        source_type="test",
    )
    result = CapabilityResult(
        capability="example",
        status=RunStatus.PARTIAL,
        summary="Summary",
        sources=(source, source),
        warnings=(CapabilityWarning(code="PARTIAL", message="Some data is missing."),),
        components=(
            MetricGrid(
                id="metrics",
                status=ComponentStatus.PARTIAL,
                metrics=(MetricItem(label="State", value="partial"),),
            ),
        ),
        metadata=RunMetadata(started_at=now, completed_at=now),
    )
    rendered = ResponseRenderer().render(result)
    assert rendered.text == "Summary\nWarnings: Some data is missing."
    assert [item.source_id for item in rendered.sources] == ["source-1"]
    assert [component.id for component in rendered.components] == ["metrics"]


async def test_pipeline_executes_all_request_variants() -> None:
    container = build_container(market_test_settings())
    try:
        requests = (
            CommandExecutionRequest(command="/ping"),
            IntentExecutionRequest(text="system health"),
            CapabilityExecutionRequest(capability="system.ping"),
            WorkflowExecutionRequest(workflow="system.health"),
        )
        outcomes = [await container.pipeline.execute(request) for request in requests]
        assert [outcome.response.status for outcome in outcomes] == [
            RunStatus.COMPLETED,
            RunStatus.COMPLETED,
            RunStatus.COMPLETED,
            RunStatus.COMPLETED,
        ]
    finally:
        await container.close()


async def test_permission_check_and_optional_workflow_failure_are_user_safe() -> None:
    capability_registry = CapabilityRegistry()
    success = SuccessfulCapability()
    failure = FailingCapability()
    capability_registry.register(
        RegisteredCapability(
            descriptor=_descriptor("step.success", permissions=("execute",)),
            implementation=success,
            retry_policy=RetryPolicy(),
        )
    )
    capability_registry.register(
        RegisteredCapability(
            descriptor=_descriptor("step.failure"),
            implementation=failure,
            retry_policy=RetryPolicy(),
        )
    )
    runs = InMemoryRunRepository()
    contexts = ExecutionContextManager(InMemoryEventBus())
    capability_executor = CapabilityExecutor(capability_registry, contexts, RetryStrategy(), runs)
    with pytest.raises(PermissionDeniedError):
        await capability_executor.execute("step.success", ExecutionContext(), {})

    workflows = WorkflowRegistry(capability_registry)
    workflows.register(
        WorkflowDefinition(
            name="partial.workflow",
            version="1.0.0",
            description="partial",
            steps=(
                WorkflowStep(id="failure", capability="step.failure", required=False),
                WorkflowStep(id="success", capability="step.success", required=True),
            ),
        )
    )
    executor = WorkflowExecutor(workflows, WorkflowEngine(), capability_executor, contexts, runs)
    result = await executor.execute(
        "partial.workflow", ExecutionContext(permissions=("execute",)), {}
    )
    assert result.status == RunStatus.PARTIAL
    assert result.steps["failure"].warnings[0].message == (
        "The workflow step could not be completed."
    )
    assert "private failure detail" not in result.model_dump_json()


async def test_workflow_layers_and_dependency_payload_are_deterministic() -> None:
    capability_registry = CapabilityRegistry()
    success = SuccessfulCapability()
    for name in ("step.a", "step.b", "step.c"):
        capability_registry.register(
            RegisteredCapability(
                descriptor=_descriptor(name),
                implementation=success,
                retry_policy=RetryPolicy(),
            )
        )
    definition = WorkflowDefinition(
        name="layered.workflow",
        version="1.0.0",
        description="layered",
        steps=(
            WorkflowStep(id="a", capability="step.a"),
            WorkflowStep(id="b", capability="step.b"),
            WorkflowStep(id="c", capability="step.c", depends_on=("a",)),
        ),
    )
    layers = WorkflowEngine().compile(definition)
    assert [[step.id for step in layer] for layer in layers] == [["a", "b"], ["c"]]

    workflows = WorkflowRegistry(capability_registry)
    workflows.register(definition)
    runs = InMemoryRunRepository()
    contexts = ExecutionContextManager(InMemoryEventBus())
    capability_executor = CapabilityExecutor(capability_registry, contexts, RetryStrategy(), runs)
    result = await WorkflowExecutor(
        workflows, WorkflowEngine(), capability_executor, contexts, runs
    ).execute("layered.workflow", ExecutionContext(), {})
    assert list(result.steps) == ["a", "b", "c"]
    assert result.steps["a"].data["dependency_count"] == 0
    assert result.steps["b"].data["dependency_count"] == 0
    assert result.steps["c"].data["dependency_count"] == 1


def _descriptor(name: str, permissions: tuple[str, ...] = ()):
    from tradesentinel.platform.contracts import CapabilityDescriptor

    return CapabilityDescriptor(
        name=name,
        version="1.0.0",
        description=name,
        permissions=permissions,
    )


def test_command_parser_rejects_unknown_commands() -> None:
    with pytest.raises(CommandSyntaxError):
        CommandParser(CommandRegistry()).parse("/missing")


def test_workflow_binding_can_pass_a_complete_typed_result() -> None:
    binding = WorkflowInputBinding(source="steps.history.data")
    found, value = WorkflowExecutor._resolve_binding(
        {"steps": {"history": {"data": {"bars": [{"close": "100"}]}}}},
        binding.source,
    )
    assert found is True
    assert value == {"bars": [{"close": "100"}]}


def test_event_bus_rejects_duplicate_subscriptions() -> None:
    bus = InMemoryEventBus()

    async def handler(event) -> None:
        del event

    bus.subscribe("event", handler)
    with pytest.raises(EventBusError):
        bus.subscribe("event", handler)
