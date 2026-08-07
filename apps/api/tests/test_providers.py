from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
import structlog.testing
from pydantic import BaseModel, ValidationError
from tradesentinel.platform.capabilities import Capability
from tradesentinel.platform.config import Settings
from tradesentinel.platform.contracts import (
    CapabilityResult,
    ExecutionContext,
    RunMetadata,
    RunStatus,
)
from tradesentinel.platform.dependencies import DependencyResolver
from tradesentinel.platform.errors import DependencyResolutionError
from tradesentinel.platform.events import InMemoryEventBus
from tradesentinel.platform.modules import ModuleLoader
from tradesentinel.platform.rate_limits import InMemoryRateLimiter, RateLimiter
from tradesentinel.platform.registries import (
    CapabilityRegistry,
    CommandRegistry,
    IntentRegistry,
    WorkflowRegistry,
)
from tradesentinel.providers.contracts import (
    CorporateAction,
    CorporateActionsRequest,
    FreshnessStatus,
    InstrumentRecord,
    InstrumentReference,
    InstrumentSearchRequest,
    LicenseClassification,
    MarketQuote,
    PriceHistory,
    PriceHistoryRequest,
    ProviderContext,
    ProviderDescriptor,
    ProviderKind,
    ProviderMetadata,
    ProviderRateLimit,
    QuoteRequest,
)
from tradesentinel.providers.discovery import ProviderBootstrap
from tradesentinel.providers.errors import (
    ProviderAuthenticationError,
    ProviderChainExhaustedError,
    ProviderOutputError,
    ProviderRegistryError,
    ProviderUnavailableError,
)
from tradesentinel.providers.factory import ProviderFactory
from tradesentinel.providers.interfaces import MarketDataProvider
from tradesentinel.providers.registry import (
    INTERFACE_BY_KIND,
    ProviderRegistration,
    ProviderRegistry,
)


def _metadata(provider: str) -> ProviderMetadata:
    return ProviderMetadata(
        provider=provider,
        source_id=f"{provider}:quote",
        observed_at=datetime.now(UTC),
        retrieved_at=datetime.now(UTC),
        timezone="UTC",
        license=LicenseClassification.INTERNAL,
        freshness=FreshnessStatus.FRESH,
    )


def _quote(provider: str) -> MarketQuote:
    return MarketQuote(
        instrument=InstrumentReference(symbol="TEST", exchange="XTEST"),
        price=Decimal("10.25"),
        currency="USD",
        as_of=datetime.now(UTC),
        metadata=_metadata(provider),
    )


class MarketAdapter(MarketDataProvider):
    calls = 0

    async def search_instruments(
        self, context: ProviderContext, request: InstrumentSearchRequest
    ) -> tuple[InstrumentRecord, ...]:
        del context, request
        return ()

    async def get_quote(self, context: ProviderContext, request: QuoteRequest) -> MarketQuote:
        del context, request
        type(self).calls += 1
        return _quote("market")

    async def get_history(
        self, context: ProviderContext, request: PriceHistoryRequest
    ) -> PriceHistory:
        del context, request
        raise NotImplementedError

    async def get_corporate_actions(
        self, context: ProviderContext, request: CorporateActionsRequest
    ) -> tuple[CorporateAction, ...]:
        del context, request
        return ()


class UnavailableMarket(MarketAdapter):
    async def get_quote(self, context: ProviderContext, request: QuoteRequest) -> MarketQuote:
        del context, request
        raise ProviderUnavailableError("unavailable")


class SecondaryMarket(MarketAdapter):
    async def get_quote(self, context: ProviderContext, request: QuoteRequest) -> MarketQuote:
        del context, request
        type(self).calls += 1
        return _quote("secondary")


class PermanentMarket(MarketAdapter):
    async def get_quote(self, context: ProviderContext, request: QuoteRequest) -> MarketQuote:
        del context, request
        raise ProviderAuthenticationError("permanent")


class InvalidMarket(MarketAdapter):
    async def get_quote(self, context: ProviderContext, request: QuoteRequest) -> MarketQuote:
        del context, request
        return cast(MarketQuote, {"unexpected": True})


class SlowMarket(MarketAdapter):
    async def get_quote(self, context: ProviderContext, request: QuoteRequest) -> MarketQuote:
        del context, request
        await asyncio.sleep(0.05)
        return _quote("slow")


class ProviderInput(BaseModel):
    pass


class InjectedCapability(Capability[ProviderInput]):
    input_model = ProviderInput

    def __init__(self, provider: MarketDataProvider) -> None:
        self.provider = provider

    async def execute(self, context: ExecutionContext, payload: ProviderInput) -> CapabilityResult:
        del context, payload
        now = datetime.now(UTC)
        return CapabilityResult(
            capability="",
            status=RunStatus.COMPLETED,
            metadata=RunMetadata(started_at=now, completed_at=now),
        )


