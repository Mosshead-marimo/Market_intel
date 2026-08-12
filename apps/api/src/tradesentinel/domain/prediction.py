from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tradesentinel.domain.instruments import InstrumentRef


class PredictionModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Direction(StrEnum):
    RISE = "rise"
    SIDEWAYS = "sideways"
    DECLINE = "decline"
    UNCERTAIN = "uncertain"


class FeatureGroup(StrEnum):
    MARKET = "market"
    TECHNICAL = "technical"
    SENTIMENT = "sentiment"
    RESEARCH = "research"
    FUNDAMENTALS = "fundamentals"


class PointInTimeValue(PredictionModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_.]*$")
    value: Decimal | str | None
    observed_at: datetime
    known_at: datetime
    source_version: str = Field(min_length=1, max_length=120)

    @model_validator(mode="after")
    def validate_time(self) -> PointInTimeValue:
        if self.known_at < self.observed_at:
            raise ValueError("known_at cannot precede observed_at")
        return self


class ObservationBatch(PredictionModel):
    idempotency_key: str = Field(min_length=8, max_length=160)
    instrument: InstrumentRef
    group: FeatureGroup
    observations: tuple[PointInTimeValue, ...] = Field(min_length=1, max_length=10_000)


class ObservationReceipt(PredictionModel):
    batch_id: UUID
    accepted: int
    duplicate: bool = False


class FeatureValue(PredictionModel):
    name: str
    value: Decimal | None
    known_at: datetime
    source_versions: tuple[str, ...]


class FeatureVector(PredictionModel):
    vector_id: UUID = Field(default_factory=uuid4)
    instrument: InstrumentRef
    cutoff: datetime
    schema_version: str = "prediction-features-v1"
    profile: tuple[FeatureGroup, ...]
    values: tuple[FeatureValue, ...]
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_point_in_time(self) -> FeatureVector:
        if any(item.known_at > self.cutoff for item in self.values):
            raise ValueError("feature value was not known at the cutoff")
        names = [item.name for item in self.values]
        if names != sorted(names) or len(names) != len(set(names)):
            raise ValueError("feature names must be unique and ordered")
        required = {FeatureGroup.MARKET, FeatureGroup.TECHNICAL}
        if not required.issubset(self.profile):
            raise ValueError("market and technical feature groups are required")
        return self


class LabelDefinition(PredictionModel):
    version: str = "direction-volatility-v1"
    horizon_sessions: Literal[5, 20]
    volatility_multiplier: Decimal = Decimal("0.5")
    minimum_threshold: Decimal


class TrainingLabel(PredictionModel):
    vector_id: UUID
    direction: Literal[Direction.RISE, Direction.SIDEWAYS, Direction.DECLINE]
    forward_return: Decimal
    threshold: Decimal
    outcome_at: datetime
    definition: LabelDefinition


class DatasetBuildRequest(PredictionModel):
    idempotency_key: str = Field(min_length=8, max_length=160)
    horizon_sessions: Literal[5, 20]
    profile: tuple[FeatureGroup, ...] = (FeatureGroup.MARKET, FeatureGroup.TECHNICAL)
    cutoff_start: datetime
    cutoff_end: datetime
    universe: str = Field(default="all-equities", min_length=1, max_length=120)


class DatasetVersion(PredictionModel):
    dataset_version: str
    feature_schema_version: str
    label_version: str
    profile: tuple[FeatureGroup, ...]
    horizon_sessions: Literal[5, 20]
    universe: str
    sample_count: int = Field(ge=0)
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


