from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tradesentinel.domain.instruments import InstrumentRef
from tradesentinel.providers.contracts import CorporateActionType, ProviderMetadata


class MarketDataContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MarketInterval(StrEnum):
    DAILY = "1d"
    WEEKLY = "1wk"
    MONTHLY = "1mo"


class CacheDisposition(StrEnum):
    HIT = "hit"
    MISS = "miss"


class CacheMetadata(MarketDataContract):
    disposition: CacheDisposition
    cached_at: datetime
    expires_at: datetime


class StockQuoteInput(MarketDataContract):
    instrument: InstrumentRef


class MarketRangeInput(MarketDataContract):
    instrument: InstrumentRef
    start: datetime
    end: datetime
    interval: MarketInterval = MarketInterval.DAILY

    @model_validator(mode="after")
    def validate_range(self) -> MarketRangeInput:
        if self.start >= self.end:
            raise ValueError("start must be before end")
        return self


class StockHistoryInput(MarketRangeInput):
    pass


class StockPerformanceInput(MarketRangeInput):
    pass


class StockCorporateActionsInput(MarketDataContract):
    instrument: InstrumentRef
    start: datetime
    end: datetime

    @model_validator(mode="after")
    def validate_range(self) -> StockCorporateActionsInput:
        if self.start >= self.end:
            raise ValueError("start must be before end")
        return self


class FiveYearPerformanceInput(MarketDataContract):
    instrument: InstrumentRef
    as_of: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StockComparisonInput(MarketDataContract):
    instruments: tuple[InstrumentRef, ...] = Field(min_length=2, max_length=10)
    start: datetime
    end: datetime
    interval: MarketInterval = MarketInterval.DAILY

    @model_validator(mode="after")
    def validate_input(self) -> StockComparisonInput:
        if self.start >= self.end:
            raise ValueError("start must be before end")
        identifiers = [item.instrument_id for item in self.instruments]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("comparison instruments must be unique")
        return self


class BenchmarkComparisonInput(MarketDataContract):
    instrument: InstrumentRef
    benchmark: InstrumentRef
    start: datetime
    end: datetime
    interval: MarketInterval = MarketInterval.DAILY

    @model_validator(mode="after")
    def validate_input(self) -> BenchmarkComparisonInput:
        if self.instrument.instrument_id == self.benchmark.instrument_id:
            raise ValueError("instrument and benchmark must differ")
        if self.start >= self.end:
            raise ValueError("start must be before end")
        return self


class StockQuoteOutput(MarketDataContract):
    instrument: InstrumentRef
    price: Decimal
    currency: str
    as_of: datetime
    previous_close: Decimal | None = None
    change: Decimal | None = None
    change_percent: Decimal | None = None
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    volume: Decimal | None = None
    market_status: str | None = None
    provider: ProviderMetadata
    cache: CacheMetadata


class AdjustedPriceBar(MarketDataContract):
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adjusted_close: Decimal
    volume: Decimal | None = None


class StockHistoryOutput(MarketDataContract):
    instrument: InstrumentRef
    interval: MarketInterval
    price_basis: Literal["adjusted"] = "adjusted"
    currency: str
    bars: tuple[AdjustedPriceBar, ...]
    provider: ProviderMetadata
    cache: CacheMetadata


class PerformanceMetrics(MarketDataContract):
    start_at: datetime
    end_at: datetime
    start_value: Decimal
    end_value: Decimal
    observations: int = Field(ge=2)
    total_return: Decimal
    cagr: Decimal
    annualized_volatility: Decimal
    maximum_drawdown: Decimal


class RebasedPoint(MarketDataContract):
    timestamp: datetime
    value: Decimal


class StockPerformanceOutput(MarketDataContract):
    instrument: InstrumentRef
    interval: MarketInterval
    currency: str
    metrics: PerformanceMetrics
    series: tuple[RebasedPoint, ...]
    provider: ProviderMetadata
    cache: CacheMetadata


class StockComparisonItem(MarketDataContract):
    instrument: InstrumentRef
    currency: str
    metrics: PerformanceMetrics
    series: tuple[RebasedPoint, ...]
    provider: ProviderMetadata
    cache: CacheMetadata


class StockComparisonOutput(MarketDataContract):
    start: datetime
    end: datetime
    interval: MarketInterval
    items: tuple[StockComparisonItem, ...]


class StockCorporateAction(MarketDataContract):
    instrument: InstrumentRef
    action_type: CorporateActionType
    effective_at: datetime
    amount: Decimal | None = None
    currency: str | None = None
    ratio: Decimal | None = None
    provider: ProviderMetadata


class StockCorporateActionsOutput(MarketDataContract):
    instrument: InstrumentRef
    start: datetime
    end: datetime
    actions: tuple[StockCorporateAction, ...]
    provider: ProviderMetadata
    cache: CacheMetadata


class FiveYearPerformanceOutput(MarketDataContract):
    requested_as_of: datetime
    effective_start: datetime
    performance: StockPerformanceOutput


class BenchmarkComparisonOutput(MarketDataContract):
    instrument: StockComparisonItem
    benchmark: StockComparisonItem
    overlapping_observations: int = Field(ge=2)
    excess_total_return: Decimal
    excess_cagr: Decimal
