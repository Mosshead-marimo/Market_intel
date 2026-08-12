from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from tradesentinel.api.app import create_app
from tradesentinel.domain.instruments import AssetType, InstrumentRef
from tradesentinel.domain.prediction import (
    Direction,
    FeatureGroup,
    FeatureVector,
    LabelDefinition,
    ModelMetrics,
    ModelVersion,
    NumericRange,
    ObservationBatch,
    PerformanceFilter,
    PointInTimeValue,
    PredictionResult,
    ProbabilitySet,
    Scenario,
    TrainingLabel,
)
from tradesentinel.modules.prediction_engine.errors import (
    PredictionDataError,
    PredictionQualityGateError,
)
from tradesentinel.modules.prediction_engine.evaluation import PredictionEvaluationService
from tradesentinel.modules.prediction_engine.repository import (
    InMemoryPredictionRepository,
    PredictionRepositoryFactory,
)
from tradesentinel.modules.prediction_engine.service import (
    FeatureBuilder,
    PredictionService,
    ScenarioGenerator,
    TrainingSample,
)
from tradesentinel.platform.config import Settings
from tradesentinel.platform.object_store import FileObjectStore, InMemoryObjectStore
from tradesentinel.providers.contracts import (
    FreshnessStatus,
    InstrumentReference,
    LicenseClassification,
    PriceBar,
    PriceHistory,
    ProviderMetadata,
)


def instrument() -> InstrumentRef:
    return InstrumentRef(
        instrument_id=uuid4(),
        symbol="TEST",
        name="Test Corporation",
        exchange="NSE",
        asset_type=AssetType.EQUITY,
        currency="INR",
        aliases=("TESTCO",),
    )


def batches(reference: InstrumentRef) -> tuple[ObservationBatch, ...]:
    started = datetime(2025, 1, 1, tzinfo=UTC)
    market: list[PointInTimeValue] = []
    for index in range(70):
        observed = started + timedelta(days=index)
        for name, value in (
            ("market.adjusted_close", Decimal(100 + index)),
            ("market.volume", Decimal(1_000 + index * 2)),
            ("market.benchmark_adjusted_close", Decimal(200 + index)),
        ):
            market.append(
                PointInTimeValue(
                    name=name,
                    value=value,
                    observed_at=observed,
                    known_at=observed,
                    source_version="fixture-v1",
                )
            )
    technical = PointInTimeValue(
        name="technical.calculation_version",
        value=Decimal(1),
        observed_at=started + timedelta(days=69),
        known_at=started + timedelta(days=69),
        source_version="technical-v1",
    )
    return (
        ObservationBatch(
            idempotency_key="market-batch-0001",
            instrument=reference,
            group=FeatureGroup.MARKET,
            observations=tuple(market),
        ),
        ObservationBatch(
            idempotency_key="technical-batch-0001",
            instrument=reference,
            group=FeatureGroup.TECHNICAL,
            observations=(technical,),
        ),
    )


def model(*, active: bool = False, ece: str = "0.05") -> ModelVersion:
    return ModelVersion(
        model_version="model-v1",
        dataset_version="dataset-v1",
        feature_schema_version="prediction-features-v1",
        profile=(FeatureGroup.MARKET, FeatureGroup.TECHNICAL),
        horizon_sessions=5,
        asset_type="equity",
        universe="all-equities",
        family="logistic_regression",
        calibration_version="sigmoid-v1",
        preprocessing_version="median-indicator-v1",
        training_code_version="prediction-training-v1",
        artifact_schema_version="skops-bundle-v1",
        artifact_key="prediction/model-v1.skops",
        artifact_sha256="a" * 64,
        artifact_size=100,
        library_versions={"python": "3.13"},
        trusted_types=(),
        metrics=ModelMetrics(
            multiclass_brier=Decimal("0.4"),
            log_loss=Decimal("0.8"),
            expected_calibration_error=Decimal(ece),
            range_coverage=Decimal("0.8"),
            total_samples=500,
            class_samples={"rise": 150, "sideways": 200, "decline": 150},
            leakage_checks_passed=True,
        ),
        active=active,
    )


