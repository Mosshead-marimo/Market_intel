from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from pydantic import BaseModel, JsonValue

from tradesentinel.domain.prediction import (
    ActivationRequest,
    DatasetBuildRequest,
    EmptyPredictionInput,
    EvaluationRequest,
    EvaluationScheduleList,
    JobExecutionRequest,
    JobReference,
    ModelPerformanceReport,
    ModelReference,
    ObservationBatch,
    PerformanceFilter,
    PerformanceRebuildResult,
    PredictionEvaluation,
    PredictionReference,
    PredictionRequest,
    TrainingRequest,
)
from tradesentinel.modules.prediction_engine.errors import PredictionDataError
from tradesentinel.modules.prediction_engine.evaluation import PredictionEvaluationService
from tradesentinel.modules.prediction_engine.service import PredictionService
from tradesentinel.platform.capabilities import Capability
from tradesentinel.platform.contracts import (
    CapabilityResult,
    EventEnvelope,
    ExecutionContext,
    RunMetadata,
    RunStatus,
)
from tradesentinel.platform.events import EventBus


def _result(value: BaseModel, started: datetime) -> CapabilityResult:
    return CapabilityResult(
        capability="",
        status=RunStatus.COMPLETED,
        data=cast(dict[str, JsonValue], value.model_dump(mode="json")),
        metadata=RunMetadata(started_at=started, completed_at=datetime.now(UTC)),
    )


class _PredictionCapability:
    def __init__(self, service: PredictionService, events: EventBus) -> None:
        self.service = service
        self.events = events

    async def emit(self, name: str, context: ExecutionContext, **payload: JsonValue) -> None:
        await self.events.publish(
            EventEnvelope(
                name=name,
                producer="prediction_engine",
                correlation_id=context.correlation_id,
                causation_id=context.causation_id,
                payload=payload,
            )
        )


