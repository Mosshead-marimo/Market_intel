from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, select, update
from sqlalchemy.orm import Mapped, mapped_column

from tradesentinel.domain.prediction import (
    DatasetVersion,
    EvaluationAttempt,
    EvaluationSchedule,
    EvaluationState,
    FeatureVector,
    ModelVersion,
    ObservationBatch,
    ObservationReceipt,
    PredictionJob,
    PredictionOutcome,
    PredictionResult,
    TrainingLabel,
)
from tradesentinel.platform.persistence import Base, PersistenceResources


@dataclass(frozen=True)
class PredictionOutboxEvent:
    event_id: UUID
    job_id: UUID
    event_name: str
    payload: dict[str, Any]
    created_at: datetime


class ObservationRecord(Base):
    __tablename__ = "feature_observations"
    __table_args__ = ({"schema": "prediction"},)
    idempotency_key: Mapped[str] = mapped_column(String(160), primary_key=True)
    batch_id: Mapped[UUID]
    instrument_id: Mapped[UUID]
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DatasetRecord(Base):
    __tablename__ = "dataset_versions"
    __table_args__ = ({"schema": "prediction"},)
    dataset_version: Mapped[str] = mapped_column(String(160), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class FeatureVectorRecord(Base):
    __tablename__ = "feature_vectors"
    __table_args__ = ({"schema": "prediction"},)
    vector_id: Mapped[UUID] = mapped_column(primary_key=True)
    dataset_version: Mapped[str] = mapped_column(String(160))
    instrument_id: Mapped[UUID]
    cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class LabelRecord(Base):
    __tablename__ = "labels"
    __table_args__ = ({"schema": "prediction"},)
    vector_id: Mapped[UUID] = mapped_column(primary_key=True)
    definition_version: Mapped[str] = mapped_column(String(120))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class ModelRecord(Base):
    __tablename__ = "model_versions"
    __table_args__ = ({"schema": "prediction"},)
    model_version: Mapped[str] = mapped_column(String(160), primary_key=True)
    horizon_sessions: Mapped[int] = mapped_column(Integer)
    asset_type: Mapped[str] = mapped_column(String(80))
    universe: Mapped[str] = mapped_column(String(120))
    profile_key: Mapped[str] = mapped_column(String(240))
    active: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ModelActivationRecord(Base):
    __tablename__ = "model_activations"
    __table_args__ = ({"schema": "prediction"},)
    activation_id: Mapped[UUID] = mapped_column(primary_key=True)
    model_version: Mapped[str] = mapped_column(String(160))
    activated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    activated_by: Mapped[str] = mapped_column(String(160))


class ModelMetricRecord(Base):
    __tablename__ = "model_metrics"
    __table_args__ = ({"schema": "prediction"},)
    model_version: Mapped[str] = mapped_column(String(160), primary_key=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON)


class PredictionRecord(Base):
    __tablename__ = "predictions"
    __table_args__ = ({"schema": "prediction"},)
    prediction_id: Mapped[UUID] = mapped_column(primary_key=True)
    instrument_id: Mapped[UUID]
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class PredictionFeatureRecord(Base):
    __tablename__ = "prediction_features"
    __table_args__ = ({"schema": "prediction"},)
    prediction_id: Mapped[UUID] = mapped_column(primary_key=True)
    feature_fingerprint: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class PredictionScenarioRecord(Base):
    __tablename__ = "prediction_scenarios"
    __table_args__ = ({"schema": "prediction"},)
    prediction_id: Mapped[UUID] = mapped_column(primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class OutcomeRecord(Base):
    __tablename__ = "prediction_outcomes"
    __table_args__ = ({"schema": "prediction"},)
    prediction_id: Mapped[UUID] = mapped_column(primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvaluationScheduleRecord(Base):
    __tablename__ = "evaluation_schedules"
    __table_args__ = ({"schema": "prediction"},)
    schedule_id: Mapped[UUID] = mapped_column(primary_key=True)
    prediction_id: Mapped[UUID] = mapped_column(unique=True, index=True)
    state: Mapped[str] = mapped_column(String(30), index=True)
    next_check_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    lease_owner: Mapped[str | None] = mapped_column(String(160))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class EvaluationAttemptRecord(Base):
    __tablename__ = "evaluation_attempts"
    __table_args__ = ({"schema": "prediction"},)
    attempt_id: Mapped[UUID] = mapped_column(primary_key=True)
    schedule_id: Mapped[UUID] = mapped_column(index=True)
    prediction_id: Mapped[UUID] = mapped_column(index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class PerformanceAggregateRecord(Base):
    __tablename__ = "performance_aggregates"
    __table_args__ = ({"schema": "prediction"},)
    aggregate_key: Mapped[str] = mapped_column(String(240), primary_key=True)
    metrics_version: Mapped[str] = mapped_column(String(120))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class JobRecord(Base):
    __tablename__ = "jobs"
    __table_args__ = ({"schema": "prediction"},)
    job_id: Mapped[UUID] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True)
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40))
    attempts: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(120))
    lease_owner: Mapped[str | None] = mapped_column(String(160))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PredictionOutboxRecord(Base):
    __tablename__ = "outbox"
    __table_args__ = ({"schema": "prediction"},)
    event_id: Mapped[UUID] = mapped_column(primary_key=True)
    job_id: Mapped[UUID]
    event_name: Mapped[str] = mapped_column(String(160))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PredictionRepository(ABC):
    @abstractmethod
    async def ingest(self, batch: ObservationBatch) -> ObservationReceipt: ...

    @abstractmethod
    async def observations(self) -> tuple[ObservationBatch, ...]: ...

    @abstractmethod
    async def save_dataset(self, dataset: DatasetVersion) -> None: ...

    @abstractmethod
    async def get_dataset(self, version: str) -> DatasetVersion | None: ...

    @abstractmethod
    async def save_samples(
        self,
        dataset_version: str,
        samples: tuple[tuple[FeatureVector, TrainingLabel], ...],
    ) -> None: ...

    @abstractmethod
    async def samples(
        self, dataset_version: str
    ) -> tuple[tuple[FeatureVector, TrainingLabel], ...]: ...

    @abstractmethod
    async def save_model(self, model: ModelVersion) -> None: ...

    @abstractmethod
    async def models(self) -> tuple[ModelVersion, ...]: ...

    @abstractmethod
    async def activate(self, version: str) -> ModelVersion | None: ...

    @abstractmethod
    async def active_model(
        self, horizon: int, asset_type: str, universe: str, profile_key: str
    ) -> ModelVersion | None: ...

    @abstractmethod
    async def save_prediction(self, prediction: PredictionResult) -> None: ...

    @abstractmethod
    async def prediction(self, prediction_id: UUID) -> PredictionResult | None: ...

    @abstractmethod
    async def predictions(self) -> tuple[PredictionResult, ...]: ...

    @abstractmethod
    async def save_outcome(self, outcome: PredictionOutcome) -> None: ...

    @abstractmethod
    async def outcome(self, prediction_id: UUID) -> PredictionOutcome | None: ...

    @abstractmethod
    async def outcomes(self) -> tuple[PredictionOutcome, ...]: ...

    @abstractmethod
    async def schedules(self) -> tuple[EvaluationSchedule, ...]: ...

    @abstractmethod
    async def due_schedules(self, now: datetime) -> tuple[EvaluationSchedule, ...]: ...

    @abstractmethod
    async def claim_schedule(self, schedule_id: UUID) -> EvaluationSchedule | None: ...

    @abstractmethod
    async def update_schedule(self, schedule: EvaluationSchedule) -> None: ...

    @abstractmethod
    async def save_evaluation_attempt(self, attempt: EvaluationAttempt) -> None: ...

    @abstractmethod
    async def replace_performance_aggregates(
        self, aggregates: dict[str, dict[str, Any]]
    ) -> None: ...

    @abstractmethod
    async def enqueue(self, job: PredictionJob) -> PredictionJob: ...

    @abstractmethod
    async def job(self, job_id: UUID) -> PredictionJob | None: ...

    @abstractmethod
    async def queued_jobs(self) -> tuple[PredictionJob, ...]: ...

    @abstractmethod
    async def update_job(self, job: PredictionJob) -> None: ...

    @abstractmethod
    async def claim_job(self, job_id: UUID) -> PredictionJob | None: ...

    @abstractmethod
    async def pending_outbox(self) -> tuple[PredictionOutboxEvent, ...]: ...

    @abstractmethod
    async def mark_outbox_published(self, event_id: UUID) -> None: ...