def persisted_prediction(reference: InstrumentRef) -> PredictionResult:
    probabilities = ProbabilitySet(
        rise=Decimal("0.6"), sideways=Decimal("0.25"), decline=Decimal("0.15")
    )
    return PredictionResult(
        instrument=reference,
        data_cutoff=datetime(2025, 1, 10, tzinfo=UTC),
        horizon_sessions=5,
        label_threshold=Decimal("0.01"),
        direction=Direction.RISE,
        probabilities=probabilities,
        confidence=Decimal("0.2"),
        cutoff_adjusted_close=Decimal(100),
        currency=reference.currency,
        modeled_return_range=NumericRange(low=Decimal("-0.1"), high=Decimal("0.2")),
        modeled_price_range=NumericRange(low=Decimal(90), high=Decimal(120)),
        scenarios=(
            Scenario(
                name="bear",
                probability=probabilities.decline,
                return_range=NumericRange(low=Decimal("-0.1"), high=Decimal("-0.02")),
                price_range=NumericRange(low=Decimal(90), high=Decimal(98)),
                representative_return=Decimal("-0.05"),
            ),
            Scenario(
                name="base",
                probability=probabilities.sideways,
                return_range=NumericRange(low=Decimal("-0.02"), high=Decimal("0.08")),
                price_range=NumericRange(low=Decimal(98), high=Decimal(108)),
                representative_return=Decimal("0.02"),
            ),
            Scenario(
                name="bull",
                probability=probabilities.rise,
                return_range=NumericRange(low=Decimal("0.08"), high=Decimal("0.2")),
                price_range=NumericRange(low=Decimal(108), high=Decimal(120)),
                representative_return=Decimal("0.12"),
            ),
        ),
        model_version="model-v1",
        dataset_version="dataset-v1",
        feature_schema_version="prediction-features-v1",
        feature_profile=(FeatureGroup.MARKET, FeatureGroup.TECHNICAL),
        feature_fingerprint="c" * 64,
        label_version="direction-volatility-v1",
        preprocessing_version="median-indicator-v1",
        calibration_version="sigmoid-v1",
        training_code_version="prediction-training-v1",
        artifact_version="skops-bundle-v1",
        market_key=f"{reference.asset_type.value}:{reference.exchange}",
        sector="technology",
        sector_known_at=datetime(2025, 1, 9, tzinfo=UTC),
        sector_source="fixture-profile-v1",
    )


class FakeEvaluationMarketData:
    def __init__(self, bars: tuple[PriceBar, ...]) -> None:
        self.bars = bars

    async def get_history(self, context: object, request: object) -> PriceHistory:
        return PriceHistory(
            instrument=InstrumentReference(symbol="TEST", exchange="NSE"),
            interval="1d",
            currency="INR",
            bars=self.bars,
            metadata=ProviderMetadata(
                provider="fixture-market",
                source_id="fixture-history",
                observed_at=self.bars[-1].timestamp if self.bars else None,
                retrieved_at=datetime(2025, 2, 1, tzinfo=UTC),
                license=LicenseClassification.INTERNAL,
                freshness=FreshnessStatus.FRESH,
            ),
        )


def test_feature_builder_is_point_in_time_and_deterministic() -> None:
    reference = instrument()
    cutoff = datetime(2025, 3, 11, tzinfo=UTC)
    first = FeatureBuilder().build(
        reference,
        batches(reference),
        cutoff,
        (FeatureGroup.MARKET, FeatureGroup.TECHNICAL),
    )
    second = FeatureBuilder().build(
        reference,
        batches(reference),
        cutoff,
        (FeatureGroup.TECHNICAL, FeatureGroup.MARKET),
    )
    assert first.fingerprint == second.fingerprint
    assert [value.name for value in first.values] == sorted(value.name for value in first.values)
    assert all(value.known_at <= cutoff for value in first.values)
    assert next(value.value for value in first.values if value.name == "market.return_5") > 0