class IngestObservationsCapability(_PredictionCapability, Capability[ObservationBatch]):
    input_model = ObservationBatch

    async def execute(
        self, context: ExecutionContext, payload: ObservationBatch
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        receipt = await self.service.ingest(payload)
        await self.emit(
            "prediction.observations.ingested",
            context,
            batch_id=str(receipt.batch_id),
            accepted=receipt.accepted,
        )
        return _result(receipt, started)


class EnqueueDatasetCapability(_PredictionCapability, Capability[DatasetBuildRequest]):
    input_model = DatasetBuildRequest

    async def execute(
        self, context: ExecutionContext, payload: DatasetBuildRequest
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        job = await self.service.enqueue_dataset(payload)
        await self.emit("prediction.job.queued", context, job_id=str(job.job_id), kind=job.kind)
        return _result(job, started)


class EnqueueTrainingCapability(_PredictionCapability, Capability[TrainingRequest]):
    input_model = TrainingRequest

    async def execute(
        self, context: ExecutionContext, payload: TrainingRequest
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        job = await self.service.enqueue_training(payload)
        await self.emit("prediction.job.queued", context, job_id=str(job.job_id), kind=job.kind)
        return _result(job, started)


class EnqueueEvaluationCapability(_PredictionCapability, Capability[EvaluationRequest]):
    input_model = EvaluationRequest

    async def execute(
        self, context: ExecutionContext, payload: EvaluationRequest
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        job = await self.service.enqueue_evaluation(payload.idempotency_key)
        await self.emit("prediction.job.queued", context, job_id=str(job.job_id), kind=job.kind)
        return _result(job, started)


class JobReadCapability(_PredictionCapability, Capability[JobReference]):
    input_model = JobReference

    async def execute(self, context: ExecutionContext, payload: JobReference) -> CapabilityResult:
        started = datetime.now(UTC)
        job = await self.service.repository.job(payload.job_id)
        if job is None:
            raise PredictionDataError("The prediction job was not found.")
        return _result(job, started)


class JobExecuteCapability(_PredictionCapability, Capability[JobExecutionRequest]):
    input_model = JobExecutionRequest

    async def execute(
        self, context: ExecutionContext, payload: JobExecutionRequest
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        job = await self.service.execute_job(payload.job_id)
        await self.emit(
            "prediction.job.completed",
            context,
            job_id=str(job.job_id),
            status=job.status.value,
        )
        return _result(job, started)


class ModelListCapability(_PredictionCapability, Capability[EmptyPredictionInput]):
    input_model = EmptyPredictionInput

    async def execute(
        self, context: ExecutionContext, payload: EmptyPredictionInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        from tradesentinel.domain.prediction import ModelVersionList

        return _result(ModelVersionList(items=await self.service.repository.models()), started)


class ModelReadCapability(_PredictionCapability, Capability[ModelReference]):
    input_model = ModelReference

    async def execute(self, context: ExecutionContext, payload: ModelReference) -> CapabilityResult:
        started = datetime.now(UTC)
        model = next(
            (
                item
                for item in await self.service.repository.models()
                if item.model_version == payload.model_version
            ),
            None,
        )
        if model is None:
            raise PredictionDataError("The model version was not found.")
        return _result(model, started)


class ActivateModelCapability(_PredictionCapability, Capability[ActivationRequest]):
    input_model = ActivationRequest

    async def execute(
        self, context: ExecutionContext, payload: ActivationRequest
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        model = await self.service.activate(payload.model_version)
        await self.emit("prediction.model.activated", context, model_version=model.model_version)
        return _result(model, started)


class PredictCapability(_PredictionCapability, Capability[PredictionRequest]):
    input_model = PredictionRequest

    async def execute(
        self, context: ExecutionContext, payload: PredictionRequest
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        prediction = await self.service.predict(payload)
        await self.emit(
            "prediction.completed",
            context,
            prediction_id=str(prediction.prediction_id),
            model_version=prediction.model_version,
        )
        return _result(prediction, started)


class PredictionReadCapability(_PredictionCapability, Capability[PredictionReference]):
    input_model = PredictionReference

    async def execute(
        self, context: ExecutionContext, payload: PredictionReference
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        prediction = await self.service.repository.prediction(payload.prediction_id)
        if prediction is None:
            raise PredictionDataError("The prediction was not found.")
        return _result(prediction, started)


class PredictionHistoryCapability(_PredictionCapability, Capability[EmptyPredictionInput]):
    input_model = EmptyPredictionInput

    async def execute(
        self, context: ExecutionContext, payload: EmptyPredictionInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        from tradesentinel.domain.prediction import PaginatedPredictions

        return _result(
            PaginatedPredictions(items=await self.service.repository.predictions()), started
        )


class _EvaluationCapability:
    def __init__(self, evaluation_service: PredictionEvaluationService, events: EventBus) -> None:
        self.evaluation_service = evaluation_service
        self.events = events


class EvaluationCollectCapability(_EvaluationCapability, Capability[EmptyPredictionInput]):
    input_model = EmptyPredictionInput

    async def execute(
        self, context: ExecutionContext, payload: EmptyPredictionInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        processed = await self.evaluation_service.evaluate_due()
        await self.events.publish(
            EventEnvelope(
                name="prediction.evaluations.collected",
                producer="prediction_engine",
                correlation_id=context.correlation_id,
                payload={"processed": processed},
            )
        )
        return _result(
            PerformanceRebuildResult(outcomes_processed=processed, aggregates_written=0), started
        )


class EvaluationScheduleListCapability(_EvaluationCapability, Capability[EmptyPredictionInput]):
    input_model = EmptyPredictionInput

    async def execute(
        self, context: ExecutionContext, payload: EmptyPredictionInput
    ) -> CapabilityResult:
        return _result(
            EvaluationScheduleList(items=await self.evaluation_service.repository.schedules()),
            datetime.now(UTC),
        )


class PredictionEvaluationReadCapability(_EvaluationCapability, Capability[PredictionReference]):
    input_model = PredictionReference

    async def execute(
        self, context: ExecutionContext, payload: PredictionReference
    ) -> CapabilityResult:
        prediction = await self.evaluation_service.repository.prediction(payload.prediction_id)
        schedule = next(
            (
                item
                for item in await self.evaluation_service.repository.schedules()
                if item.prediction_id == payload.prediction_id
            ),
            None,
        )
        if prediction is None or schedule is None:
            raise PredictionDataError("The prediction evaluation was not found.")
        outcome = await self.evaluation_service.repository.outcome(payload.prediction_id)
        return _result(
            PredictionEvaluation(prediction=prediction, schedule=schedule, outcome=outcome),
            datetime.now(UTC),
        )


class ModelPerformanceCapability(_EvaluationCapability, Capability[PerformanceFilter]):
    input_model = PerformanceFilter

    async def execute(
        self, context: ExecutionContext, payload: PerformanceFilter
    ) -> CapabilityResult:
        report: ModelPerformanceReport = await self.evaluation_service.performance(payload)
        return _result(report, datetime.now(UTC))


class PerformanceRebuildCapability(_EvaluationCapability, Capability[EmptyPredictionInput]):
    input_model = EmptyPredictionInput

    async def execute(
        self, context: ExecutionContext, payload: EmptyPredictionInput
    ) -> CapabilityResult:
        result = await self.evaluation_service.rebuild_metrics()
        return _result(result, datetime.now(UTC))