class InMemoryPredictionRepository(PredictionRepository):
    def __init__(self) -> None:
        self.batches: dict[str, tuple[UUID, ObservationBatch]] = {}
        self.datasets: dict[str, DatasetVersion] = {}
        self.dataset_samples: dict[str, tuple[tuple[FeatureVector, TrainingLabel], ...]] = {}
        self.model_records: dict[str, ModelVersion] = {}
        self.prediction_records: dict[UUID, PredictionResult] = {}
        self.outcome_records: dict[UUID, PredictionOutcome] = {}
        self.evaluation_schedules: dict[UUID, EvaluationSchedule] = {}
        self.evaluation_attempts: dict[UUID, EvaluationAttempt] = {}
        self.performance_aggregates: dict[str, dict[str, Any]] = {}
        self.jobs: dict[UUID, PredictionJob] = {}
        self.outbox: dict[UUID, PredictionOutboxEvent] = {}
        self.leases: dict[UUID, datetime] = {}

    async def ingest(self, batch: ObservationBatch) -> ObservationReceipt:
        existing = self.batches.get(batch.idempotency_key)
        if existing is not None:
            return ObservationReceipt(batch_id=existing[0], accepted=0, duplicate=True)
        receipt = ObservationReceipt(
            batch_id=UUID(int=len(self.batches) + 1), accepted=len(batch.observations)
        )
        self.batches[batch.idempotency_key] = (receipt.batch_id, batch)
        return receipt

    async def observations(self) -> tuple[ObservationBatch, ...]:
        return tuple(item[1] for item in self.batches.values())

    async def save_dataset(self, dataset: DatasetVersion) -> None:
        self.datasets.setdefault(dataset.dataset_version, dataset)

    async def get_dataset(self, version: str) -> DatasetVersion | None:
        return self.datasets.get(version)

    async def save_samples(
        self,
        dataset_version: str,
        samples: tuple[tuple[FeatureVector, TrainingLabel], ...],
    ) -> None:
        self.dataset_samples.setdefault(dataset_version, samples)

    async def samples(
        self, dataset_version: str
    ) -> tuple[tuple[FeatureVector, TrainingLabel], ...]:
        return self.dataset_samples.get(dataset_version, ())

    async def save_model(self, model: ModelVersion) -> None:
        self.model_records.setdefault(model.model_version, model)

    async def models(self) -> tuple[ModelVersion, ...]:
        return tuple(sorted(self.model_records.values(), key=lambda item: item.model_version))

    async def activate(self, version: str) -> ModelVersion | None:
        selected = self.model_records.get(version)
        if selected is None:
            return None
        key = _model_key(selected)
        for name, model in tuple(self.model_records.items()):
            if _model_key(model) == key:
                self.model_records[name] = model.model_copy(update={"active": name == version})
        return self.model_records[version]

    async def active_model(
        self, horizon: int, asset_type: str, universe: str, profile_key: str
    ) -> ModelVersion | None:
        return next(
            (
                m
                for m in self.model_records.values()
                if m.active and _model_key(m) == (horizon, asset_type, universe, profile_key)
            ),
            None,
        )

    async def save_prediction(self, prediction: PredictionResult) -> None:
        self.prediction_records.setdefault(prediction.prediction_id, prediction)
        existing = next(
            (
                item
                for item in self.evaluation_schedules.values()
                if item.prediction_id == prediction.prediction_id
            ),
            None,
        )
        if existing is None:
            schedule = _evaluation_schedule(prediction)
            self.evaluation_schedules[schedule.schedule_id] = schedule

    async def prediction(self, prediction_id: UUID) -> PredictionResult | None:
        return self.prediction_records.get(prediction_id)

    async def predictions(self) -> tuple[PredictionResult, ...]:
        return tuple(
            sorted(
                self.prediction_records.values(), key=lambda item: item.generated_at, reverse=True
            )
        )

    async def save_outcome(self, outcome: PredictionOutcome) -> None:
        self.outcome_records.setdefault(outcome.prediction_id, outcome)

    async def outcome(self, prediction_id: UUID) -> PredictionOutcome | None:
        return self.outcome_records.get(prediction_id)

    async def outcomes(self) -> tuple[PredictionOutcome, ...]:
        return tuple(sorted(self.outcome_records.values(), key=lambda item: item.evaluated_at))

    async def schedules(self) -> tuple[EvaluationSchedule, ...]:
        return tuple(sorted(self.evaluation_schedules.values(), key=lambda item: item.created_at))

    async def due_schedules(self, now: datetime) -> tuple[EvaluationSchedule, ...]:
        return tuple(
            item
            for item in await self.schedules()
            if item.state != EvaluationState.EVALUATED
            and item.next_check_at <= now
            and (item.lease_expires_at is None or item.lease_expires_at <= now)
        )

    async def claim_schedule(self, schedule_id: UUID) -> EvaluationSchedule | None:
        item = self.evaluation_schedules.get(schedule_id)
        now = datetime.now(UTC)
        if (
            item is None
            or item.state == EvaluationState.EVALUATED
            or item.next_check_at > now
            or (item.lease_expires_at is not None and item.lease_expires_at > now)
        ):
            return None
        claimed = item.model_copy(
            update={
                "state": EvaluationState.COLLECTING,
                "attempts": item.attempts + 1,
                "lease_owner": "memory-worker",
                "lease_expires_at": now + timedelta(seconds=60),
                "updated_at": now,
            }
        )
        self.evaluation_schedules[schedule_id] = claimed
        return claimed

    async def update_schedule(self, schedule: EvaluationSchedule) -> None:
        self.evaluation_schedules[schedule.schedule_id] = schedule

    async def save_evaluation_attempt(self, attempt: EvaluationAttempt) -> None:
        self.evaluation_attempts.setdefault(attempt.attempt_id, attempt)

    async def replace_performance_aggregates(self, aggregates: dict[str, dict[str, Any]]) -> None:
        self.performance_aggregates = dict(aggregates)

    async def enqueue(self, job: PredictionJob) -> PredictionJob:
        existing = next(
            (j for j in self.jobs.values() if j.idempotency_key == job.idempotency_key), None
        )
        if existing is not None:
            return existing
        self.jobs[job.job_id] = job
        event = PredictionOutboxEvent(
            event_id=uuid4(),
            job_id=job.job_id,
            event_name="prediction.job.queued",
            payload={"job_id": str(job.job_id), "kind": job.kind},
            created_at=job.created_at,
        )
        self.outbox[event.event_id] = event
        return job

    async def job(self, job_id: UUID) -> PredictionJob | None:
        return self.jobs.get(job_id)

    async def queued_jobs(self) -> tuple[PredictionJob, ...]:
        now = datetime.now(UTC)
        return tuple(
            job
            for job in self.jobs.values()
            if job.status == "queued"
            or (job.status == "running" and self.leases.get(job.job_id, now) <= now)
        )

    async def update_job(self, job: PredictionJob) -> None:
        self.jobs[job.job_id] = job
        if job.status != "running":
            self.leases.pop(job.job_id, None)

    async def claim_job(self, job_id: UUID) -> PredictionJob | None:
        job = self.jobs.get(job_id)
        now = datetime.now(UTC)
        if job is None or (
            job.status != "queued"
            and not (job.status == "running" and self.leases.get(job_id, now) <= now)
        ):
            return None
        claimed = job.model_copy(
            update={
                "status": "running",
                "attempts": job.attempts + 1,
                "updated_at": now,
            }
        )
        self.jobs[job_id] = claimed
        self.leases[job_id] = now + timedelta(seconds=60)
        return claimed

    async def pending_outbox(self) -> tuple[PredictionOutboxEvent, ...]:
        return tuple(sorted(self.outbox.values(), key=lambda event: event.created_at))

    async def mark_outbox_published(self, event_id: UUID) -> None:
        self.outbox.pop(event_id, None)