def test_feature_builder_rejects_missing_exact_profile() -> None:
    reference = instrument()
    with pytest.raises(PredictionDataError):
        FeatureBuilder().build(
            reference,
            batches(reference),
            datetime(2025, 3, 11, tzinfo=UTC),
            (FeatureGroup.MARKET, FeatureGroup.TECHNICAL, FeatureGroup.SENTIMENT),
        )


def test_known_at_cannot_precede_observation() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError):
        PointInTimeValue(
            name="market.adjusted_close",
            value=Decimal(100),
            observed_at=now,
            known_at=now - timedelta(seconds=1),
            source_version="v1",
        )


def test_probabilities_and_scenario_rearrangement() -> None:
    probabilities = ProbabilitySet(
        rise=Decimal("0.5"), sideways=Decimal("0.3"), decline=Decimal("0.2")
    )
    scenarios, returns, prices = ScenarioGenerator().generate(
        probabilities,
        (Decimal("0.20"), Decimal("-0.10"), Decimal("0.05"), Decimal("0"), Decimal("0.10")),
        Decimal(100),
    )
    assert [scenario.name for scenario in scenarios] == ["bear", "base", "bull"]
    assert returns.low == Decimal("-0.10") and returns.high == Decimal("0.20")
    assert prices.low == Decimal("90.00") and prices.high == Decimal("120.00")
    assert scenarios[0].probability == probabilities.decline
    with pytest.raises(ValidationError):
        ProbabilitySet(rise=Decimal("0.5"), sideways=Decimal("0.5"), decline=Decimal("0.5"))


@pytest.mark.asyncio
async def test_repository_ingestion_activation_and_history_are_idempotent() -> None:
    repository = InMemoryPredictionRepository()
    batch = batches(instrument())[0]
    first = await repository.ingest(batch)
    duplicate = await repository.ingest(batch)
    assert first.accepted == len(batch.observations)
    assert duplicate.duplicate and duplicate.batch_id == first.batch_id
    await repository.save_model(model())
    activated = await repository.activate("model-v1")
    assert activated is not None and activated.active
    selected = await repository.active_model(5, "equity", "all-equities", "market,technical")
    assert selected is not None and selected.model_version == "model-v1"


@pytest.mark.asyncio
async def test_durable_job_outbox_and_claim_are_idempotent() -> None:
    from tradesentinel.domain.prediction import PredictionJob

    repository = InMemoryPredictionRepository()
    job = await repository.enqueue(
        PredictionJob(
            kind="evaluation",
            idempotency_key="evaluation-job-0001",
            payload={},
        )
    )
    duplicate = await repository.enqueue(job.model_copy(update={"job_id": uuid4()}))
    assert duplicate.job_id == job.job_id
    outbox = await repository.pending_outbox()
    assert len(outbox) == 1 and outbox[0].job_id == job.job_id
    claimed = await repository.claim_job(job.job_id)
    assert claimed is not None and claimed.attempts == 1
    assert await repository.claim_job(job.job_id) is None
    await repository.mark_outbox_published(outbox[0].event_id)
    assert await repository.pending_outbox() == ()


@pytest.mark.asyncio
async def test_object_stores_verify_content_and_reject_unsafe_keys(tmp_path: Path) -> None:
    for store in (InMemoryObjectStore(), FileObjectStore(tmp_path)):
        stored = await store.put("prediction/model.skops", b"artifact")
        assert stored.sha256 == sha256(b"artifact").hexdigest()
        assert await store.get(stored.key) == b"artifact"
        with pytest.raises(ValueError):
            await store.put("../escape", b"bad")


