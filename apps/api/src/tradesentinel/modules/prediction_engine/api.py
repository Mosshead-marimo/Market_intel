from __future__ import annotations

import hmac
from datetime import datetime
from hashlib import sha256
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel

from tradesentinel.api.dependencies import ContainerDependency
from tradesentinel.domain.prediction import (
    ActivationRequest,
    CalibrationBin,
    DatasetBuildRequest,
    EmptyPredictionInput,
    EvaluationRequest,
    EvaluationScheduleList,
    JobReference,
    ModelPerformanceReport,
    ModelReference,
    ModelVersion,
    ModelVersionList,
    ObservationBatch,
    ObservationReceipt,
    PaginatedPredictions,
    PerformanceFilter,
    PerformanceRebuildResult,
    PredictionEvaluation,
    PredictionJob,
    PredictionReference,
    PredictionRequest,
    PredictionResult,
    TrainingRequest,
)
from tradesentinel.platform.contracts import (
    CapabilityExecutionRequest,
    CapabilityResult,
    ExecutionContext,
)

router = APIRouter(prefix="/api/v1/admin/prediction", tags=["prediction-admin"])


async def _authorize(
    authorization: str | None, request: Request, container: ContainerDependency
) -> ExecutionContext:
    configured = container.settings.prediction_admin_token_hash
    if configured is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    valid = hmac.compare_digest(
        sha256(supplied.encode()).hexdigest(), configured.get_secret_value().lower()
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid administrative credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    allowed, retry_after = await container.rate_limiter.allow(
        f"prediction-admin:{configured.get_secret_value()[:12]}",
        container.settings.prediction_admin_rate_limit,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Administrative request rate limit exceeded.",
            headers={"Retry-After": str(retry_after)},
        )
    return ExecutionContext(
        request_id=UUID(request.state.request_id),
        principal_id="prediction-admin",
        permissions=("prediction.admin",),
    )


async def _execute[OutputT: BaseModel](
    capability: str,
    payload: BaseModel,
    output: type[OutputT],
    request: Request,
    container: ContainerDependency,
    authorization: str | None,
) -> OutputT:
    context = await _authorize(authorization, request, container)
    outcome = await container.pipeline.execute(
        CapabilityExecutionRequest(capability=capability, payload=payload.model_dump(mode="json")),
        context,
    )
    result = outcome.result
    if not isinstance(result, CapabilityResult):
        raise RuntimeError("prediction admin capability returned a workflow result")
    return output.model_validate(result.data)


@router.post("/observations/batches", response_model=ObservationReceipt, status_code=201)
async def ingest_observations(
    body: ObservationBatch,
    request: Request,
    container: ContainerDependency,
    authorization: str | None = Header(default=None),
) -> ObservationReceipt:
    return await _execute(
        "prediction.observations.ingest",
        body,
        ObservationReceipt,
        request,
        container,
        authorization,
    )


@router.post("/datasets/build", response_model=PredictionJob, status_code=202)
async def build_dataset(
    body: DatasetBuildRequest,
    request: Request,
    container: ContainerDependency,
    authorization: str | None = Header(default=None),
) -> PredictionJob:
    return await _execute(
        "prediction.dataset.enqueue", body, PredictionJob, request, container, authorization
    )


@router.post("/models/train", response_model=PredictionJob, status_code=202)
async def train_model(
    body: TrainingRequest,
    request: Request,
    container: ContainerDependency,
    authorization: str | None = Header(default=None),
) -> PredictionJob:
    return await _execute(
        "prediction.training.enqueue", body, PredictionJob, request, container, authorization
    )


@router.get("/jobs/{job_id}", response_model=PredictionJob)
async def get_job(
    job_id: UUID,
    request: Request,
    container: ContainerDependency,
    authorization: str | None = Header(default=None),
) -> PredictionJob:
    return await _execute(
        "prediction.job.read",
        JobReference(job_id=job_id),
        PredictionJob,
        request,
        container,
        authorization,
    )


@router.get("/models", response_model=ModelVersionList)
async def list_models(
    request: Request,
    container: ContainerDependency,
    authorization: str | None = Header(default=None),
) -> ModelVersionList:
    return await _execute(
        "prediction.model.list",
        EmptyPredictionInput(),
        ModelVersionList,
        request,
        container,
        authorization,
    )


@router.get("/models/{model_version}", response_model=ModelVersion)
async def get_model(
    model_version: str,
    request: Request,
    container: ContainerDependency,
    authorization: str | None = Header(default=None),
) -> ModelVersion:
    return await _execute(
        "prediction.model.read",
        ModelReference(model_version=model_version),
        ModelVersion,
        request,
        container,
        authorization,
    )


@router.post("/models/{model_version}/activate", response_model=ModelVersion)
async def activate_model(
    model_version: str,
    request: Request,
    container: ContainerDependency,
    authorization: str | None = Header(default=None),
) -> ModelVersion:
    return await _execute(
        "prediction.model.activate",
        ActivationRequest(model_version=model_version),
        ModelVersion,
        request,
        container,
        authorization,
    )


@router.post("/predictions", response_model=PredictionResult, status_code=201)
async def create_prediction(
    body: PredictionRequest,
    request: Request,
    container: ContainerDependency,
    authorization: str | None = Header(default=None),
) -> PredictionResult:
    return await _execute(
        "prediction.predict", body, PredictionResult, request, container, authorization
    )


@router.get("/predictions", response_model=PaginatedPredictions)
async def list_predictions(
    request: Request,
    container: ContainerDependency,
    authorization: str | None = Header(default=None),
) -> PaginatedPredictions:
    return await _execute(
        "prediction.history.read",
        EmptyPredictionInput(),
        PaginatedPredictions,
        request,
        container,
        authorization,
    )


@router.get("/predictions/{prediction_id}", response_model=PredictionResult)
async def get_prediction(
    prediction_id: UUID,
    request: Request,
    container: ContainerDependency,
    authorization: str | None = Header(default=None),
) -> PredictionResult:
    return await _execute(
        "prediction.read",
        PredictionReference(prediction_id=prediction_id),
        PredictionResult,
        request,
        container,
        authorization,
    )


@router.post("/evaluations/run", response_model=PredictionJob, status_code=202)
async def evaluate_predictions(
    body: EvaluationRequest,
    request: Request,
    container: ContainerDependency,
    authorization: str | None = Header(default=None),
) -> PredictionJob:
    return await _execute(
        "prediction.evaluation.enqueue", body, PredictionJob, request, container, authorization
    )


def _performance_filter(
    model_version: str | None,
    horizon_sessions: Literal[5, 20] | None,
    asset_type: str | None,
    exchange: str | None,
    sector: str | None,
    start: datetime | None,
    end: datetime | None,
) -> PerformanceFilter:
    return PerformanceFilter(
        model_version=model_version,
        horizon_sessions=horizon_sessions,
        asset_type=asset_type,
        exchange=exchange,
        sector=sector,
        start=start,
        end=end,
    )


@router.get("/model-performance", response_model=ModelPerformanceReport)
async def model_performance(
    request: Request,
    container: ContainerDependency,
    authorization: str | None = Header(default=None),
    model_version: str | None = None,
    horizon_sessions: Literal[5, 20] | None = None,
    asset_type: str | None = None,
    exchange: str | None = None,
    sector: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
) -> ModelPerformanceReport:
    return await _execute(
        "prediction.performance.read",
        _performance_filter(
            model_version, horizon_sessions, asset_type, exchange, sector, start, end
        ),
        ModelPerformanceReport,
        request,
        container,
        authorization,
    )


@router.get("/model-performance/calibration", response_model=tuple[CalibrationBin, ...])
async def model_calibration(
    request: Request,
    container: ContainerDependency,
    authorization: str | None = Header(default=None),
    model_version: str | None = None,
    horizon_sessions: Literal[5, 20] | None = None,
) -> tuple[CalibrationBin, ...]:
    report = await _execute(
        "prediction.performance.read",
        PerformanceFilter(model_version=model_version, horizon_sessions=horizon_sessions),
        ModelPerformanceReport,
        request,
        container,
        authorization,
    )
    return report.calibration


@router.post("/model-performance/rebuild", response_model=PerformanceRebuildResult)
async def rebuild_model_performance(
    request: Request,
    container: ContainerDependency,
    authorization: str | None = Header(default=None),
) -> PerformanceRebuildResult:
    return await _execute(
        "prediction.performance.rebuild",
        EmptyPredictionInput(),
        PerformanceRebuildResult,
        request,
        container,
        authorization,
    )


@router.get("/evaluations", response_model=EvaluationScheduleList)
async def list_evaluations(
    request: Request,
    container: ContainerDependency,
    authorization: str | None = Header(default=None),
) -> EvaluationScheduleList:
    return await _execute(
        "prediction.evaluation.schedules",
        EmptyPredictionInput(),
        EvaluationScheduleList,
        request,
        container,
        authorization,
    )


@router.get("/predictions/{prediction_id}/evaluation", response_model=PredictionEvaluation)
async def get_prediction_evaluation(
    prediction_id: UUID,
    request: Request,
    container: ContainerDependency,
    authorization: str | None = Header(default=None),
) -> PredictionEvaluation:
    return await _execute(
        "prediction.evaluation.read",
        PredictionReference(prediction_id=prediction_id),
        PredictionEvaluation,
        request,
        container,
        authorization,
    )
