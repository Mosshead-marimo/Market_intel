"""Application composition root."""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine

from tradesentinel.platform.cache import CacheStore, InMemoryCacheStore, RedisCacheStore
from tradesentinel.platform.chat import BackgroundTaskRunner, ChatOrchestrator
from tradesentinel.platform.chat_persistence import (
    ChatRepository,
    InMemoryChatRepository,
    SqlChatRepository,
)
from tradesentinel.platform.chat_streams import (
    ChatStreamStore,
    InMemoryChatStreamStore,
    RedisChatStreamStore,
)
from tradesentinel.platform.commands import CommandParser
from tradesentinel.platform.config import Settings
from tradesentinel.platform.context import ExecutionContextManager
from tradesentinel.platform.dependencies import DependencyResolver
from tradesentinel.platform.events import EventBus, InMemoryEventBus, RedisStreamEventBus
from tradesentinel.platform.execution import CapabilityExecutor
from tradesentinel.platform.gateway import ExecutionGateway
from tradesentinel.platform.intents import ExactExampleIntentResolver
from tradesentinel.platform.modules import ModuleLoader
from tradesentinel.platform.object_store import FileObjectStore, InMemoryObjectStore, ObjectStore
from tradesentinel.platform.persistence import (
    InMemoryRunRepository,
    PersistenceResources,
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
from tradesentinel.providers.contracts import ProviderKind
from tradesentinel.providers.discovery import ProviderBootstrap
from tradesentinel.providers.factory import ProviderFactory
from tradesentinel.providers.registry import ProviderRegistry


@dataclass
class Container:
    settings: Settings
    engine: AsyncEngine
    redis: Redis
    cache: CacheStore
    object_store: ObjectStore
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
    chat_repository: ChatRepository
    chat_streams: ChatStreamStore
    chat: ChatOrchestrator
    tasks: BackgroundTaskRunner
    providers: ProviderRegistry
    provider_factory: ProviderFactory
    gateway: ExecutionGateway

    async def close(self) -> None:
        await self.tasks.close()
        await self.engine.dispose()
        await self.redis.aclose()


def build_container(settings: Settings) -> Container:
    engine = create_engine(settings.database_url.get_secret_value())
    redis = Redis.from_url(settings.redis_url.get_secret_value(), decode_responses=False)
    events: EventBus = (
        RedisStreamEventBus(redis) if settings.event_backend == "redis" else InMemoryEventBus()
    )
    session_factory = create_session_factory(engine)
    runs: RunRepository = (
        SqlRunRepository(session_factory)
        if settings.persistence_backend == "postgres"
        else InMemoryRunRepository()
    )
    rate_limiter: RateLimiter = (
        RedisRateLimiter(redis) if settings.event_backend == "redis" else InMemoryRateLimiter()
    )
    cache: CacheStore = (
        RedisCacheStore(redis) if settings.cache_backend == "redis" else InMemoryCacheStore()
    )
    object_store: ObjectStore = (
        FileObjectStore(settings.object_store_root)
        if settings.object_store_backend == "filesystem"
        else InMemoryObjectStore()
    )
    capabilities = CapabilityRegistry()
    commands = CommandRegistry()
    intents = IntentRegistry()
    workflows = WorkflowRegistry(capabilities)
    gateway = ExecutionGateway(commands)
    dependency_resolver = DependencyResolver()
    dependency_resolver.register_instance(Settings, settings)
    dependency_resolver.register_instance(EventBus, events)
    dependency_resolver.register_instance(RateLimiter, rate_limiter)
    dependency_resolver.register_instance(CacheStore, cache)
    dependency_resolver.register_instance(ObjectStore, object_store)
    dependency_resolver.register_instance(ExecutionGateway, gateway)
    dependency_resolver.register_instance(
        PersistenceResources,
        PersistenceResources(backend=settings.persistence_backend, sessions=session_factory),
    )
    loader = ModuleLoader(capabilities, commands, intents, workflows, events, dependency_resolver)
    providers = ProviderRegistry()
    provider_factory = ProviderBootstrap(
        providers,
        dependency_resolver,
        rate_limiter,
        {
            ProviderKind.MARKET_DATA: settings.market_data_providers,
            ProviderKind.NEWS: settings.news_providers,
            ProviderKind.SENTIMENT: settings.sentiment_providers,
            ProviderKind.ECONOMIC_DATA: settings.economic_data_providers,
            ProviderKind.FUNDAMENTALS: settings.fundamentals_providers,
            ProviderKind.LANGUAGE_MODEL: settings.llm_providers,
        },
    ).load(loader, settings.module_roots)
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
    gateway.bind(pipeline)
    loader.bind_event_consumers(pipeline)
    chat_repository: ChatRepository = (
        SqlChatRepository(session_factory)
        if settings.persistence_backend == "postgres"
        else InMemoryChatRepository()
    )
    chat_streams: ChatStreamStore = (
        RedisChatStreamStore(redis, retention_seconds=settings.chat_event_retention_seconds)
        if settings.event_backend == "redis"
        else InMemoryChatStreamStore()
    )
    chat = ChatOrchestrator(
        chat_repository,
        chat_streams,
        events,
        pipeline,
        context_message_limit=settings.chat_context_message_limit,
    )
    events.subscribe("chat.turn.requested", chat.handle_requested)
    events.subscribe("assistant.progress", chat.handle_assistant_progress)
    tasks = BackgroundTaskRunner()
    return Container(
        settings=settings,
        engine=engine,
        redis=redis,
        cache=cache,
        object_store=object_store,
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
        chat_repository=chat_repository,
        chat_streams=chat_streams,
        chat=chat,
        tasks=tasks,
        providers=providers,
        provider_factory=provider_factory,
        gateway=gateway,
    )