@pytest.mark.asyncio
async def test_training_artifact_and_prediction_are_versioned_and_persisted() -> None:
    reference = instrument()
    source_batches = batches(reference)
    cutoff = datetime(2025, 3, 11, tzinfo=UTC)
    base = FeatureBuilder().build(
        reference,
        source_batches,
        cutoff,
        (FeatureGroup.MARKET, FeatureGroup.TECHNICAL),
    )
    directions = (Direction.RISE, Direction.SIDEWAYS, Direction.DECLINE)
    samples: list[TrainingSample] = []
    for index in range(90):
        vector = FeatureVector(
            vector_id=uuid4(),
            instrument=reference,
            cutoff=cutoff + timedelta(days=index),
            profile=base.profile,
            values=base.values,
            fingerprint=sha256(f"sample-{index}".encode()).hexdigest(),
        )
        direction = directions[index % 3]
        samples.append(
            TrainingSample(
                vector=vector,
                label=TrainingLabel(
                    vector_id=vector.vector_id,
                    direction=direction,
                    forward_return=Decimal(index % 3 - 1) / Decimal(100),
                    threshold=Decimal("0.01"),
                    outcome_at=vector.cutoff + timedelta(days=5),
                    definition=LabelDefinition(
                        horizon_sessions=5, minimum_threshold=Decimal("0.01")
                    ),
                ),
            )
        )
    repository = InMemoryPredictionRepository()
    factory = object.__new__(PredictionRepositoryFactory)
    factory.implementation = repository
    store = InMemoryObjectStore()
    service = PredictionService(
        factory,
        store,
        Settings(
            environment="test",
            prediction_min_training_samples=30,
            prediction_min_class_samples=5,
        ),
    )
    from tradesentinel.domain.prediction import DatasetVersion, PredictionRequest

    dataset = DatasetVersion(
        dataset_version="dataset-training-test",
        feature_schema_version="prediction-features-v1",
        label_version="direction-volatility-v1",
        profile=base.profile,
        horizon_sessions=5,
        universe="all-equities",
        sample_count=len(samples),
        fingerprint="b" * 64,
    )
    trained = await service._train_models(dataset, tuple(samples), 42)
    assert trained.artifact_schema_version == "skops-bundle-v1"
    assert trained.library_versions["scikit-learn"]
    await repository.activate(trained.model_version)
    for batch in source_batches:
        await repository.ingest(batch)
    prediction = await service.predict(
        PredictionRequest(
            instrument=reference,
            cutoff=cutoff,
            horizon_sessions=5,
            cutoff_adjusted_close=Decimal(169),
            currency="INR",
        )
    )
    assert prediction.model_version == trained.model_version
    assert sum(prediction.probabilities.model_dump().values()) == Decimal(1)
    assert prediction.scenarios[0].name == "bear"
    assert await repository.prediction(prediction.prediction_id) == prediction


def test_admin_api_is_hidden_without_configuration() -> None:
    settings = Settings(
        environment="test",
        persistence_backend="memory",
        event_backend="memory",
        cache_backend="memory",
    )
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/v1/admin/prediction/models")
        assert response.status_code == 404
        public = client.post("/api/v1/predictions", json={})
        assert public.status_code == 501