class DenyFirstRateLimiter(RateLimiter):
    async def allow(self, key: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
        del limit, window_seconds
        return ("unavailable" not in key, 2)


def _registration(
    name: str,
    adapter: type[MarketDataProvider],
    *,
    timeout_ms: int = 1_000,
) -> ProviderRegistration:
    return ProviderRegistration(
        ProviderDescriptor(
            kind=ProviderKind.MARKET_DATA,
            name=name,
            class_path=f"test_providers:{adapter.__name__}",
            timeout_ms=timeout_ms,
            rate_limit=ProviderRateLimit(requests=10, window_seconds=60),
        ),
        adapter,
    )


def _factory(
    registrations: tuple[ProviderRegistration, ...],
    names: tuple[str, ...],
    rate_limiter: RateLimiter | None = None,
) -> ProviderFactory:
    registry = ProviderRegistry()
    for registration in registrations:
        registry.register(registration)
    factory = ProviderFactory(registry, DependencyResolver(), rate_limiter or InMemoryRateLimiter())
    factory.configure({ProviderKind.MARKET_DATA: names})
    return factory


def _context() -> ProviderContext:
    return ProviderContext(request_id=uuid4(), correlation_id=uuid4())


def _request() -> QuoteRequest:
    return QuoteRequest(instrument=InstrumentReference(symbol="TEST"))


def test_contracts_are_strict_and_all_provider_kinds_have_interfaces() -> None:
    assert set(INTERFACE_BY_KIND) == set(ProviderKind)
    assert _quote("test").price == Decimal("10.25")
    with pytest.raises(ValidationError):
        ProviderMetadata(
            provider="test",
            source_id="source",
            retrieved_at=datetime.now(UTC),
            secret="not allowed",
        )


def test_registry_rejects_duplicates_and_incompatible_classes() -> None:
    registry = ProviderRegistry()
    registration = _registration("primary", MarketAdapter)
    registry.register(registration)
    with pytest.raises(ProviderRegistryError):
        registry.register(registration)
    with pytest.raises(ProviderRegistryError, match="declared interface"):
        registry.register(
            ProviderRegistration(
                ProviderDescriptor(
                    kind=ProviderKind.MARKET_DATA,
                    name="wrong",
                    class_path="builtins:object",
                ),
                object,
            )
        )


def test_registry_listing_is_deterministic() -> None:
    registry = ProviderRegistry()
    registry.register(_registration("zeta", MarketAdapter))
    registry.register(_registration("alpha", SecondaryMarket))
    assert [item.descriptor.name for item in registry.list()] == ["alpha", "zeta"]


def test_settings_and_factory_switch_providers_without_code_changes() -> None:
    settings = Settings(market_data_providers=("secondary",))
    factory = _factory(
        (
            _registration("primary", MarketAdapter),
            _registration("secondary", SecondaryMarket),
        ),
        settings.market_data_providers,
    )
    assert factory.selected() == (ProviderKind.MARKET_DATA,)
    with pytest.raises(ProviderRegistryError, match="duplicate"):
        _factory(
            (_registration("primary", MarketAdapter),),
            ("primary", "primary"),
        )


async def test_factory_falls_back_for_retryable_availability_failure() -> None:
    factory = _factory(
        (
            _registration("unavailable", UnavailableMarket),
            _registration("secondary", SecondaryMarket),
        ),
        ("unavailable", "secondary"),
    )
    provider = cast(MarketDataProvider, factory.get(ProviderKind.MARKET_DATA))
    assert (await provider.get_quote(_context(), _request())).metadata.provider == "secondary"


async def test_provider_logs_contain_context_but_not_request_payloads() -> None:
    factory = _factory((_registration("secondary", SecondaryMarket),), ("secondary",))
    provider = cast(MarketDataProvider, factory.get(ProviderKind.MARKET_DATA))
    context = _context()
    with structlog.testing.capture_logs() as logs:
        await provider.get_quote(context, _request())
    completed = logs[-1]
    assert completed["provider"] == "secondary"
    assert completed["request_id"] == str(context.request_id)
    assert "request" not in completed


async def test_factory_falls_back_after_timeout_and_local_rate_limit() -> None:
    timeout_factory = _factory(
        (
            _registration("slow", SlowMarket, timeout_ms=1),
            _registration("secondary", SecondaryMarket),
        ),
        ("slow", "secondary"),
    )
    timeout_provider = cast(MarketDataProvider, timeout_factory.get(ProviderKind.MARKET_DATA))
    assert (
        await timeout_provider.get_quote(_context(), _request())
    ).metadata.provider == "secondary"

    limited_factory = _factory(
        (
            _registration("unavailable", MarketAdapter),
            _registration("secondary", SecondaryMarket),
        ),
        ("unavailable", "secondary"),
        DenyFirstRateLimiter(),
    )
    limited_provider = cast(MarketDataProvider, limited_factory.get(ProviderKind.MARKET_DATA))
    assert (
        await limited_provider.get_quote(_context(), _request())
    ).metadata.provider == "secondary"


async def test_factory_stops_on_permanent_and_invalid_output_failures() -> None:
    permanent = _factory(
        (
            _registration("permanent", PermanentMarket),
            _registration("secondary", SecondaryMarket),
        ),
        ("permanent", "secondary"),
    )
    with pytest.raises(ProviderAuthenticationError):
        await cast(MarketDataProvider, permanent.get(ProviderKind.MARKET_DATA)).get_quote(
            _context(), _request()
        )

    invalid = _factory(
        (_registration("invalid", InvalidMarket),),
        ("invalid",),
    )
    with pytest.raises(ProviderOutputError):
        await cast(MarketDataProvider, invalid.get(ProviderKind.MARKET_DATA)).get_quote(
            _context(), _request()
        )


async def test_factory_exhaustion_and_cancellation_are_safe() -> None:
    exhausted = _factory((_registration("unavailable", UnavailableMarket),), ("unavailable",))
    with pytest.raises(ProviderChainExhaustedError) as caught:
        await cast(MarketDataProvider, exhausted.get(ProviderKind.MARKET_DATA)).get_quote(
            _context(), _request()
        )
    assert caught.value.details == {
        "kind": "market_data",
        "providers": ["unavailable"],
    }

    class CancelledMarket(MarketAdapter):
        async def get_quote(self, context: ProviderContext, request: QuoteRequest) -> MarketQuote:
            del context, request
            raise asyncio.CancelledError

    cancelled = _factory((_registration("cancelled", CancelledMarket),), ("cancelled",))
    with pytest.raises(asyncio.CancelledError):
        await cast(MarketDataProvider, cancelled.get(ProviderKind.MARKET_DATA)).get_quote(
            _context(), _request()
        )


def _loader(resolver: DependencyResolver) -> tuple[ModuleLoader, CapabilityRegistry]:
    capabilities = CapabilityRegistry()
    events = InMemoryEventBus()
    loader = ModuleLoader(
        capabilities,
        CommandRegistry(),
        IntentRegistry(),
        WorkflowRegistry(capabilities),
        events,
        resolver,
    )
    return loader, capabilities


def _write_manifest(path: Path, capability_path: str) -> None:
    path.mkdir()
    (path / "manifest.yaml").write_text(
        f"""name: test.provider_module
version: 1.0.0
description: Provider bootstrap test
providers:
  - kind: market_data
    name: secondary
    class_path: test_providers:SecondaryMarket
    timeout_ms: 500
    rate_limit:
      requests: 10
      window_seconds: 60
capabilities:
  - name: test.provider_capability
    class_path: {capability_path}
    description: Requires a selected provider
""",
        encoding="utf-8",
    )


def test_manifest_provider_becomes_constructor_dependency_without_core_registration(
    tmp_path: Path,
) -> None:
    _write_manifest(tmp_path / "module", "test_providers:InjectedCapability")
    resolver = DependencyResolver()
    loader, capabilities = _loader(resolver)
    registry = ProviderRegistry()
    factory = ProviderBootstrap(
        registry,
        resolver,
        InMemoryRateLimiter(),
        {ProviderKind.MARKET_DATA: ("secondary",)},
    ).load(loader, (tmp_path,))
    implementation = capabilities.get("test.provider_capability").implementation
    assert isinstance(cast(InjectedCapability, implementation).provider, MarketDataProvider)
    assert factory.selected() == (ProviderKind.MARKET_DATA,)
    assert registry.get(ProviderKind.MARKET_DATA, "secondary").adapter_class is SecondaryMarket


def test_missing_selection_fails_only_when_a_capability_requires_the_port(
    tmp_path: Path,
) -> None:
    _write_manifest(tmp_path / "module", "test_providers:InjectedCapability")
    resolver = DependencyResolver()
    loader, _ = _loader(resolver)
    with pytest.raises(DependencyResolutionError):
        ProviderBootstrap(ProviderRegistry(), resolver, InMemoryRateLimiter(), {}).load(
            loader, (tmp_path,)
        )


def test_provider_and_dependency_registration_roll_back_atomically(tmp_path: Path) -> None:
    _write_manifest(tmp_path / "module", "builtins:object")
    resolver = DependencyResolver()
    loader, _ = _loader(resolver)
    registry = ProviderRegistry()
    with pytest.raises(Exception, match="does not implement Capability"):
        ProviderBootstrap(
            registry,
            resolver,
            InMemoryRateLimiter(),
            {ProviderKind.MARKET_DATA: ("secondary",)},
        ).load(loader, (tmp_path,))
    assert registry.list() == ()
    with pytest.raises(DependencyResolutionError):
        resolver.resolve(MarketDataProvider)