class SqlPredictionRepository(PredictionRepository):
    def __init__(self, resources: PersistenceResources) -> None:
        self._sessions = resources.sessions
        self._lease_owner = str(uuid4())

    async def ingest(self, batch: ObservationBatch) -> ObservationReceipt:
        async with self._sessions.begin() as session:
            existing = await session.get(ObservationRecord, batch.idempotency_key)
            if existing:
                return ObservationReceipt(batch_id=existing.batch_id, accepted=0, duplicate=True)
            receipt = ObservationReceipt(batch_id=uuid4(), accepted=len(batch.observations))
            session.add(
                ObservationRecord(
                    idempotency_key=batch.idempotency_key,
                    batch_id=receipt.batch_id,
                    instrument_id=batch.instrument.instrument_id,
                    payload=batch.model_dump(mode="json"),
                    created_at=datetime.now(UTC),
                )
            )
            return receipt

    async def observations(self) -> tuple[ObservationBatch, ...]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(ObservationRecord).order_by(ObservationRecord.created_at)
                )
            ).all()
            return tuple(ObservationBatch.model_validate(row.payload) for row in rows)

    async def save_dataset(self, dataset: DatasetVersion) -> None:
        async with self._sessions.begin() as session:
            await session.merge(
                DatasetRecord(
                    dataset_version=dataset.dataset_version,
                    payload=dataset.model_dump(mode="json"),
                    created_at=dataset.created_at,
                )
            )

    async def get_dataset(self, version: str) -> DatasetVersion | None:
        async with self._sessions() as session:
            row = await session.get(DatasetRecord, version)
            return DatasetVersion.model_validate(row.payload) if row else None

    async def save_samples(
        self,
        dataset_version: str,
        samples: tuple[tuple[FeatureVector, TrainingLabel], ...],
    ) -> None:
        async with self._sessions.begin() as session:
            for vector, label in samples:
                await session.merge(
                    FeatureVectorRecord(
                        vector_id=vector.vector_id,
                        dataset_version=dataset_version,
                        instrument_id=vector.instrument.instrument_id,
                        cutoff=vector.cutoff,
                        fingerprint=vector.fingerprint,
                        payload=vector.model_dump(mode="json"),
                    )
                )
                await session.merge(
                    LabelRecord(
                        vector_id=vector.vector_id,
                        definition_version=label.definition.version,
                        payload=label.model_dump(mode="json"),
                    )
                )

    async def samples(
        self, dataset_version: str
    ) -> tuple[tuple[FeatureVector, TrainingLabel], ...]:
        async with self._sessions() as session:
            rows = (
                await session.execute(
                    select(FeatureVectorRecord, LabelRecord)
                    .join(LabelRecord, LabelRecord.vector_id == FeatureVectorRecord.vector_id)
                    .where(FeatureVectorRecord.dataset_version == dataset_version)
                    .order_by(FeatureVectorRecord.cutoff, FeatureVectorRecord.instrument_id)
                )
            ).all()
            return tuple(
                (
                    FeatureVector.model_validate(vector.payload),
                    TrainingLabel.model_validate(label.payload),
                )
                for vector, label in rows
            )

    async def save_model(self, model: ModelVersion) -> None:
        async with self._sessions.begin() as session:
            await session.merge(
                ModelRecord(
                    model_version=model.model_version,
                    horizon_sessions=model.horizon_sessions,
                    asset_type=model.asset_type,
                    universe=model.universe,
                    profile_key=_profile_key(model.profile),
                    active=model.active,
                    payload=model.model_dump(mode="json"),
                    created_at=model.created_at,
                )
            )
            await session.merge(
                ModelMetricRecord(
                    model_version=model.model_version,
                    metrics=model.metrics.model_dump(mode="json"),
                )
            )

    async def models(self) -> tuple[ModelVersion, ...]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(select(ModelRecord).order_by(ModelRecord.model_version))
            ).all()
            return tuple(
                ModelVersion.model_validate(row.payload | {"active": row.active}) for row in rows
            )

    async def activate(self, version: str) -> ModelVersion | None:
        async with self._sessions.begin() as session:
            selected = await session.get(ModelRecord, version)
            if selected is None:
                return None
            await session.execute(
                update(ModelRecord)
                .where(
                    ModelRecord.horizon_sessions == selected.horizon_sessions,
                    ModelRecord.asset_type == selected.asset_type,
                    ModelRecord.universe == selected.universe,
                    ModelRecord.profile_key == selected.profile_key,
                )
                .values(active=False)
            )
            selected.active = True
            payload = dict(selected.payload)
            payload["active"] = True
            selected.payload = payload
            session.add(
                ModelActivationRecord(
                    activation_id=uuid4(),
                    model_version=version,
                    activated_at=datetime.now(UTC),
                    activated_by="prediction-admin",
                )
            )
            return ModelVersion.model_validate(payload)

    async def active_model(
        self, horizon: int, asset_type: str, universe: str, profile_key: str
    ) -> ModelVersion | None:
        async with self._sessions() as session:
            row = await session.scalar(
                select(ModelRecord).where(
                    ModelRecord.horizon_sessions == horizon,
                    ModelRecord.asset_type == asset_type,
                    ModelRecord.universe == universe,
                    ModelRecord.profile_key == profile_key,
                    ModelRecord.active.is_(True),
                )
            )
            return ModelVersion.model_validate(row.payload | {"active": True}) if row else None

    async def save_prediction(self, prediction: PredictionResult) -> None:
        async with self._sessions.begin() as session:
            existing = await session.get(PredictionRecord, prediction.prediction_id)
            if existing is not None:
                return
            session.add(
                PredictionRecord(
                    prediction_id=prediction.prediction_id,
                    instrument_id=prediction.instrument.instrument_id,
                    generated_at=prediction.generated_at,
                    payload=prediction.model_dump(mode="json"),
                )
            )
            session.add(
                PredictionFeatureRecord(
                    prediction_id=prediction.prediction_id,
                    feature_fingerprint=prediction.feature_fingerprint,
                    payload={
                        "feature_schema_version": prediction.feature_schema_version,
                        "feature_profile": [item.value for item in prediction.feature_profile],
                        "dataset_version": prediction.dataset_version,
                    },
                )
            )
            session.add(
                PredictionScenarioRecord(
                    prediction_id=prediction.prediction_id,
                    payload={
                        "modeled_return_range": prediction.modeled_return_range.model_dump(
                            mode="json"
                        ),
                        "modeled_price_range": prediction.modeled_price_range.model_dump(
                            mode="json"
                        ),
                        "scenarios": [
                            item.model_dump(mode="json") for item in prediction.scenarios
                        ],
                    },
                )
            )
            schedule = _evaluation_schedule(prediction)
            session.add(
                EvaluationScheduleRecord(
                    schedule_id=schedule.schedule_id,
                    prediction_id=schedule.prediction_id,
                    state=schedule.state.value,
                    next_check_at=schedule.next_check_at,
                    lease_owner=None,
                    lease_expires_at=None,
                    payload=schedule.model_dump(mode="json"),
                )
            )

    async def prediction(self, prediction_id: UUID) -> PredictionResult | None:
        async with self._sessions() as session:
            row = await session.get(PredictionRecord, prediction_id)
            return PredictionResult.model_validate(row.payload) if row else None

    async def predictions(self) -> tuple[PredictionResult, ...]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(PredictionRecord).order_by(PredictionRecord.generated_at.desc())
                )
            ).all()
            return tuple(PredictionResult.model_validate(row.payload) for row in rows)

    async def save_outcome(self, outcome: PredictionOutcome) -> None:
        async with self._sessions.begin() as session:
            if await session.get(OutcomeRecord, outcome.prediction_id) is not None:
                return
            session.add(
                OutcomeRecord(
                    prediction_id=outcome.prediction_id,
                    payload=outcome.model_dump(mode="json"),
                    evaluated_at=outcome.evaluated_at,
                )
            )

    async def outcome(self, prediction_id: UUID) -> PredictionOutcome | None:
        async with self._sessions() as session:
            row = await session.get(OutcomeRecord, prediction_id)
            return PredictionOutcome.model_validate(row.payload) if row else None

    async def outcomes(self) -> tuple[PredictionOutcome, ...]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(select(OutcomeRecord).order_by(OutcomeRecord.evaluated_at))
            ).all()
            return tuple(PredictionOutcome.model_validate(row.payload) for row in rows)

    async def schedules(self) -> tuple[EvaluationSchedule, ...]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(EvaluationScheduleRecord).order_by(
                        EvaluationScheduleRecord.next_check_at
                    )
                )
            ).all()
            return tuple(EvaluationSchedule.model_validate(row.payload) for row in rows)

    async def due_schedules(self, now: datetime) -> tuple[EvaluationSchedule, ...]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(EvaluationScheduleRecord)
                    .where(
                        EvaluationScheduleRecord.state != EvaluationState.EVALUATED.value,
                        EvaluationScheduleRecord.next_check_at <= now,
                        (EvaluationScheduleRecord.lease_expires_at.is_(None))
                        | (EvaluationScheduleRecord.lease_expires_at <= now),
                    )
                    .order_by(EvaluationScheduleRecord.next_check_at)
                    .limit(100)
                )
            ).all()
            return tuple(EvaluationSchedule.model_validate(row.payload) for row in rows)

    async def claim_schedule(self, schedule_id: UUID) -> EvaluationSchedule | None:
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=60)
        async with self._sessions.begin() as session:
            row = await session.scalar(
                update(EvaluationScheduleRecord)
                .where(
                    EvaluationScheduleRecord.schedule_id == schedule_id,
                    EvaluationScheduleRecord.state != EvaluationState.EVALUATED.value,
                    EvaluationScheduleRecord.next_check_at <= now,
                    (EvaluationScheduleRecord.lease_expires_at.is_(None))
                    | (EvaluationScheduleRecord.lease_expires_at <= now),
                )
                .values(
                    state=EvaluationState.COLLECTING.value,
                    lease_owner=self._lease_owner,
                    lease_expires_at=expires,
                )
                .returning(EvaluationScheduleRecord)
            )
            if row is None:
                return None
            schedule = EvaluationSchedule.model_validate(row.payload).model_copy(
                update={
                    "state": EvaluationState.COLLECTING,
                    "attempts": EvaluationSchedule.model_validate(row.payload).attempts + 1,
                    "lease_owner": self._lease_owner,
                    "lease_expires_at": expires,
                    "updated_at": now,
                }
            )
            row.payload = schedule.model_dump(mode="json")
            return schedule

    async def update_schedule(self, schedule: EvaluationSchedule) -> None:
        async with self._sessions.begin() as session:
            await session.execute(
                update(EvaluationScheduleRecord)
                .where(EvaluationScheduleRecord.schedule_id == schedule.schedule_id)
                .values(
                    state=schedule.state.value,
                    next_check_at=schedule.next_check_at,
                    lease_owner=schedule.lease_owner,
                    lease_expires_at=schedule.lease_expires_at,
                    payload=schedule.model_dump(mode="json"),
                )
            )

    async def save_evaluation_attempt(self, attempt: EvaluationAttempt) -> None:
        async with self._sessions.begin() as session:
            session.add(
                EvaluationAttemptRecord(
                    attempt_id=attempt.attempt_id,
                    schedule_id=attempt.schedule_id,
                    prediction_id=attempt.prediction_id,
                    completed_at=attempt.completed_at,
                    payload=attempt.model_dump(mode="json"),
                )
            )

    async def replace_performance_aggregates(self, aggregates: dict[str, dict[str, Any]]) -> None:
        async with self._sessions.begin() as session:
            for key, payload in aggregates.items():
                await session.merge(
                    PerformanceAggregateRecord(
                        aggregate_key=key,
                        metrics_version="prediction-performance-v1",
                        updated_at=datetime.now(UTC),
                        payload=payload,
                    )
                )

    async def enqueue(self, job: PredictionJob) -> PredictionJob:
        async with self._sessions.begin() as session:
            row = await session.scalar(
                select(JobRecord).where(JobRecord.idempotency_key == job.idempotency_key)
            )
            if row:
                return _job(row)
            session.add(
                JobRecord(
                    job_id=job.job_id,
                    idempotency_key=job.idempotency_key,
                    kind=job.kind,
                    status=job.status,
                    attempts=job.attempts,
                    payload=job.payload,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                    error_code=job.error_code,
                    lease_owner=None,
                    lease_expires_at=None,
                )
            )
            session.add(
                PredictionOutboxRecord(
                    event_id=uuid4(),
                    job_id=job.job_id,
                    event_name="prediction.job.queued",
                    payload={"job_id": str(job.job_id), "kind": job.kind},
                    created_at=job.created_at,
                    published_at=None,
                )
            )
            return job

    async def job(self, job_id: UUID) -> PredictionJob | None:
        async with self._sessions() as session:
            row = await session.get(JobRecord, job_id)
            return _job(row) if row else None

    async def queued_jobs(self) -> tuple[PredictionJob, ...]:
        now = datetime.now(UTC)
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(JobRecord)
                    .where(
                        (JobRecord.status == "queued")
                        | ((JobRecord.status == "running") & (JobRecord.lease_expires_at <= now))
                    )
                    .order_by(JobRecord.created_at)
                )
            ).all()
            return tuple(_job(row) for row in rows)

    async def update_job(self, job: PredictionJob) -> None:
        async with self._sessions.begin() as session:
            await session.merge(
                JobRecord(
                    job_id=job.job_id,
                    idempotency_key=job.idempotency_key,
                    kind=job.kind,
                    status=job.status,
                    attempts=job.attempts,
                    payload=job.payload,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                    error_code=job.error_code,
                    lease_owner=None if job.status != "running" else self._lease_owner,
                    lease_expires_at=(
                        None
                        if job.status != "running"
                        else datetime.now(UTC) + timedelta(seconds=60)
                    ),
                )
            )

    async def claim_job(self, job_id: UUID) -> PredictionJob | None:
        now = datetime.now(UTC)
        lease_expires_at = now + timedelta(seconds=60)
        async with self._sessions.begin() as session:
            row = await session.scalar(
                update(JobRecord)
                .where(
                    JobRecord.job_id == job_id,
                    (JobRecord.status == "queued")
                    | ((JobRecord.status == "running") & (JobRecord.lease_expires_at <= now)),
                )
                .values(
                    status="running",
                    attempts=JobRecord.attempts + 1,
                    updated_at=now,
                    lease_owner=self._lease_owner,
                    lease_expires_at=lease_expires_at,
                )
                .returning(JobRecord)
            )
            return _job(row) if row else None

    async def pending_outbox(self) -> tuple[PredictionOutboxEvent, ...]:
        async with self._sessions() as session:
            rows = (
                await session.scalars(
                    select(PredictionOutboxRecord)
                    .where(PredictionOutboxRecord.published_at.is_(None))
                    .order_by(PredictionOutboxRecord.created_at)
                    .limit(100)
                )
            ).all()
            return tuple(
                PredictionOutboxEvent(
                    event_id=row.event_id,
                    job_id=row.job_id,
                    event_name=row.event_name,
                    payload=row.payload,
                    created_at=row.created_at,
                )
                for row in rows
            )

    async def mark_outbox_published(self, event_id: UUID) -> None:
        async with self._sessions.begin() as session:
            await session.execute(
                update(PredictionOutboxRecord)
                .where(
                    PredictionOutboxRecord.event_id == event_id,
                    PredictionOutboxRecord.published_at.is_(None),
                )
                .values(published_at=datetime.now(UTC))
            )


