from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tradesentinel.domain.instruments import InstrumentRef
from tradesentinel.domain.market_data import (
    CacheMetadata,
    MarketInterval,
    StockHistoryOutput,
)
from tradesentinel.providers.contracts import ProviderMetadata


class TechnicalContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TechnicalStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    EMPTY = "empty"


class TechnicalParameters(TechnicalContract):
    rsi_period: int = Field(default=14, ge=2, le=200)
    macd_fast_period: int = Field(default=12, ge=2, le=200)
    macd_slow_period: int = Field(default=26, ge=3, le=400)
    macd_signal_period: int = Field(default=9, ge=2, le=200)
    ema_period: int = Field(default=20, ge=2, le=400)
    sma_period: int = Field(default=20, ge=2, le=400)
    atr_period: int = Field(default=14, ge=2, le=200)
    adx_period: int = Field(default=14, ge=2, le=200)
    momentum_roc_period: int = Field(default=10, ge=1, le=200)
    volatility_period: int = Field(default=20, ge=2, le=200)
    trend_fast_period: int = Field(default=20, ge=2, le=200)
    trend_slow_period: int = Field(default=50, ge=3, le=400)
    level_lookback: int = Field(default=60, ge=5, le=500)
    pivot_span: int = Field(default=2, ge=1, le=20)
    pivot_max_levels: int = Field(default=3, ge=1, le=10)
    pivot_atr_multiplier: Decimal = Field(default=Decimal("0.5"), gt=0, le=5)
    trend_spread_threshold: Decimal = Field(default=Decimal("0.005"), ge=0, le=1)
    momentum_rsi_lower: Decimal = Field(default=Decimal("45"), ge=0, le=100)
    momentum_rsi_upper: Decimal = Field(default=Decimal("55"), ge=0, le=100)
    volatility_low_percentile: Decimal = Field(default=Decimal("0.25"), ge=0, le=1)
    volatility_high_percentile: Decimal = Field(default=Decimal("0.75"), ge=0, le=1)

    @model_validator(mode="after")
    def validate_period_relationships(self) -> TechnicalParameters:
        if self.macd_fast_period >= self.macd_slow_period:
            raise ValueError("MACD fast period must be below its slow period")
        if self.trend_fast_period >= self.trend_slow_period:
            raise ValueError("trend fast period must be below its slow period")
        if self.momentum_rsi_lower >= self.momentum_rsi_upper:
            raise ValueError("momentum RSI lower threshold must be below the upper threshold")
        if self.volatility_low_percentile >= self.volatility_high_percentile:
            raise ValueError("volatility percentile thresholds must be ordered")
        if self.level_lookback < self.pivot_span * 2 + 1:
            raise ValueError("level lookback is too short for the selected pivot span")
        return self


class TechnicalAnalysisRequest(TechnicalParameters):
    query: str = Field(min_length=1, max_length=200)
    exchange: str | None = Field(default=None, min_length=1, max_length=20)
    start: datetime | None = None
    end: datetime | None = None
    as_of: datetime | None = None
    interval: MarketInterval = MarketInterval.DAILY

    @model_validator(mode="after")
    def validate_range_shape(self) -> TechnicalAnalysisRequest:
        if (self.start is None) != (self.end is None):
            raise ValueError("start and end must be supplied together")
        if self.start is not None and self.as_of is not None:
            raise ValueError("as_of cannot be combined with an explicit range")
        if self.start is not None and self.end is not None and self.start >= self.end:
            raise ValueError("start must be before end")
        return self


class TechnicalWindowInput(TechnicalContract):
    start: datetime | None = None
    end: datetime | None = None
    as_of: datetime | None = None

    @model_validator(mode="after")
    def validate_range_shape(self) -> TechnicalWindowInput:
        if (self.start is None) != (self.end is None):
            raise ValueError("start and end must be supplied together")
        if self.start is not None and self.as_of is not None:
            raise ValueError("as_of cannot be combined with an explicit range")
        if self.start is not None and self.end is not None and self.start >= self.end:
            raise ValueError("start must be before end")
        return self


class TechnicalWindow(TechnicalContract):
    start: datetime
    end: datetime


class AdjustedTechnicalBar(TechnicalContract):
    timestamp: datetime
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: Decimal | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_ohlc(self) -> AdjustedTechnicalBar:
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("adjusted high and low must bound open and close")
        return self


