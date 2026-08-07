from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from tradesentinel.platform.commands import CommandParser
from tradesentinel.platform.config import Settings
from tradesentinel.platform.context import ExecutionContextManager
from tradesentinel.platform.dependencies import DependencyResolver
from tradesentinel.platform.events import EventBus, InMemoryEventBus, RedisStreamEventBus
from tradesentinel.platform.execution import CapabilityExecutor
from tradesentinel.platform.intents import ExactExampleIntentResolver
from tradesentinel.platform.modules import ModuleLoader
from tradesentinel.platform.persistence import (
    InMemoryRunRepository,
    RunRepository,
    SqlRunRepository,
    create_engine,
    create_session_factory,
)
from tradesentinel.platform.pipeline import ExecutionPipeline
from tradesentinel.platform.rate_limits import InMemoryRateLimiter, RateLimiter, RedisRateLimiter
from tradesentinel.platform.registries import (
    CapabilityRegistry,
    CommandRegistry,
    IntentRegistry,
    WorkflowRegistry,
)
from tradesentinel.platform.rendering import ResponseRenderer
from tradesentinel.platform.retry import RetryStrategy
from tradesentinel.platform.workflows import WorkflowEngine, WorkflowExecutor


@dataclass
class Container:
    settings: Settings
    engine: AsyncEngine
    redis: Redis
    events: EventBus
    runs: RunRepository
    rate_limiter: RateLimiter
    capabilities: CapabilityRegistry
    commands: CommandRegistry
    intents: IntentRegistry
    workflows: WorkflowRegistry
    loader: ModuleLoader
    executor: WorkflowExecutor
    pipeline: ExecutionPipeline

    async def close(self) -> None:
        await self.engine.dispose()
        await self.redis.aclose()


def build_container(settings: Settings) -> Container:
    engine = create_engine(settings.database_url.get_secret_value())
    redis = Redis.from_url(settings.redis_url.get_secret_value(), decode_responses=False)
    events: EventBus = (
        RedisStreamEventBus(redis) if settings.event_backend == "redis" else InMemoryEventBus()
    )
    runs: RunRepository = (
        SqlRunRepository(create_session_factory(engine))
        if settings.persistence_backend == "postgres"
        else InMemoryRunRepository()
    )
    rate_limiter: RateLimiter = (
        RedisRateLimiter(redis) if settings.event_backend == "redis" else InMemoryRateLimiter()
    )
    capabilities = CapabilityRegistry()
    commands = CommandRegistry()
    intents = IntentRegistry()
    workflows = WorkflowRegistry(capabilities)
    dependency_resolver = DependencyResolver()
    loader = ModuleLoader(capabilities, commands, intents, workflows, events, dependency_resolver)
    loader.load(settings.module_roots)
    contexts = ExecutionContextManager(events)
    retry_strategy = RetryStrategy()
    capability_executor = CapabilityExecutor(capabilities, contexts, retry_strategy, runs)
    executor = WorkflowExecutor(workflows, WorkflowEngine(), capability_executor, contexts, runs)
    pipeline = ExecutionPipeline(
        CommandParser(commands),
        intents,
        ExactExampleIntentResolver(),
        capability_executor,
        executor,
        contexts,
        ResponseRenderer(),
    )
    loader.bind_event_consumers(pipeline)
    return Container(
        settings=settings,
        engine=engine,
        redis=redis,
        events=events,
        runs=runs,
        rate_limiter=rate_limiter,
        capabilities=capabilities,
        commands=commands,
        intents=intents,
        workflows=workflows,
        loader=loader,
        executor=executor,
        pipeline=pipeline,
    )
