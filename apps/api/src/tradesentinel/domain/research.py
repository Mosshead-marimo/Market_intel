from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator


class ResearchContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class TimestampBasis(StrEnum):
    PUBLISHED = "published"
    RETRIEVED = "retrieved"


class ResearchEventType(StrEnum):
    EARNINGS = "earnings"
    GUIDANCE = "guidance"
    DIVIDEND = "dividend"
    MERGER_ACQUISITION = "merger_acquisition"
    LEADERSHIP = "leadership"
    PRODUCT = "product"
    PARTNERSHIP = "partnership"
    FINANCING = "financing"
    REGULATORY_LEGAL = "regulatory_legal"
    OPERATIONS = "operations"
    OTHER = "other"


class ConfidenceBasis(StrEnum):
    STRONG_TITLE = "strong_title_phrase"
    TITLE = "title_rule"
    SUMMARY = "summary_rule"
    DOCUMENT = "document_rule"


class ResearchSource(ResearchContract):
    source_id: str = Field(min_length=1)
    provider_source_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: AnyHttpUrl
    published_at: datetime | None = None
    retrieved_at: datetime
    timestamp: datetime
    timestamp_basis: TimestampBasis
    summary: str | None = None
    document_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    license: str = "unknown"
    freshness: str = "unknown"
    untrusted: Literal[True] = True

    @model_validator(mode="after")
    def validate_timestamp(self) -> ResearchSource:
        if self.timestamp_basis == TimestampBasis.PUBLISHED:
            if self.published_at is None or self.timestamp != self.published_at:
                raise ValueError("published timestamp basis requires the published timestamp")
        elif self.timestamp != self.retrieved_at:
            raise ValueError("retrieved timestamp basis requires the retrieval timestamp")
        return self


class NewsSearchInput(ResearchContract):
    query: str = Field(min_length=1, max_length=500)
    start: datetime | None = None
    end: datetime | None = None
    limit: int | None = Field(default=None, ge=1, le=100)

    @model_validator(mode="after")
    def validate_range(self) -> NewsSearchInput:
        if self.start is not None and self.end is not None and self.start >= self.end:
            raise ValueError("start must be before end")
        return self


class NewsSearchOutput(ResearchContract):
    query: str
    sources: tuple[ResearchSource, ...]


class NewsDeduplicateInput(ResearchContract):
    query: str = Field(min_length=1, max_length=500)
    sources: tuple[ResearchSource, ...]


class DuplicateGroup(ResearchContract):
    representative_source_id: str
    duplicate_source_ids: tuple[str, ...]
    reason: Literal["provider_source", "canonical_url", "document_hash", "title_day"]


class NewsDeduplicateOutput(ResearchContract):
    query: str
    sources: tuple[ResearchSource, ...]
    duplicate_groups: tuple[DuplicateGroup, ...]
    input_count: int = Field(ge=0)
    unique_count: int = Field(ge=0)


class EventExtractionInput(ResearchContract):
    query: str = Field(min_length=1, max_length=500)
    sources: tuple[ResearchSource, ...]


class ResearchClaim(ResearchContract):
    claim_id: UUID
    event_id: UUID
    text: str = Field(min_length=1)
    source: ResearchSource
    provider: str = Field(min_length=1)
    timestamp: datetime
    timestamp_basis: TimestampBasis
    confidence: float = Field(ge=0, le=1)
    confidence_basis: ConfidenceBasis
    extraction_version: str = Field(min_length=1)
    evidence_excerpt: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_evidence_timestamp(self) -> ResearchClaim:
        if (
            self.timestamp != self.source.timestamp
            or self.timestamp_basis != self.source.timestamp_basis
        ):
            raise ValueError("claim timestamp must match its source evidence timestamp")
        if self.provider != self.source.provider:
            raise ValueError("claim provider must match its source provider")
        return self


class ResearchEvent(ResearchContract):
    event_id: UUID
    query: str
    event_type: ResearchEventType
    headline: str = Field(min_length=1)
    observed_at: datetime
    timestamp_basis: TimestampBasis
    confidence: float = Field(ge=0, le=1)
    extraction_version: str = Field(min_length=1)
    claims: tuple[ResearchClaim, ...] = Field(min_length=1)
    source_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_claim_sources(self) -> ResearchEvent:
        claim_sources = tuple(dict.fromkeys(claim.source.source_id for claim in self.claims))
        if self.source_ids != claim_sources:
            raise ValueError("event source identifiers must match claim evidence")
        if any(claim.event_id != self.event_id for claim in self.claims):
            raise ValueError("event claims must reference their containing event")
        return self


class EventExtractionOutput(ResearchContract):
    query: str
    events: tuple[ResearchEvent, ...]
    sources: tuple[ResearchSource, ...]
    unmatched_source_ids: tuple[str, ...]
    document_failures: tuple[str, ...] = ()


class ResearchTimelineInput(ResearchContract):
    query: str = Field(min_length=1, max_length=500)
    events: tuple[ResearchEvent, ...]


class ResearchTimelineOutput(ResearchContract):
    query: str
    events: tuple[ResearchEvent, ...]


class ResearchEvidenceInput(ResearchContract):
    event_id: UUID


class ResearchEvidenceOutput(ResearchContract):
    event: ResearchEvent
    sources: tuple[ResearchSource, ...]
    claims: tuple[ResearchClaim, ...]

    @model_validator(mode="after")
    def validate_provenance(self) -> ResearchEvidenceOutput:
        if self.claims != self.event.claims:
            raise ValueError("evidence claims must match the persisted event")
        if tuple(source.source_id for source in self.sources) != self.event.source_ids:
            raise ValueError("evidence sources must match the persisted event")
        return self


class ResearchReportInput(ResearchContract):
    query: str = Field(min_length=1, max_length=500)
    events: tuple[ResearchEvent, ...]
    sources: tuple[ResearchSource, ...]
    duplicate_groups: tuple[DuplicateGroup, ...] = ()
    input_count: int = Field(default=0, ge=0)
    unmatched_source_ids: tuple[str, ...] = ()
    document_failures: tuple[str, ...] = ()


class ResearchCoverage(ResearchContract):
    source_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    event_count: int = Field(ge=0)
    claim_count: int = Field(ge=0)
    unmatched_count: int = Field(ge=0)
    document_failure_count: int = Field(ge=0)


class ResearchReportOutput(ResearchContract):
    query: str
    status: Literal["completed", "partial", "empty"]
    coverage: ResearchCoverage
    events: tuple[ResearchEvent, ...]
    sources: tuple[ResearchSource, ...]
    duplicate_groups: tuple[DuplicateGroup, ...]
    warnings: tuple[str, ...] = ()
