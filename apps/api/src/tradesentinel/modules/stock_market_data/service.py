from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal, localcontext
from itertools import pairwise
from typing import TypeVar

import structlog
from pydantic import BaseModel, TypeAdapter, ValidationError

from tradesentinel.domain.instruments import InstrumentRef
from tradesentinel.domain.market_data import (
    AdjustedPriceBar,
    BenchmarkComparisonInput,
    BenchmarkComparisonOutput,
    CacheDisposition,
    CacheMetadata,
    FiveYearPerformanceInput,
    FiveYearPerformanceOutput,
    MarketInterval,
    PerformanceMetrics,
    RebasedPoint,
    StockComparisonInput,
    StockComparisonItem,
    StockComparisonOutput,
    StockCorporateAction,
    StockCorporateActionsInput,
    StockCorporateActionsOutput,
    StockHistoryInput,
    StockHistoryOutput,
    StockPerformanceInput,
    StockPerformanceOutput,
    StockQuoteInput,
    StockQuoteOutput,
)
from tradesentinel.modules.stock_market_data.errors import (
    CurrencyMismatchError,
    InsufficientHistoryError,
    InsufficientOverlapError,
    MarketDataIntegrityError,
)
from tradesentinel.platform.cache import CacheStore
from tradesentinel.platform.config import Settings
from tradesentinel.platform.contracts import ExecutionContext
from tradesentinel.providers.contracts import (
    CorporateActions,
    CorporateActionsRequest,
    InstrumentReference,
    MarketQuote,
    PriceHistory,
    PriceHistoryRequest,
    ProviderContext,
    QuoteRequest,
)
from tradesentinel.providers.interfaces import MarketDataProvider

OutputT = TypeVar("OutputT")


