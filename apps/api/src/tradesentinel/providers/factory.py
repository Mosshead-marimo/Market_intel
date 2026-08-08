from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from time import perf_counter
from typing import TypeVar, cast

import structlog
from pydantic import TypeAdapter, ValidationError

from tradesentinel.platform.dependencies import DependencyResolver
from tradesentinel.platform.rate_limits import RateLimiter
from tradesentinel.providers.contracts import (
    CompanyProfile,
    CompanyProfileRequest,
    CorporateActions,
    CorporateActionsRequest,
    EconomicObservationSeries,
    EconomicObservationsRequest,
    EconomicSeries,
    EconomicSeriesSearchRequest,
    FinancialStatement,
    FinancialStatementsRequest,
    FundamentalFact,
    FundamentalFactsRequest,
    InstrumentRecord,
    InstrumentSearchRequest,
    MarketQuote,
    NewsArticle,
    NewsDocument,
    NewsDocumentRequest,
    NewsSearchRequest,
    PriceHistory,
    PriceHistoryRequest,
    ProviderContext,
    ProviderDescriptor,
    ProviderKind,
    QuoteRequest,
    SentimentObservation,
    SentimentRequest,
)
from tradesentinel.providers.errors import (
    ProviderChainExhaustedError,
    ProviderError,
    ProviderInvocationError,
    ProviderNotConfiguredError,
    ProviderNotFoundError,
    ProviderOutputError,
    ProviderRateLimitedError,
    ProviderRegistryError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from tradesentinel.providers.interfaces import (
    EconomicDataProvider,
    FundamentalsProvider,
    MarketDataProvider,
    NewsProvider,
    SentimentProvider,
)
from tradesentinel.providers.registry import INTERFACE_BY_KIND, ProviderRegistry

OutputT = TypeVar("OutputT")
ProviderOperation = Callable[[ProviderContext, object], Awaitable[object]]


class _ProviderChain:
    def __init__(
        self,
        kind: ProviderKind,
        providers: tuple[tuple[ProviderDescriptor, object], ...],
        rate_limiter: RateLimiter,
    ) -> None:
        self._kind = kind
        self._providers = providers
        self._rate_limiter = rate_limiter

    async def _invoke(
        self,
        method: str,
        context: ProviderContext,
        request: object,
        output: TypeAdapter[OutputT],
    ) -> OutputT:
        if not self._providers:
            raise ProviderNotConfiguredError(self._kind)
        requested_provider = getattr(request, "provider", None)
        providers = self._providers
        if requested_provider is not None:
            providers = tuple(
                item for item in self._providers if item[0].name == requested_provider
            )
            if not providers:
                raise ProviderNotFoundError(self._kind, requested_provider)
        attempted: list[str] = []
        for descriptor, adapter in providers:
            attempted.append(descriptor.name)
            started = perf_counter()
            try:
                allowed, retry_after = await self._rate_limiter.allow(
                    f"provider:{descriptor.kind.value}:{descriptor.name}",
                    descriptor.rate_limit.requests,
                    descriptor.rate_limit.window_seconds,
                )
                if not allowed:
                    raise ProviderRateLimitedError(descriptor.name, retry_after)
                operation = cast(ProviderOperation, getattr(adapter, method))
                async with asyncio.timeout(descriptor.timeout_ms / 1_000):
                    raw = await operation(context, request)
                try:
                    result = output.validate_python(raw)
                except ValidationError as exc:
                    raise ProviderOutputError(descriptor.name) from exc
            except asyncio.CancelledError:
                raise
            except TimeoutError:
                error: ProviderError = ProviderTimeoutError(descriptor.name)
            except ConnectionError:
                error = ProviderUnavailableError(descriptor.name)
            except ProviderError as exc:
                error = exc
            except Exception as exc:
                structlog.get_logger().exception(
                    "provider_call_failed",
                    provider=descriptor.name,
                    provider_kind=descriptor.kind.value,
                    operation=method,
                    request_id=str(context.request_id),
                    run_id=str(context.capability_run_id) if context.capability_run_id else None,
                    error_type=type(exc).__name__,
                )
                raise ProviderInvocationError(descriptor.name) from exc
            else:
                structlog.get_logger().info(
                    "provider_call_completed",
                    provider=descriptor.name,
                    provider_kind=descriptor.kind.value,
                    operation=method,
                    duration_ms=round((perf_counter() - started) * 1_000, 3),
                    request_id=str(context.request_id),
                    run_id=str(context.capability_run_id) if context.capability_run_id else None,
                )
                return result
            structlog.get_logger().warning(
                "provider_call_unavailable",
                provider=descriptor.name,
                provider_kind=descriptor.kind.value,
                operation=method,
                duration_ms=round((perf_counter() - started) * 1_000, 3),
                request_id=str(context.request_id),
                run_id=str(context.capability_run_id) if context.capability_run_id else None,
                error_code=error.code,
            )
            if not error.retryable:
                raise error
        raise ProviderChainExhaustedError(self._kind, tuple(attempted))


class _MarketDataChain(_ProviderChain, MarketDataProvider):
    async def search_instruments(
        self, context: ProviderContext, request: InstrumentSearchRequest
    ) -> tuple[InstrumentRecord, ...]:
        return await self._invoke(
            "search_instruments", context, request, TypeAdapter(tuple[InstrumentRecord, ...])
        )

    async def get_quote(self, context: ProviderContext, request: QuoteRequest) -> MarketQuote:
        return await self._invoke("get_quote", context, request, TypeAdapter(MarketQuote))

    async def get_history(
        self, context: ProviderContext, request: PriceHistoryRequest
    ) -> PriceHistory:
        return await self._invoke("get_history", context, request, TypeAdapter(PriceHistory))

    async def get_corporate_actions(
        self, context: ProviderContext, request: CorporateActionsRequest
    ) -> CorporateActions:
        return await self._invoke(
            "get_corporate_actions", context, request, TypeAdapter(CorporateActions)
        )


class _NewsChain(_ProviderChain, NewsProvider):
    async def search(
        self, context: ProviderContext, request: NewsSearchRequest
    ) -> tuple[NewsArticle, ...]:
        return await self._invoke("search", context, request, TypeAdapter(tuple[NewsArticle, ...]))

    async def get_document(
        self, context: ProviderContext, request: NewsDocumentRequest
    ) -> NewsDocument:
        return await self._invoke("get_document", context, request, TypeAdapter(NewsDocument))


class _SentimentChain(_ProviderChain, SentimentProvider):
    async def collect(
        self, context: ProviderContext, request: SentimentRequest
    ) -> tuple[SentimentObservation, ...]:
        return await self._invoke(
            "collect", context, request, TypeAdapter(tuple[SentimentObservation, ...])
        )


class _EconomicDataChain(_ProviderChain, EconomicDataProvider):
    async def search_series(
        self, context: ProviderContext, request: EconomicSeriesSearchRequest
    ) -> tuple[EconomicSeries, ...]:
        return await self._invoke(
            "search_series", context, request, TypeAdapter(tuple[EconomicSeries, ...])
        )

    async def get_observations(
        self, context: ProviderContext, request: EconomicObservationsRequest
    ) -> EconomicObservationSeries:
        return await self._invoke(
            "get_observations", context, request, TypeAdapter(EconomicObservationSeries)
        )


class _FundamentalsChain(_ProviderChain, FundamentalsProvider):
    async def get_company_profile(
        self, context: ProviderContext, request: CompanyProfileRequest
    ) -> CompanyProfile:
        return await self._invoke(
            "get_company_profile", context, request, TypeAdapter(CompanyProfile)
        )

    async def get_financial_statements(
        self, context: ProviderContext, request: FinancialStatementsRequest
    ) -> tuple[FinancialStatement, ...]:
        return await self._invoke(
            "get_financial_statements",
            context,
            request,
            TypeAdapter(tuple[FinancialStatement, ...]),
        )

    async def get_fundamental_facts(
        self, context: ProviderContext, request: FundamentalFactsRequest
    ) -> tuple[FundamentalFact, ...]:
        return await self._invoke(
            "get_fundamental_facts",
            context,
            request,
            TypeAdapter(tuple[FundamentalFact, ...]),
        )


CHAIN_BY_KIND: dict[ProviderKind, type[_ProviderChain]] = {
    ProviderKind.MARKET_DATA: _MarketDataChain,
    ProviderKind.NEWS: _NewsChain,
    ProviderKind.SENTIMENT: _SentimentChain,
    ProviderKind.ECONOMIC_DATA: _EconomicDataChain,
    ProviderKind.FUNDAMENTALS: _FundamentalsChain,
}


class ProviderFactory:
    def __init__(
        self,
        registry: ProviderRegistry,
        resolver: DependencyResolver,
        rate_limiter: RateLimiter,
    ) -> None:
        self.registry = registry
        self.resolver = resolver
        self.rate_limiter = rate_limiter
        self._selected: dict[ProviderKind, _ProviderChain] = {}

    def configure(self, selections: Mapping[ProviderKind, tuple[str, ...]]) -> None:
        selected: dict[ProviderKind, _ProviderChain] = {}
        for kind in ProviderKind:
            names = selections.get(kind, ())
            if not names:
                unavailable = CHAIN_BY_KIND[kind](kind, (), self.rate_limiter)
                self.resolver.register_instance(INTERFACE_BY_KIND[kind], unavailable)
                continue
            if len(names) != len(set(names)):
                raise ProviderRegistryError(
                    "A configured provider chain contains duplicate names.",
                    {"kind": kind.value, "providers": list(names)},
                )
            providers = tuple(
                (
                    registration.descriptor,
                    self.resolver.resolve(registration.adapter_class),
                )
                for name in names
                for registration in (self.registry.get(kind, name),)
            )
            chain = CHAIN_BY_KIND[kind](kind, providers, self.rate_limiter)
            selected[kind] = chain
            self.resolver.register_instance(INTERFACE_BY_KIND[kind], chain)
        self._selected = selected

    def get(self, kind: ProviderKind) -> object:
        try:
            return self._selected[kind]
        except KeyError as exc:
            raise ProviderNotConfiguredError(kind) from exc

    def selected(self) -> tuple[ProviderKind, ...]:
        return tuple(sorted(self._selected, key=lambda kind: kind.value))
