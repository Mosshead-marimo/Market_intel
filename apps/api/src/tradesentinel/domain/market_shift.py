from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator

from tradesentinel.domain.instruments import InstrumentRef


class MarketShiftContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MarketShiftCategory(StrEnum):
    NEWS = "news"
    PUBLIC_SENTIMENT = "public_sentiment"
    TECHNICAL_TREND = "technical_trend"
    FUNDAMENTALS = "fundamentals"
    SECTOR = "sector"
    MACRO = "macro"
    INSTITUTIONAL_ACTIVITY = "institutional_activity"


class MarketShiftDirection(StrEnum):
    IMPROVING = "improving"
    STABLE = "stable"
    DETERIORATING = "deteriorating"
    UNCERTAIN = "uncertain"


class MarketShiftStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class SignalPolarity(StrEnum):
    POSITIVE_WHEN_RISING = "positive_when_rising"
    NEGATIVE_WHEN_RISING = "negative_when_rising"
    CONTEXT_ONLY = "context_only"


class MarketShiftWindow(MarketShiftContract):
    previous_start: datetime
    current_start: datetime
    end: datetime

    @model_validator(mode="after")
    def validate_order(self) -> MarketShiftWindow:
        if not self.previous_start < self.current_start < self.end:
            raise ValueError("market-shift windows must be strictly ordered")
        if self.current_start - self.previous_start != self.end - self.current_start:
            raise ValueError("market-shift comparison windows must have equal duration")
        return self

    @classmethod
    def ending_at(cls, end: datetime, days: int) -> MarketShiftWindow:
        current_start = end - timedelta(days=days)
        return cls(
            previous_start=current_start - timedelta(days=days),
            current_start=current_start,
            end=end,
        )


class MarketShiftObservation(MarketShiftContract):
    observation_id: UUID = Field(default_factory=uuid4)
    idempotency_key: str = Field(min_length=1, max_length=160)
    category: MarketShiftCategory
    instrument_id: UUID | None = None
    scope: str = Field(min_length=1, max_length=160)
    metric: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    value: Decimal
    unit: str = Field(min_length=1, max_length=40)
    observed_at: datetime
    known_at: datetime
    retrieved_at: datetime
    source_id: str = Field(min_length=1, max_length=240)
    provider: str = Field(min_length=1, max_length=120)
    source_url: AnyHttpUrl | None = None
    source_version: str = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def validate_point_in_time(self) -> MarketShiftObservation:
        if self.known_at < self.observed_at:
            raise ValueError("known_at cannot precede observed_at")
        if self.retrieved_at < self.known_at:
            raise ValueError("retrieved_at cannot precede known_at")
        return self


class MarketShiftObservationBatch(MarketShiftContract):
    idempotency_key: str = Field(min_length=1, max_length=160)
    observations: tuple[MarketShiftObservation, ...] = Field(min_length=1, max_length=10_000)


class MarketShiftObservationReceipt(MarketShiftContract):
    batch_id: UUID
    accepted: int = Field(ge=0)
    duplicate: bool = False


class MarketShiftObservationQuery(MarketShiftContract):
    instrument: InstrumentRef
    as_of: datetime = Field(default_factory=lambda: datetime.now(UTC))
    window_days: int = Field(default=90, ge=7, le=365)
    idempotency_key: str | None = Field(default=None, max_length=160)


class MarketShiftObservationSet(MarketShiftContract):
    instrument: InstrumentRef
    window: MarketShiftWindow
    observations: tuple[MarketShiftObservation, ...]
    idempotency_key: str


class MarketShiftEvidence(MarketShiftContract):
    evidence_id: str = Field(pattern=r"^mse_[a-f0-9]{16}$")
    category: MarketShiftCategory
    metric: str
    source_id: str
    provider: str
    timestamp: datetime
    current_value: Decimal
    previous_value: Decimal
    normalized_delta: Decimal = Field(ge=-1, le=1)
    source_url: AnyHttpUrl | None = None


class MarketShiftCategorySignal(MarketShiftContract):
    category: MarketShiftCategory
    score: Decimal = Field(ge=-1, le=1)
    weight: Decimal = Field(gt=0, le=1)
    weighted_contribution: Decimal = Field(ge=-1, le=1)
    coverage: Decimal = Field(ge=0, le=1)
    freshness: Decimal = Field(ge=0, le=1)
    agreement: Decimal = Field(ge=0, le=1)
    temporal_alignment: Decimal = Field(ge=0, le=1)
    confidence: Decimal = Field(ge=0, le=1)
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class MarketShiftDriver(MarketShiftContract):
    label: str = Field(min_length=1, max_length=240)
    category: MarketShiftCategory
    contribution: Decimal = Field(ge=-1, le=1)
    confidence: Decimal = Field(ge=0, le=1)
    observed_at: datetime
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class MarketShiftNarrative(MarketShiftContract):
    narrative_id: str = Field(pattern=r"^msn_[a-f0-9]{16}$")
    label: str = Field(min_length=1, max_length=240)
    direction: Literal["emerging", "strengthening", "stable", "weakening", "retired"]
    current_prevalence: Decimal = Field(ge=0, le=1)
    previous_prevalence: Decimal = Field(ge=0, le=1)
    change: Decimal = Field(ge=-1, le=1)
    evidence_ids: tuple[str, ...] = Field(min_length=1)