class PredictionRepositoryFactory:
    def __init__(self, resources: PersistenceResources) -> None:
        self.implementation: PredictionRepository = (
            SqlPredictionRepository(resources)
            if resources.backend == "postgres"
            else InMemoryPredictionRepository()
        )

    async def ingest(self, batch: ObservationBatch) -> ObservationReceipt:
        return await self.implementation.ingest(batch)

    async def observations(self) -> tuple[ObservationBatch, ...]:
        return await self.implementation.observations()

    async def save_dataset(self, dataset: DatasetVersion) -> None:
        await self.implementation.save_dataset(dataset)

    async def get_dataset(self, version: str) -> DatasetVersion | None:
        return await self.implementation.get_dataset(version)

    async def save_samples(
        self,
        dataset_version: str,
        samples: tuple[tuple[FeatureVector, TrainingLabel], ...],
    ) -> None:
        await self.implementation.save_samples(dataset_version, samples)

    async def samples(
        self, dataset_version: str
    ) -> tuple[tuple[FeatureVector, TrainingLabel], ...]:
        return await self.implementation.samples(dataset_version)

    async def save_model(self, model: ModelVersion) -> None:
        await self.implementation.save_model(model)

    async def models(self) -> tuple[ModelVersion, ...]:
        return await self.implementation.models()

    async def activate(self, version: str) -> ModelVersion | None:
        return await self.implementation.activate(version)

    async def active_model(
        self, horizon: int, asset_type: str, universe: str, profile_key: str
    ) -> ModelVersion | None:
        return await self.implementation.active_model(horizon, asset_type, universe, profile_key)

    async def save_prediction(self, prediction: PredictionResult) -> None:
        await self.implementation.save_prediction(prediction)

    async def prediction(self, prediction_id: UUID) -> PredictionResult | None:
        return await self.implementation.prediction(prediction_id)

    async def predictions(self) -> tuple[PredictionResult, ...]:
        return await self.implementation.predictions()

    async def save_outcome(self, outcome: PredictionOutcome) -> None:
        await self.implementation.save_outcome(outcome)

    async def outcome(self, prediction_id: UUID) -> PredictionOutcome | None:
        return await self.implementation.outcome(prediction_id)

    async def outcomes(self) -> tuple[PredictionOutcome, ...]:
        return await self.implementation.outcomes()

    async def schedules(self) -> tuple[EvaluationSchedule, ...]:
        return await self.implementation.schedules()

    async def due_schedules(self, now: datetime) -> tuple[EvaluationSchedule, ...]:
        return await self.implementation.due_schedules(now)

    async def claim_schedule(self, schedule_id: UUID) -> EvaluationSchedule | None:
        return await self.implementation.claim_schedule(schedule_id)

    async def update_schedule(self, schedule: EvaluationSchedule) -> None:
        await self.implementation.update_schedule(schedule)

    async def save_evaluation_attempt(self, attempt: EvaluationAttempt) -> None:
        await self.implementation.save_evaluation_attempt(attempt)

    async def replace_performance_aggregates(self, aggregates: dict[str, dict[str, Any]]) -> None:
        await self.implementation.replace_performance_aggregates(aggregates)

    async def enqueue(self, job: PredictionJob) -> PredictionJob:
        return await self.implementation.enqueue(job)

    async def job(self, job_id: UUID) -> PredictionJob | None:
        return await self.implementation.job(job_id)

    async def queued_jobs(self) -> tuple[PredictionJob, ...]:
        return await self.implementation.queued_jobs()

    async def update_job(self, job: PredictionJob) -> None:
        await self.implementation.update_job(job)

    async def claim_job(self, job_id: UUID) -> PredictionJob | None:
        return await self.implementation.claim_job(job_id)

    async def pending_outbox(self) -> tuple[PredictionOutboxEvent, ...]:
        return await self.implementation.pending_outbox()

    async def mark_outbox_published(self, event_id: UUID) -> None:
        await self.implementation.mark_outbox_published(event_id)


