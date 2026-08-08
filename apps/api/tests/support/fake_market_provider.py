from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from pydantic import BaseModel
from tradesentinel.platform.capabilities import Capability
from tradesentinel.platform.config import Settings
from tradesentinel.platform.contracts import (
    CapabilityResult,
    ExecutionContext,
    RunMetadata,
    RunStatus,
)
from tradesentinel.providers.contracts import (
    CorporateAction,
    CorporateActions,
    CorporateActionsRequest,
    CorporateActionType,
    FreshnessStatus,
    InstrumentRecord,
    InstrumentSearchRequest,
    LicenseClassification,
    MarketQuote,
    PriceBar,
    PriceHistory,
    PriceHistoryRequest,
    ProviderContext,
    ProviderMetadata,
    QuoteRequest,
)
from tradesentinel.providers.interfaces import MarketDataProvider


def metadata(source: str, observed_at: datetime) -> ProviderMetadata:
    return ProviderMetadata(
        provider="test-market",
        source_id=source,
        observed_at=observed_at,
        retrieved_at=observed_at,
        timezone="UTC",
        license=LicenseClassification.INTERNAL,
        freshness=FreshnessStatus.FRESH,
    )


class DeterministicMarketDataProvider(MarketDataProvider):
    quote_calls = 0
    history_calls = 0
    action_calls = 0

    async def search_instruments(
        self, context: ProviderContext, request: InstrumentSearchRequest
    ) -> tuple[InstrumentRecord, ...]:
        del context, request
        return ()

    async def get_quote(self, context: ProviderContext, request: QuoteRequest) -> MarketQuote:
        del context
        type(self).quote_calls += 1
        observed = datetime(2026, 1, 2, 10, tzinfo=UTC)
        return MarketQuote(
            instrument=request.instrument,
            price=Decimal("110"),
            previous_close=Decimal("100"),
            open=Decimal("102"),
            high=Decimal("112"),
            low=Decimal("101"),
            volume=Decimal("1000"),
            market_status="closed",
            currency="INR",
            as_of=observed,
            metadata=metadata("quote", observed),
        )

    async def get_history(
        self, context: ProviderContext, request: PriceHistoryRequest
    ) -> PriceHistory:
        del context
        type(self).history_calls += 1
        step = max((request.end - request.start) / 2, timedelta(days=1))
        timestamps = (request.start, request.start + step, request.end)
        values = (Decimal("100"), Decimal("90"), Decimal("121"))
        bars = tuple(
            PriceBar(
                timestamp=timestamp,
                open=value,
                high=value + 2,
                low=value - 2,
                close=value,
                adjusted_close=value,
                volume=Decimal("1000"),
            )
            for timestamp, value in zip(timestamps, values, strict=True)
        )
        return PriceHistory(
            instrument=request.instrument,
            interval=request.interval,
            currency="INR",
            bars=bars,
            metadata=metadata("history", request.end),
        )

    async def get_corporate_actions(
        self, context: ProviderContext, request: CorporateActionsRequest
    ) -> CorporateActions:
        del context
        type(self).action_calls += 1
        effective = request.start + (request.end - request.start) / 2
        return CorporateActions(
            instrument=request.instrument,
            actions=(
                CorporateAction(
                    instrument=request.instrument,
                    action_type=CorporateActionType.DIVIDEND,
                    effective_at=effective,
                    amount=Decimal("2"),
                    currency="INR",
                    metadata=metadata("action", effective),
                ),
            ),
            metadata=metadata("actions", effective),
        )


class ProviderFixtureInput(BaseModel):
    pass


class ProviderFixtureCapability(Capability[ProviderFixtureInput]):
    input_model = ProviderFixtureInput

    async def execute(
        self, context: ExecutionContext, payload: ProviderFixtureInput
    ) -> CapabilityResult:
        del context, payload
        now = datetime.now(UTC)
        return CapabilityResult(
            capability="test.market_provider",
            status=RunStatus.COMPLETED,
            metadata=RunMetadata(started_at=now, completed_at=now),
        )


def market_test_settings() -> Settings:
    tests_root = Path(__file__).parents[1]
    api_root = tests_root.parent
    return Settings(
        environment="test",
        persistence_backend="memory",
        event_backend="memory",
        cache_backend="memory",
        market_data_providers=("test-market",),
        module_roots=(
            api_root / "src" / "tradesentinel" / "modules",
            tests_root / "fixtures" / "market_provider",
        ),
    )