class MarketShiftCalculateInput(MarketShiftContract):
    instrument: InstrumentRef
    as_of: datetime = Field(default_factory=lambda: datetime.now(UTC))
    window_days: int = Field(default=90, ge=7, le=365)
    idempotency_key: str | None = Field(default=None, max_length=160)


class MarketShiftRequest(MarketShiftContract):
    query: str = Field(min_length=1, max_length=200)
    exchange: str | None = Field(default=None, min_length=1, max_length=20)
    as_of: datetime | None = None
    window_days: int = Field(default=90, ge=7, le=365)
    idempotency_key: str | None = Field(default=None, max_length=160)


class MarketShiftScoreInput(MarketShiftContract):
    instrument: InstrumentRef
    window: MarketShiftWindow
    observations: tuple[MarketShiftObservation, ...]
    idempotency_key: str


class MarketShiftSnapshot(MarketShiftContract):
    calculation_id: UUID
    status: Literal["completed"] = "completed"
    instrument: InstrumentRef
    generated_at: datetime
    data_cutoff: datetime
    window: MarketShiftWindow
    score: Decimal = Field(ge=-100, le=100)
    direction: MarketShiftDirection
    confidence: Decimal = Field(ge=0, le=1)
    category_signals: tuple[MarketShiftCategorySignal, ...] = Field(min_length=7, max_length=7)
    catalysts: tuple[MarketShiftDriver, ...] = ()
    risks: tuple[MarketShiftDriver, ...] = ()
    narratives: tuple[MarketShiftNarrative, ...] = ()
    evidence: tuple[MarketShiftEvidence, ...] = Field(min_length=7)
    calculation_version: Literal["market-shift-v1"] = "market-shift-v1"
    evidence_schema_version: Literal["market-shift-evidence-v1"] = "market-shift-evidence-v1"
    scoring_rule_version: str
    configuration_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_categories(self) -> MarketShiftSnapshot:
        categories = tuple(signal.category for signal in self.category_signals)
        if set(categories) != set(MarketShiftCategory):
            raise ValueError("a market-shift snapshot requires every category exactly once")
        if len(categories) != len(set(categories)):
            raise ValueError("market-shift categories must be unique")
        known = {item.evidence_id for item in self.evidence}
        referenced: set[str] = set()
        for signal in self.category_signals:
            referenced.update(signal.evidence_ids)
        for driver in (*self.catalysts, *self.risks):
            referenced.update(driver.evidence_ids)
        for narrative in self.narratives:
            referenced.update(narrative.evidence_ids)
        if not referenced <= known:
            raise ValueError("market-shift output references unknown evidence")
        return self


class MarketShiftAttempt(MarketShiftContract):
    calculation_id: UUID
    status: MarketShiftStatus
    instrument_id: UUID
    requested_at: datetime
    completed_at: datetime
    idempotency_key: str
    snapshot: MarketShiftSnapshot | None = None
    error_code: str | None = None
    error_message: str | None = None


class MarketShiftReference(MarketShiftContract):
    calculation_id: UUID


class MarketShiftHistoryRequest(MarketShiftContract):
    instrument_id: UUID
    cursor: datetime | None = None
    limit: int = Field(default=25, ge=1, le=100)


class MarketShiftHistoryItem(MarketShiftContract):
    snapshot: MarketShiftSnapshot
    score_change: Decimal | None = None
    confidence_change: Decimal | None = None
    direction_changed: bool = False
    new_narratives: tuple[str, ...] = ()
    retired_narratives: tuple[str, ...] = ()


class MarketShiftHistoryPage(MarketShiftContract):
    items: tuple[MarketShiftHistoryItem, ...]
    next_cursor: datetime | None = None


class MarketShiftWatchlistEntry(MarketShiftContract):
    watchlist_id: UUID = Field(default_factory=uuid4)
    instrument: InstrumentRef
    enabled: bool = True
    timezone: str = "UTC"
    run_time: str = Field(default="02:00", pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    window_days: int = Field(default=90, ge=7, le=365)
    next_run_at: datetime | None = None
    last_run_at: datetime | None = None


class MarketShiftWatchlist(MarketShiftContract):
    items: tuple[MarketShiftWatchlistEntry, ...]


class MarketShiftWatchlistReference(MarketShiftContract):
    watchlist_id: UUID


class EmptyMarketShiftInput(MarketShiftContract):
    pass


class MarketShiftScheduleResult(MarketShiftContract):
    processed: int = Field(ge=0)