def _profile_key(profile: tuple[Any, ...]) -> str:
    return ",".join(sorted(str(item.value if hasattr(item, "value") else item) for item in profile))


def _evaluation_schedule(prediction: PredictionResult) -> EvaluationSchedule:
    calendar_days = (prediction.horizon_sessions * 7 + 4) // 5 + 2
    expected = prediction.data_cutoff + timedelta(days=calendar_days)
    return EvaluationSchedule(
        prediction_id=prediction.prediction_id,
        idempotency_key=f"evaluation:{prediction.prediction_id}",
        model_version=prediction.model_version,
        dataset_version=prediction.dataset_version,
        horizon_sessions=prediction.horizon_sessions,
        market_key=prediction.market_key,
        sector=prediction.sector,
        expected_maturity_at=expected,
        next_check_at=expected,
    )


def _model_key(model: ModelVersion) -> tuple[int, str, str, str]:
    return model.horizon_sessions, model.asset_type, model.universe, _profile_key(model.profile)


def _job(row: JobRecord) -> PredictionJob:
    return PredictionJob(
        job_id=row.job_id,
        kind=row.kind,
        status=row.status,
        idempotency_key=row.idempotency_key,
        payload=row.payload,
        attempts=row.attempts,
        created_at=row.created_at,
        updated_at=row.updated_at,
        error_code=row.error_code,
    )
