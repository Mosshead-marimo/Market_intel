from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from tradesentinel.platform.config import Settings
from tradesentinel.platform.events import EventBus, InMemoryEventBus, RedisStreamEventBus
from tradesentinel.platform.modules import ModuleLoader
from tradesentinel.platform.persistence import (
    InMemoryRunRepository,
    RunRepository,
    SqlRunRepository,
    create_engine,
    create_session_factory,
)
from tradesentinel.platform.rate_limits import InMemoryRateLimiter, RateLimiter, RedisRateLimiter
from tradesentinel.platform.registries import CapabilityRegistry, CommandRegistry, WorkflowRegistry
from tradesentinel.platform.workflows import WorkflowExecutor


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
    workflows: WorkflowRegistry
    loader: ModuleLoader
    executor: WorkflowExecutor

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
    workflows = WorkflowRegistry(capabilities)
    loader = ModuleLoader(capabilities, commands, workflows, events)
    loader.load(settings.module_roots)
    executor = WorkflowExecutor(workflows, capabilities, events, runs)
    return Container(
        settings=settings,
        engine=engine,
        redis=redis,
        events=events,
        runs=runs,
        rate_limiter=rate_limiter,
        capabilities=capabilities,
        commands=commands,
        workflows=workflows,
        loader=loader,
        executor=executor,
    )