class TechnicalCalculationInput(TechnicalContract):
    history: StockHistoryOutput
    requested_start: datetime
    requested_end: datetime
    parameters: TechnicalParameters = Field(default_factory=TechnicalParameters)

    @model_validator(mode="after")
    def validate_requested_range(self) -> TechnicalCalculationInput:
        if self.requested_start >= self.requested_end:
            raise ValueError("requested start must be before requested end")
        return self


class IndicatorPoint(TechnicalContract):
    timestamp: datetime
    value: Decimal


class IndicatorSeries(TechnicalContract):
    period: int
    latest: Decimal
    points: tuple[IndicatorPoint, ...]


class RsiOutput(TechnicalContract):
    instrument: InstrumentRef
    interval: MarketInterval
    series: IndicatorSeries


class EmaOutput(RsiOutput):
    """Exponential moving-average output."""


class SmaOutput(RsiOutput):
    """Simple moving-average output."""


class AtrOutput(RsiOutput):
    """Average true-range output."""


class MacdPoint(TechnicalContract):
    timestamp: datetime
    macd: Decimal
    signal: Decimal
    histogram: Decimal


class MacdOutput(TechnicalContract):
    instrument: InstrumentRef
    interval: MarketInterval
    fast_period: int
    slow_period: int
    signal_period: int
    latest: MacdPoint
    points: tuple[MacdPoint, ...]


class AdxPoint(TechnicalContract):
    timestamp: datetime
    adx: Decimal
    positive_di: Decimal
    negative_di: Decimal


class AdxOutput(TechnicalContract):
    instrument: InstrumentRef
    interval: MarketInterval
    period: int
    latest: AdxPoint
    points: tuple[AdxPoint, ...]


class PriceLevel(TechnicalContract):
    method: Literal["rolling_extreme", "pivot_cluster"]
    level: Decimal
    touches: int = Field(ge=1)
    first_tested_at: datetime
    last_tested_at: datetime
    distance_percent: Decimal


class LevelOutput(TechnicalContract):
    instrument: InstrumentRef
    interval: MarketInterval
    side: Literal["support", "resistance"]
    current_price: Decimal
    lookback: int
    levels: tuple[PriceLevel, ...]


class TrendOutput(TechnicalContract):
    instrument: InstrumentRef
    interval: MarketInterval
    direction: Literal["rising", "falling", "sideways"]
    strength: Literal["weak", "developing", "strong"]
    fast_ema: Decimal
    slow_ema: Decimal
    spread_percent: Decimal
    adx: Decimal


class MomentumOutput(TechnicalContract):
    instrument: InstrumentRef
    interval: MarketInterval
    direction: Literal["positive", "neutral", "negative"]
    positive_votes: int = Field(ge=0, le=3)
    negative_votes: int = Field(ge=0, le=3)
    rsi: Decimal
    macd_histogram: Decimal
    rate_of_change: Decimal


class VolatilityOutput(TechnicalContract):
    instrument: InstrumentRef
    interval: MarketInterval
    regime: Literal["low", "normal", "high", "unknown"]
    period: int
    annualized_volatility: Decimal
    atr_percent: Decimal
    percentile_rank: Decimal | None = Field(default=None, ge=0, le=1)
    rolling: tuple[IndicatorPoint, ...]


class TechnicalSnapshot(TechnicalContract):
    instrument: InstrumentRef
    status: TechnicalStatus
    interval: MarketInterval
    requested_start: datetime
    requested_end: datetime
    observed_start: datetime | None = None
    observed_end: datetime | None = None
    data_cutoff: datetime | None = None
    observation_count: int = Field(ge=0)
    price_basis: Literal["adjusted_ohlc"] = "adjusted_ohlc"
    calculation_version: Literal["technical-v1"] = "technical-v1"
    parameters: TechnicalParameters
    provider: ProviderMetadata
    cache: CacheMetadata
    warnings: tuple[str, ...] = ()
    rsi: RsiOutput | None = None
    macd: MacdOutput | None = None
    ema: EmaOutput | None = None
    sma: SmaOutput | None = None
    atr: AtrOutput | None = None
    adx: AdxOutput | None = None
    support: LevelOutput | None = None
    resistance: LevelOutput | None = None
    trend: TrendOutput | None = None
    momentum: MomentumOutput | None = None
    volatility: VolatilityOutput | None = None