class PredictionJob(PredictionModel):
    job_id: UUID = Field(default_factory=uuid4)
    kind: Literal["dataset", "training", "evaluation"]
    status: JobStatus = JobStatus.QUEUED
    idempotency_key: str
    payload: dict[str, object]
    attempts: int = Field(default=0, ge=0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    error_code: str | None = None


class TrainingRequest(PredictionModel):
    idempotency_key: str = Field(min_length=8, max_length=160)
    dataset_version: str
    random_seed: int = 42


class JobReference(PredictionModel):
    job_id: UUID


class JobExecutionRequest(PredictionModel):
    job_id: UUID
    kind: str | None = None


class ModelReference(PredictionModel):
    model_version: str


class PredictionReference(PredictionModel):
    prediction_id: UUID


class EvaluationRequest(PredictionModel):
    idempotency_key: str = Field(min_length=8, max_length=160)


class EmptyPredictionInput(PredictionModel):
    pass


class ModelMetrics(PredictionModel):
    multiclass_brier: Decimal
    log_loss: Decimal
    expected_calibration_error: Decimal
    range_coverage: Decimal
    total_samples: int
    class_samples: dict[str, int]
    leakage_checks_passed: bool


class ModelVersion(PredictionModel):
    model_version: str
    dataset_version: str
    feature_schema_version: str
    profile: tuple[FeatureGroup, ...]
    horizon_sessions: Literal[5, 20]
    asset_type: str
    universe: str
    family: Literal["logistic_regression", "hist_gradient_boosting"]
    calibration_version: str
    preprocessing_version: str
    training_code_version: str
    artifact_schema_version: str
    artifact_key: str
    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    artifact_size: int = Field(gt=0)
    library_versions: dict[str, str]
    trusted_types: tuple[str, ...]
    metrics: ModelMetrics
    active: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ModelVersionList(PredictionModel):
    items: tuple[ModelVersion, ...]


class ActivationRequest(PredictionModel):
    model_version: str


class ProbabilitySet(PredictionModel):
    rise: Decimal = Field(ge=0, le=1)
    sideways: Decimal = Field(ge=0, le=1)
    decline: Decimal = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_sum(self) -> ProbabilitySet:
        if abs(self.rise + self.sideways + self.decline - Decimal(1)) > Decimal("0.000001"):
            raise ValueError("probabilities must sum to one")
        return self


class NumericRange(PredictionModel):
    low: Decimal
    high: Decimal

    @model_validator(mode="after")
    def validate_order(self) -> NumericRange:
        if self.low > self.high:
            raise ValueError("range low cannot exceed high")
        return self


class Scenario(PredictionModel):
    name: Literal["bear", "base", "bull"]
    probability: Decimal = Field(ge=0, le=1)
    return_range: NumericRange
    price_range: NumericRange
    representative_return: Decimal
    label: str = "Model-implied scenario; not a price target"


class PredictionRequest(PredictionModel):
    instrument: InstrumentRef
    cutoff: datetime
    horizon_sessions: Literal[5, 20]
    feature_profile: tuple[FeatureGroup, ...] = (
        FeatureGroup.MARKET,
        FeatureGroup.TECHNICAL,
    )
    cutoff_adjusted_close: Decimal = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    sector: str | None = Field(default=None, min_length=1, max_length=120)
    sector_known_at: datetime | None = None
    sector_source: str | None = Field(default=None, min_length=1, max_length=160)

    @model_validator(mode="after")
    def validate_sector_provenance(self) -> PredictionRequest:
        supplied = (self.sector, self.sector_known_at, self.sector_source)
        if any(value is not None for value in supplied) and not all(
            value is not None for value in supplied
        ):
            raise ValueError("sector, sector_known_at, and sector_source must be supplied together")
        if self.sector_known_at is not None and self.sector_known_at > self.cutoff:
            raise ValueError("sector metadata must be known at the prediction cutoff")
        return self


class PredictionResult(PredictionModel):
    contract_version: str = "prediction-result-v2"
    prediction_id: UUID = Field(default_factory=uuid4)
    instrument: InstrumentRef
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data_cutoff: datetime
    horizon_sessions: Literal[5, 20]
    label_threshold: Decimal = Field(gt=0)
    direction: Direction
    probabilities: ProbabilitySet
    confidence: Decimal = Field(ge=0, le=1)
    confidence_version: str = "entropy-v1"
    cutoff_adjusted_close: Decimal
    currency: str
    modeled_return_range: NumericRange
    modeled_price_range: NumericRange
    scenarios: tuple[Scenario, Scenario, Scenario]
    model_version: str
    dataset_version: str
    feature_schema_version: str
    feature_profile: tuple[FeatureGroup, ...]
    feature_fingerprint: str
    label_version: str
    preprocessing_version: str
    calibration_version: str
    scenario_version: str = "quantile-scenarios-v1"
    training_code_version: str
    artifact_version: str
    market_key: str
    sector: str | None = None
    sector_known_at: datetime | None = None
    sector_source: str | None = None
    warnings: tuple[str, ...] = ()
    limitations: tuple[str, ...] = (
        "Probabilities describe a historical statistical model, not certainty.",
        "Scenario ranges are not price targets or recommendations.",
    )

    @model_validator(mode="before")
    @classmethod
    def derive_market_for_legacy_records(cls, value: object) -> object:
        if isinstance(value, dict) and not value.get("market_key"):
            instrument = value.get("instrument")
            if isinstance(instrument, dict):
                asset_type = instrument.get("asset_type")
                exchange = instrument.get("exchange")
                if asset_type and exchange:
                    return value | {"market_key": f"{asset_type}:{exchange}"}
        return value


class PredictionOutcome(PredictionModel):
    prediction_id: UUID
    evaluated_at: datetime
    evaluation_data_cutoff: datetime
    realized_return: Decimal
    realized_adjusted_close: Decimal = Field(gt=0)
    realized_direction: Literal[Direction.RISE, Direction.SIDEWAYS, Direction.DECLINE]
    brier_score: Decimal
    log_loss: Decimal
    within_modeled_range: bool
    within_modeled_price_range: bool
    provider: str
    source_id: str
    observed_at: datetime
    retrieved_at: datetime
    market_key: str
    sector: str | None = None
    model_version: str
    horizon_sessions: Literal[5, 20]
    predicted_direction: Direction
    evaluation_version: str = "prediction-evaluation-v2"


class EvaluationState(StrEnum):
    SCHEDULED = "scheduled"
    WAITING = "waiting"
    COLLECTING = "collecting"
    EVALUATED = "evaluated"
    RETRYING = "retrying"
    OVERDUE = "overdue"


class EvaluationSchedule(PredictionModel):
    schedule_id: UUID = Field(default_factory=uuid4)
    prediction_id: UUID
    idempotency_key: str
    model_version: str
    dataset_version: str
    horizon_sessions: Literal[5, 20]
    market_key: str
    sector: str | None = None
    expected_maturity_at: datetime
    next_check_at: datetime
    state: EvaluationState = EvaluationState.SCHEDULED
    attempts: int = Field(default=0, ge=0)
    last_error_code: str | None = None
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    schedule_version: str = "prediction-evaluation-schedule-v1"


class EvaluationAttempt(PredictionModel):
    attempt_id: UUID = Field(default_factory=uuid4)
    schedule_id: UUID
    prediction_id: UUID
    started_at: datetime
    completed_at: datetime
    state: EvaluationState
    error_code: str | None = None
    provider: str | None = None
    attempt_version: str = "prediction-evaluation-attempt-v1"


class EvaluationScheduleList(PredictionModel):
    items: tuple[EvaluationSchedule, ...]


class PredictionEvaluation(PredictionModel):
    prediction: PredictionResult
    schedule: EvaluationSchedule
    outcome: PredictionOutcome | None = None


class PerformanceFilter(PredictionModel):
    model_version: str | None = None
    horizon_sessions: Literal[5, 20] | None = None
    asset_type: str | None = None
    exchange: str | None = None
    sector: str | None = None
    start: datetime | None = None
    end: datetime | None = None

    @model_validator(mode="after")
    def validate_range(self) -> PerformanceFilter:
        if self.start is not None and self.end is not None and self.start >= self.end:
            raise ValueError("performance start must precede end")
        return self


class ConfusionMatrix(PredictionModel):
    predicted_labels: tuple[str, ...] = ("rise", "sideways", "decline", "uncertain")
    actual_labels: tuple[str, ...] = ("rise", "sideways", "decline")
    counts: tuple[tuple[int, int, int], ...]


class CalibrationBin(PredictionModel):
    class_name: Literal["rise", "sideways", "decline"]
    lower_bound: Decimal
    upper_bound: Decimal
    samples: int = Field(ge=0)
    mean_probability: Decimal | None = None
    observed_frequency: Decimal | None = None


class PerformanceMetrics(PredictionModel):
    sample_count: int = Field(ge=0)
    directional_calls: int = Field(ge=0)
    directional_coverage: Decimal | None = Field(default=None, ge=0, le=1)
    directional_accuracy: Decimal | None = Field(default=None, ge=0, le=1)
    multiclass_brier: Decimal | None = Field(default=None, ge=0)
    log_loss: Decimal | None = Field(default=None, ge=0)
    expected_calibration_error: Decimal | None = Field(default=None, ge=0, le=1)
    return_range_accuracy: Decimal | None = Field(default=None, ge=0, le=1)
    price_range_accuracy: Decimal | None = Field(default=None, ge=0, le=1)
    normalized_interval_width: Decimal | None = Field(default=None, ge=0)


class CohortPerformance(PredictionModel):
    dimension: Literal["overall", "model", "market", "sector", "horizon", "calendar", "count"]
    key: str
    metrics: PerformanceMetrics


class ModelPerformanceReport(PredictionModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data_cutoff: datetime | None
    metrics_version: str = "prediction-performance-v1"
    filters: PerformanceFilter
    overall: PerformanceMetrics
    confusion_matrix: ConfusionMatrix
    calibration: tuple[CalibrationBin, ...]
    cohorts: tuple[CohortPerformance, ...]
    scheduled: int = Field(ge=0)
    waiting: int = Field(ge=0)
    retrying: int = Field(ge=0)
    overdue: int = Field(ge=0)


class PerformanceRebuildResult(PredictionModel):
    outcomes_processed: int = Field(ge=0)
    aggregates_written: int = Field(ge=0)
    metrics_version: str = "prediction-performance-v1"


class PaginatedPredictions(PredictionModel):
    items: tuple[PredictionResult, ...]
    next_cursor: str | None = None


Observation = Annotated[ObservationBatch, Field(discriminator=None)]
