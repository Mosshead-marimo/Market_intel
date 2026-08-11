from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator

from tradesentinel.domain.instruments import InstrumentRef


class SentimentContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SentimentLabel(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    UNKNOWN = "unknown"


class AnalysisStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    EMPTY = "empty"
    INSUFFICIENT = "insufficient"


class SentimentEvidence(SentimentContract):
    source_id: str
    provider: str
    source_type: str
    observed_at: datetime
    retrieved_at: datetime
    url: AnyHttpUrl | None = None
    untrusted: Literal[True] = True


class SentimentSignal(SentimentContract):
    label: SentimentLabel
    score: Decimal | None = Field(default=None, ge=-1, le=1)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    method: Literal["provider", "lexicon", "none"]
    version: str
    positive_hits: int = Field(default=0, ge=0)
    negative_hits: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_unknown(self) -> SentimentSignal:
        if self.label == SentimentLabel.UNKNOWN and (
            self.score is not None or self.confidence is not None
        ):
            raise ValueError("unknown signals cannot contain score or confidence")
        if self.label != SentimentLabel.UNKNOWN and (self.score is None or self.confidence is None):
            raise ValueError("known signals require score and confidence")
        return self


class Discussion(SentimentContract):
    discussion_id: UUID
    provider_source_id: str
    text_excerpt: str
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    occurred_at: datetime
    author_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    language: str
    engagement_count: int = Field(ge=0)
    provider_spam: bool
    evidence: SentimentEvidence
    signal: SentimentSignal


class SpamDecision(SentimentContract):
    discussion_id: UUID
    spam: bool
    reasons: tuple[
        Literal[
            "provider_spam",
            "too_short",
            "too_many_urls",
            "too_many_tags",
            "repeated_tokens",
            "duplicate",
            "author_burst",
        ],
        ...,
    ] = ()


class CompanyMention(SentimentContract):
    instrument: InstrumentRef
    matched_value: str
    method: Literal["cashtag", "symbol", "name", "alias"]
    confidence: Decimal = Field(ge=0, le=1)


class DetectedDiscussion(SentimentContract):
    discussion: Discussion
    mentions: tuple[CompanyMention, ...]
    target_relevant: bool


class WeightedObservation(SentimentContract):
    discussion: Discussion
    mentions: tuple[CompanyMention, ...]
    provider_weight: Decimal = Field(ge=0)
    source_type_weight: Decimal = Field(ge=0)
    engagement_multiplier: Decimal = Field(ge=1, le=Decimal("1.5"))
    weight: Decimal = Field(ge=0)


class WindowMetrics(SentimentContract):
    start: datetime
    end: datetime
    mention_count: int = Field(ge=0)
    usable_count: int = Field(ge=0)
    positive_share: Decimal | None = Field(default=None, ge=0, le=1)
    neutral_share: Decimal | None = Field(default=None, ge=0, le=1)
    negative_share: Decimal | None = Field(default=None, ge=0, le=1)
    mean_score: Decimal | None = Field(default=None, ge=-1, le=1)
    agreement: Decimal | None = Field(default=None, ge=0, le=1)
    mean_signal_confidence: Decimal | None = Field(default=None, ge=0, le=1)


class SentimentSnapshot(SentimentContract):
    snapshot_id: UUID
    target: InstrumentRef
    status: AnalysisStatus
    as_of: datetime
    current: WindowMetrics
    previous: WindowMetrics
    volume_change: Decimal | None = None
    confidence: Decimal | None = Field(default=None, ge=0, le=1)
    co_mentions: tuple[InstrumentRef, ...] = ()
    warnings: tuple[str, ...] = ()
    lexicon_version: str


class AggregateSentimentOutput(SentimentContract):
    snapshot: SentimentSnapshot


class Narrative(SentimentContract):
    narrative_id: UUID
    topic: str
    method: Literal["taxonomy", "ngram"]
    sentiment: SentimentLabel
    weighted_share: Decimal = Field(ge=0, le=1)
    mention_count: int = Field(ge=1)
    confidence: Decimal = Field(ge=0, le=1)
    discussion_ids: tuple[UUID, ...]
    providers: tuple[str, ...]
    observation_timestamps: tuple[datetime, ...]


class TrendBucket(SentimentContract):
    day: datetime
    mention_count: int = Field(ge=0)
    mean_score: Decimal | None = Field(default=None, ge=-1, le=1)


class SentimentTrend(SentimentContract):
    target: InstrumentRef
    status: AnalysisStatus
    direction: Literal["improving", "stable", "deteriorating", "insufficient"]
    slope: Decimal | None = None
    acceleration: Decimal | None = None
    buckets: tuple[TrendBucket, ...]


class SentimentShift(SentimentContract):
    target: InstrumentRef
    status: AnalysisStatus
    shift_score: Decimal | None = Field(default=None, ge=-1, le=1)
    sentiment_component: Decimal | None = Field(default=None, ge=-1, le=1)
    volume_component: Decimal | None = Field(default=None, ge=-1, le=1)
    description: str


class SentimentAnalysisInput(SentimentContract):
    query: str = Field(min_length=1, max_length=200)
    exchange: str | None = Field(default=None, min_length=1, max_length=20)
    as_of: datetime | None = None
    window_days: int = Field(default=7, ge=1, le=90)
    limit: int = Field(default=500, ge=1, le=1_000)


class CollectDiscussionsInput(SentimentContract):
    target: InstrumentRef
    as_of: datetime | None = None
    window_days: int = Field(default=7, ge=1, le=90)
    limit: int = Field(default=500, ge=1, le=1_000)


class CollectedDiscussions(SentimentContract):
    target: InstrumentRef
    previous_start: datetime
    current_start: datetime
    end: datetime
    discussions: tuple[Discussion, ...]


class SpamRemovalInput(SentimentContract):
    discussions: tuple[Discussion, ...]


class SpamRemovalOutput(SentimentContract):
    retained: tuple[Discussion, ...]
    decisions: tuple[SpamDecision, ...]


class CompanyDetectionInput(SentimentContract):
    target: InstrumentRef
    catalog: tuple[InstrumentRef, ...]
    discussions: tuple[Discussion, ...]


class CompanyDetectionOutput(SentimentContract):
    target: InstrumentRef
    discussions: tuple[DetectedDiscussion, ...]
    relevant: tuple[DetectedDiscussion, ...]
    co_mentions: tuple[InstrumentRef, ...]


class SourceWeightInput(SentimentContract):
    discussions: tuple[DetectedDiscussion, ...]


class SourceWeightOutput(SentimentContract):
    observations: tuple[WeightedObservation, ...]


class AggregateSentimentInput(SentimentContract):
    target: InstrumentRef
    observations: tuple[WeightedObservation, ...]
    previous_start: datetime
    current_start: datetime
    end: datetime
    co_mentions: tuple[InstrumentRef, ...] = ()


class NarrativeExtractionInput(SentimentContract):
    target: InstrumentRef
    observations: tuple[WeightedObservation, ...]
    current_start: datetime
    end: datetime


class NarrativeList(SentimentContract):
    target: InstrumentRef
    status: AnalysisStatus
    narratives: tuple[Narrative, ...]


class TrendDetectionInput(SentimentContract):
    target: InstrumentRef
    observations: tuple[WeightedObservation, ...]
    start: datetime
    end: datetime


class ShiftDetectionInput(SentimentContract):
    snapshot: SentimentSnapshot


class PublicSentimentAnalysis(SentimentContract):
    snapshot: SentimentSnapshot
    narratives: NarrativeList
    trend: SentimentTrend
    shift: SentimentShift
