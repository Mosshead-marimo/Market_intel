from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator


class ProviderContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class ProviderKind(StrEnum):
    MARKET_DATA = "market_data"
    NEWS = "news"
    SENTIMENT = "sentiment"
    ECONOMIC_DATA = "economic_data"
    FUNDAMENTALS = "fundamentals"


class LicenseClassification(StrEnum):
    INTERNAL = "internal"
    REDISTRIBUTABLE = "redistributable"
    RESTRICTED = "restricted"
    UNKNOWN = "unknown"


class FreshnessStatus(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


class ProviderContext(ProviderContract):
    request_id: UUID
    correlation_id: UUID
    causation_id: UUID | None = None
    capability_run_id: UUID | None = None


class ProviderMetadata(ProviderContract):
    provider: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    observed_at: datetime | None = None
    retrieved_at: datetime
    timezone: str | None = None
    license: LicenseClassification = LicenseClassification.UNKNOWN
    freshness: FreshnessStatus = FreshnessStatus.UNKNOWN


class ProviderRateLimit(ProviderContract):
    requests: int = Field(default=60, ge=1)
    window_seconds: int = Field(default=60, ge=1)


class ProviderDescriptor(ProviderContract):
    kind: ProviderKind
    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    class_path: str
    timeout_ms: int = Field(default=10_000, ge=1, le=300_000)
    rate_limit: ProviderRateLimit = ProviderRateLimit()


class InstrumentReference(ProviderContract):
    symbol: str = Field(min_length=1)
    exchange: str | None = None
    identifier: str | None = None


class InstrumentSearchRequest(ProviderContract):
    query: str = Field(min_length=1)
    limit: int = Field(default=20, ge=1, le=100)


class InstrumentRecord(ProviderContract):
    instrument: InstrumentReference
    name: str
    asset_type: str
    currency: str | None = None
    metadata: ProviderMetadata


class QuoteRequest(ProviderContract):
    instrument: InstrumentReference


class MarketQuote(ProviderContract):
    instrument: InstrumentReference
    price: Decimal
    currency: str
    as_of: datetime
    previous_close: Decimal | None = None
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    volume: Decimal | None = None
    market_status: str | None = None
    metadata: ProviderMetadata

    @model_validator(mode="after")
    def validate_quote(self) -> MarketQuote:
        values = (
            self.price,
            self.previous_close,
            self.open,
            self.high,
            self.low,
            self.volume,
        )
        if any(value is not None and value < 0 for value in values):
            raise ValueError("quote numeric values cannot be negative")
        if self.high is not None and self.low is not None and self.high < self.low:
            raise ValueError("quote high cannot be below low")
        return self


class PriceHistoryRequest(ProviderContract):
    instrument: InstrumentReference
    start: datetime
    end: datetime
    interval: str = Field(min_length=1)


class PriceBar(ProviderContract):
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    adjusted_close: Decimal
    volume: Decimal | None = None

    @model_validator(mode="after")
    def validate_prices(self) -> PriceBar:
        if min(self.open, self.high, self.low, self.close, self.adjusted_close) < 0:
            raise ValueError("price values cannot be negative")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("high and low must bound open and close")
        if self.volume is not None and self.volume < 0:
            raise ValueError("volume cannot be negative")
        return self


class PriceHistory(ProviderContract):
    instrument: InstrumentReference
    interval: str
    currency: str
    bars: tuple[PriceBar, ...]
    metadata: ProviderMetadata

    @model_validator(mode="after")
    def validate_bars(self) -> PriceHistory:
        timestamps = [bar.timestamp for bar in self.bars]
        if timestamps != sorted(timestamps) or len(timestamps) != len(set(timestamps)):
            raise ValueError("history bars must have unique ascending timestamps")
        return self


class CorporateActionType(StrEnum):
    DIVIDEND = "dividend"
    SPLIT = "split"
    SPINOFF = "spinoff"
    MERGER = "merger"
    SYMBOL_CHANGE = "symbol_change"
    OTHER = "other"


class CorporateActionsRequest(ProviderContract):
    instrument: InstrumentReference
    start: datetime
    end: datetime


class CorporateAction(ProviderContract):
    instrument: InstrumentReference
    action_type: CorporateActionType
    effective_at: datetime
    amount: Decimal | None = None
    currency: str | None = None
    ratio: Decimal | None = None
    metadata: ProviderMetadata


class CorporateActions(ProviderContract):
    instrument: InstrumentReference
    actions: tuple[CorporateAction, ...]
    metadata: ProviderMetadata


class NewsSearchRequest(ProviderContract):
    query: str = Field(min_length=1)
    start: datetime | None = None
    end: datetime | None = None
    limit: int = Field(default=20, ge=1, le=100)


class NewsArticle(ProviderContract):
    source_id: str
    title: str
    url: AnyHttpUrl
    published_at: datetime | None = None
    summary: str | None = None
    untrusted: Literal[True] = True
    metadata: ProviderMetadata


class NewsDocumentRequest(ProviderContract):
    source_id: str = Field(min_length=1)


class NewsDocument(ProviderContract):
    source_id: str
    title: str
    url: AnyHttpUrl
    content: str
    content_type: str
    published_at: datetime | None = None
    untrusted: Literal[True] = True
    metadata: ProviderMetadata


class SentimentRequest(ProviderContract):
    query: str = Field(min_length=1)
    start: datetime | None = None
    end: datetime | None = None
    limit: int = Field(default=100, ge=1, le=1_000)


class SentimentObservation(ProviderContract):
    source_id: str
    text: str
    occurred_at: datetime
    label: str | None = None
    provider_score: Decimal | None = None
    provider_model: str | None = None
    untrusted: Literal[True] = True
    metadata: ProviderMetadata


class EconomicSeriesSearchRequest(ProviderContract):
    query: str = Field(min_length=1)
    limit: int = Field(default=20, ge=1, le=100)


class EconomicSeries(ProviderContract):
    series_id: str
    title: str
    frequency: str
    unit: str
    metadata: ProviderMetadata


class EconomicObservationsRequest(ProviderContract):
    series_id: str = Field(min_length=1)
    start: datetime
    end: datetime


class EconomicObservation(ProviderContract):
    observed_at: datetime
    value: Decimal | None


class EconomicObservationSeries(ProviderContract):
    series: EconomicSeries
    observations: tuple[EconomicObservation, ...]
    metadata: ProviderMetadata


class CompanyProfileRequest(ProviderContract):
    instrument: InstrumentReference


class CompanyProfile(ProviderContract):
    instrument: InstrumentReference
    legal_name: str
    description: str | None = None
    sector: str | None = None
    industry: str | None = None
    reporting_currency: str | None = None
    metadata: ProviderMetadata


class FinancialStatementsRequest(ProviderContract):
    instrument: InstrumentReference
    statement_types: tuple[str, ...] = ()
    periods: int = Field(default=4, ge=1, le=40)


class FinancialLineItem(ProviderContract):
    concept: str
    value: Decimal | None
    unit: str


class FinancialStatement(ProviderContract):
    instrument: InstrumentReference
    statement_type: str
    period_start: datetime | None = None
    period_end: datetime
    filed_at: datetime | None = None
    currency: str | None = None
    items: tuple[FinancialLineItem, ...]
    metadata: ProviderMetadata


class FundamentalFactsRequest(ProviderContract):
    instrument: InstrumentReference
    as_of: datetime | None = None


class FundamentalFact(ProviderContract):
    instrument: InstrumentReference
    concept: str
    value: Decimal | str | None
    unit: str | None = None
    period_end: datetime | None = None
    metadata: ProviderMetadata