def test_admin_api_uses_hashed_bearer_and_discovers_capabilities() -> None:
    token = "local-prediction-admin"
    settings = Settings(
        environment="test",
        persistence_backend="memory",
        event_backend="memory",
        cache_backend="memory",
        prediction_admin_token_hash=sha256(token.encode()).hexdigest(),
    )
    with TestClient(create_app(settings)) as client:
        denied = client.get(
            "/api/v1/admin/prediction/models",
            headers={"Authorization": "Bearer incorrect"},
        )
        assert denied.status_code == 401
        response = client.get(
            "/api/v1/admin/prediction/models",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        assert response.json() == {"items": []}
        performance = client.get(
            "/api/v1/admin/prediction/model-performance",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert performance.status_code == 200
        assert performance.json()["overall"]["sample_count"] == 0
        assert len(performance.json()["confusion_matrix"]["counts"]) == 4
        calibration = client.get(
            "/api/v1/admin/prediction/model-performance/calibration",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert calibration.status_code == 200
        assert len(calibration.json()) == 30
        evaluations = client.get(
            "/api/v1/admin/prediction/evaluations",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert evaluations.status_code == 200
        assert evaluations.json() == {"items": []}
        capabilities = client.get("/api/v1/capabilities").json()
        names = {item["name"] for item in capabilities}
        assert "prediction.predict" in names
        assert "prediction.job.execute" in names
        assert "prediction.performance.read" in names


def test_quality_gate_error_is_typed() -> None:
    error = PredictionQualityGateError(["calibration"])
    assert error.code == "PREDICTION_QUALITY_GATE_FAILED"
    assert error.details == {"failures": ["calibration"]}


@pytest.mark.asyncio
async def test_prediction_creates_schedule_and_provider_evaluation_updates_metrics() -> None:
    reference = instrument()
    prediction = persisted_prediction(reference)
    repository = InMemoryPredictionRepository()
    factory = object.__new__(PredictionRepositoryFactory)
    factory.implementation = repository
    await factory.save_prediction(prediction)
    schedules = await factory.schedules()
    assert len(schedules) == 1
    assert schedules[0].prediction_id == prediction.prediction_id

    bars = tuple(
        PriceBar(
            timestamp=prediction.data_cutoff + timedelta(days=index + 1),
            open=Decimal(100 + index),
            high=Decimal(102 + index),
            low=Decimal(99 + index),
            close=Decimal(101 + index),
            adjusted_close=Decimal(101 + index),
            volume=Decimal(1_000),
        )
        for index in range(5)
    )
    service = PredictionEvaluationService(
        factory,
        FakeEvaluationMarketData(bars),  # type: ignore[arg-type]
        Settings(environment="test"),
    )
    due = schedules[0].model_copy(update={"next_check_at": datetime(2025, 1, 20, tzinfo=UTC)})
    await factory.update_schedule(due)
    result = await service.evaluate(due, datetime(2025, 2, 1, tzinfo=UTC))
    assert result.outcome is not None
    assert result.outcome.realized_direction == Direction.RISE
    assert result.outcome.provider == "fixture-market"
    assert result.outcome.within_modeled_price_range
    report = await service.performance(PerformanceFilter())
    assert report.overall.sample_count == 1
    assert report.overall.directional_accuracy == Decimal(1)
    assert report.confusion_matrix.counts[0][0] == 1
    assert {item.key for item in report.cohorts if item.dimension == "market"} == {"equity:NSE"}
    assert {item.key for item in report.cohorts if item.dimension == "sector"} == {"technology"}
    assert {"30d", "90d", "365d"}.issubset(
        {item.key for item in report.cohorts if item.dimension == "calendar"}
    )
    assert {item.key for item in report.cohorts if item.dimension == "count"} == {
        "50",
        "100",
        "250",
    }


@pytest.mark.asyncio
async def test_insufficient_provider_history_becomes_overdue_without_outcome() -> None:
    prediction = persisted_prediction(instrument())
    repository = InMemoryPredictionRepository()
    factory = object.__new__(PredictionRepositoryFactory)
    factory.implementation = repository
    await factory.save_prediction(prediction)
    schedule = (await factory.schedules())[0]
    service = PredictionEvaluationService(
        factory,
        FakeEvaluationMarketData(()),  # type: ignore[arg-type]
        Settings(environment="test", prediction_evaluation_grace_days=1),
    )
    result = await service.evaluate(
        schedule,
        schedule.expected_maturity_at + timedelta(days=2),
    )
    assert result.outcome is None
    assert result.schedule.state.value == "overdue"
    assert result.schedule.last_error_code == "PREDICTION_OUTCOME_NOT_MATURE"
    assert await factory.outcome(prediction.prediction_id) is None