class StockMarketDataService:
    def __init__(
        self,
        provider: MarketDataProvider,
        cache: CacheStore,
        settings: Settings,
    ) -> None:
        self._provider = provider
        self._cache = cache
        self._settings = settings
        chain = ",".join(settings.market_data_providers)
        self._chain_fingerprint = hashlib.sha256(chain.encode()).hexdigest()[:16]

    async def quote(self, context: ExecutionContext, request: StockQuoteInput) -> StockQuoteOutput:
        provider_request = QuoteRequest(instrument=self._reference(request.instrument))
        quote, cache = await self._cached(
            "quote",
            provider_request,
            TypeAdapter(MarketQuote),
            self._settings.stock_quote_cache_ttl_seconds,
            lambda: self._provider.get_quote(self._context(context), provider_request),
        )
        self._validate_reference(request.instrument, quote.instrument)
        self._validate_currency(request.instrument, quote.currency)
        change = None
        change_percent = None
        if quote.previous_close is not None:
            change = quote.price - quote.previous_close
            if quote.previous_close != 0:
                change_percent = change / quote.previous_close
        return StockQuoteOutput(
            instrument=request.instrument,
            price=quote.price,
            currency=quote.currency,
            as_of=quote.as_of,
            previous_close=quote.previous_close,
            change=change,
            change_percent=change_percent,
            open=quote.open,
            high=quote.high,
            low=quote.low,
            volume=quote.volume,
            market_status=quote.market_status,
            provider=quote.metadata,
            cache=cache,
        )

    async def history(
        self, context: ExecutionContext, request: StockHistoryInput
    ) -> StockHistoryOutput:
        provider_request = PriceHistoryRequest(
            instrument=self._reference(request.instrument),
            start=request.start,
            end=request.end,
            interval=request.interval.value,
        )
        history, cache = await self._cached(
            "history",
            provider_request,
            TypeAdapter(PriceHistory),
            self._settings.stock_history_cache_ttl_seconds,
            lambda: self._provider.get_history(self._context(context), provider_request),
        )
        self._validate_reference(request.instrument, history.instrument)
        self._validate_currency(request.instrument, history.currency)
        if history.interval != request.interval.value:
            raise MarketDataIntegrityError("provider interval does not match the request")
        if any(
            bar.timestamp < request.start or bar.timestamp > request.end for bar in history.bars
        ):
            raise MarketDataIntegrityError("provider history contains bars outside the request")
        return StockHistoryOutput(
            instrument=request.instrument,
            interval=request.interval,
            currency=history.currency,
            bars=tuple(AdjustedPriceBar(**bar.model_dump()) for bar in history.bars),
            provider=history.metadata,
            cache=cache,
        )

    async def performance(
        self, context: ExecutionContext, request: StockPerformanceInput
    ) -> StockPerformanceOutput:
        history = await self.history(context, StockHistoryInput(**request.model_dump()))
        return self._performance(history)

    async def compare(
        self, context: ExecutionContext, request: StockComparisonInput
    ) -> StockComparisonOutput:
        histories = await asyncio.gather(
            *(
                self.history(
                    context,
                    StockHistoryInput(
                        instrument=instrument,
                        start=request.start,
                        end=request.end,
                        interval=request.interval,
                    ),
                )
                for instrument in request.instruments
            )
        )
        currencies = {history.currency for history in histories}
        if len(currencies) != 1:
            raise CurrencyMismatchError(currencies)
        items = tuple(self._comparison_item(history) for history in histories)
        return StockComparisonOutput(
            start=request.start,
            end=request.end,
            interval=request.interval,
            items=items,
        )

    async def corporate_actions(
        self, context: ExecutionContext, request: StockCorporateActionsInput
    ) -> StockCorporateActionsOutput:
        provider_request = CorporateActionsRequest(
            instrument=self._reference(request.instrument),
            start=request.start,
            end=request.end,
        )
        action_set, cache = await self._cached(
            "corporate-actions",
            provider_request,
            TypeAdapter(CorporateActions),
            self._settings.stock_actions_cache_ttl_seconds,
            lambda: self._provider.get_corporate_actions(self._context(context), provider_request),
        )
        self._validate_reference(request.instrument, action_set.instrument)
        for action in action_set.actions:
            self._validate_reference(request.instrument, action.instrument)
        normalized = tuple(
            StockCorporateAction(
                instrument=request.instrument,
                action_type=action.action_type,
                effective_at=action.effective_at,
                amount=action.amount,
                currency=action.currency,
                ratio=action.ratio,
                provider=action.metadata,
            )
            for action in sorted(action_set.actions, key=lambda item: item.effective_at)
        )
        return StockCorporateActionsOutput(
            instrument=request.instrument,
            start=request.start,
            end=request.end,
            actions=normalized,
            provider=action_set.metadata,
            cache=cache,
        )

    async def five_year_performance(
        self, context: ExecutionContext, request: FiveYearPerformanceInput
    ) -> FiveYearPerformanceOutput:
        as_of = request.as_of
        try:
            start = as_of.replace(year=as_of.year - 5)
        except ValueError:
            start = as_of.replace(year=as_of.year - 5, day=28)
        performance = await self.performance(
            context,
            StockPerformanceInput(
                instrument=request.instrument,
                start=start,
                end=as_of,
                interval=MarketInterval.DAILY,
            ),
        )
        return FiveYearPerformanceOutput(
            requested_as_of=as_of,
            effective_start=start,
            performance=performance,
        )

    async def benchmark_comparison(
        self, context: ExecutionContext, request: BenchmarkComparisonInput
    ) -> BenchmarkComparisonOutput:
        instrument_history, benchmark_history = await asyncio.gather(
            self.history(
                context,
                StockHistoryInput(
                    instrument=request.instrument,
                    start=request.start,
                    end=request.end,
                    interval=request.interval,
                ),
            ),
            self.history(
                context,
                StockHistoryInput(
                    instrument=request.benchmark,
                    start=request.start,
                    end=request.end,
                    interval=request.interval,
                ),
            ),
        )
        currencies = {instrument_history.currency, benchmark_history.currency}
        if len(currencies) != 1:
            raise CurrencyMismatchError(currencies)
        left = {bar.timestamp: bar for bar in instrument_history.bars}
        right = {bar.timestamp: bar for bar in benchmark_history.bars}
        overlap = sorted(left.keys() & right.keys())
        if len(overlap) < 2:
            raise InsufficientOverlapError(len(overlap))
        instrument_aligned = instrument_history.model_copy(
            update={"bars": tuple(left[timestamp] for timestamp in overlap)}
        )
        benchmark_aligned = benchmark_history.model_copy(
            update={"bars": tuple(right[timestamp] for timestamp in overlap)}
        )
        instrument_item = self._comparison_item(instrument_aligned)
        benchmark_item = self._comparison_item(benchmark_aligned)
        return BenchmarkComparisonOutput(
            instrument=instrument_item,
            benchmark=benchmark_item,
            overlapping_observations=len(overlap),
            excess_total_return=(
                instrument_item.metrics.total_return - benchmark_item.metrics.total_return
            ),
            excess_cagr=instrument_item.metrics.cagr - benchmark_item.metrics.cagr,
        )

    def _performance(self, history: StockHistoryOutput) -> StockPerformanceOutput:
        metrics, series = self._calculate(history.bars, history.interval)
        return StockPerformanceOutput(
            instrument=history.instrument,
            interval=history.interval,
            currency=history.currency,
            metrics=metrics,
            series=series,
            provider=history.provider,
            cache=history.cache,
        )

    def _comparison_item(self, history: StockHistoryOutput) -> StockComparisonItem:
        performance = self._performance(history)
        return StockComparisonItem(
            instrument=performance.instrument,
            currency=performance.currency,
            metrics=performance.metrics,
            series=performance.series,
            provider=performance.provider,
            cache=performance.cache,
        )

    @staticmethod
    def _calculate(
        bars: tuple[AdjustedPriceBar, ...], interval: MarketInterval
    ) -> tuple[PerformanceMetrics, tuple[RebasedPoint, ...]]:
        valid = tuple(bar for bar in bars if bar.adjusted_close > 0)
        if len(valid) != len(bars) or len(valid) < 2:
            raise InsufficientHistoryError(len(valid))
        values = tuple(bar.adjusted_close for bar in valid)
        seconds = Decimal(str((valid[-1].timestamp - valid[0].timestamp).total_seconds()))
        years = seconds / Decimal("31556952")
        if years <= 0:
            raise InsufficientHistoryError(len(valid))
        with localcontext() as context:
            context.prec = 28
            total_return = values[-1] / values[0] - 1
            cagr = ((values[-1] / values[0]).ln() / years).exp() - 1
            returns = tuple((current / previous).ln() for previous, current in pairwise(values))
            mean = sum(returns, Decimal(0)) / Decimal(len(returns))
            variance = sum(((value - mean) ** 2 for value in returns), Decimal(0)) / Decimal(
                max(1, len(returns) - 1)
            )
            factors = {
                MarketInterval.DAILY: Decimal(252),
                MarketInterval.WEEKLY: Decimal(52),
                MarketInterval.MONTHLY: Decimal(12),
            }
            volatility = (variance * factors[interval]).sqrt()
            peak = values[0]
            maximum_drawdown = Decimal(0)
            for value in values:
                peak = max(peak, value)
                maximum_drawdown = min(maximum_drawdown, value / peak - 1)
            series = tuple(
                RebasedPoint(timestamp=bar.timestamp, value=bar.adjusted_close / values[0] * 100)
                for bar in valid
            )
        return (
            PerformanceMetrics(
                start_at=valid[0].timestamp,
                end_at=valid[-1].timestamp,
                start_value=values[0],
                end_value=values[-1],
                observations=len(valid),
                total_return=total_return,
                cagr=cagr,
                annualized_volatility=volatility,
                maximum_drawdown=maximum_drawdown,
            ),
            series,
        )

    async def _cached(
        self,
        operation: str,
        request: BaseModel,
        adapter: TypeAdapter[OutputT],
        ttl_seconds: int,
        fetch: Callable[[], Awaitable[OutputT]],
    ) -> tuple[OutputT, CacheMetadata]:
        key = self._cache_key(operation, request)
        cached = await self._cache.get(key)
        if cached is not None:
            try:
                envelope = json.loads(cached)
                result = adapter.validate_python(envelope["payload"])
                structlog.get_logger().info("market_data_cache_hit", operation=operation)
                return result, CacheMetadata(
                    disposition=CacheDisposition.HIT,
                    cached_at=datetime.fromisoformat(envelope["cached_at"]),
                    expires_at=datetime.fromisoformat(envelope["expires_at"]),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, ValidationError):
                await self._cache.delete(key)
                structlog.get_logger().warning("market_data_cache_invalid", operation=operation)
        result = await fetch()
        structlog.get_logger().info("market_data_cache_miss", operation=operation)
        now = datetime.now(UTC)
        expires = datetime.fromtimestamp(now.timestamp() + ttl_seconds, UTC)
        envelope = {
            "cached_at": now.isoformat(),
            "expires_at": expires.isoformat(),
            "payload": adapter.dump_python(result, mode="json"),
        }
        await self._cache.set(
            key,
            json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode(),
            ttl_seconds,
        )
        return result, CacheMetadata(
            disposition=CacheDisposition.MISS,
            cached_at=now,
            expires_at=expires,
        )

    def _cache_key(self, operation: str, request: BaseModel) -> str:
        canonical = json.dumps(
            request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        return f"tradesentinel:market-data:v1:{self._chain_fingerprint}:{operation}:{digest}"

    @staticmethod
    def _reference(instrument: InstrumentRef) -> InstrumentReference:
        return InstrumentReference(
            symbol=instrument.symbol,
            exchange=instrument.exchange,
            identifier=str(instrument.instrument_id),
        )

    @staticmethod
    def _validate_reference(expected: InstrumentRef, actual: InstrumentReference) -> None:
        if actual.symbol.casefold() != expected.symbol.casefold() or (
            actual.exchange is not None
            and actual.exchange.casefold() != expected.exchange.casefold()
        ):
            raise MarketDataIntegrityError("provider instrument does not match the request")

    @staticmethod
    def _validate_currency(instrument: InstrumentRef, currency: str) -> None:
        if currency.casefold() != instrument.currency.casefold():
            raise MarketDataIntegrityError("provider currency does not match the instrument")

    @staticmethod
    def _context(context: ExecutionContext) -> ProviderContext:
        return ProviderContext(
            request_id=context.request_id,
            correlation_id=context.correlation_id,
            causation_id=context.causation_id,
            capability_run_id=context.capability_run_id,
        )
