from __future__ import annotations

import math
import platform
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import Any
from uuid import UUID

from tradesentinel.domain.instruments import InstrumentRef
from tradesentinel.domain.prediction import (
    DatasetBuildRequest,
    DatasetVersion,
    Direction,
    FeatureGroup,
    FeatureValue,
    FeatureVector,
    JobStatus,
    LabelDefinition,
    ModelMetrics,
    ModelVersion,
    NumericRange,
    ObservationBatch,
    ObservationReceipt,
    PredictionJob,
    PredictionOutcome,
    PredictionRequest,
    PredictionResult,
    ProbabilitySet,
    Scenario,
    TrainingLabel,
    TrainingRequest,
)
from tradesentinel.modules.prediction_engine.errors import (
    PredictionArtifactError,
    PredictionDataError,
    PredictionModelNotAvailableError,
    PredictionQualityGateError,
)
from tradesentinel.modules.prediction_engine.repository import PredictionRepositoryFactory
from tradesentinel.platform.config import Settings
from tradesentinel.platform.object_store import ObjectStore

SCHEMA_VERSION = "prediction-features-v1"
TRAINING_CODE_VERSION = "prediction-training-v1"


@dataclass(frozen=True)
class TrainingSample:
    vector: FeatureVector
    label: TrainingLabel


class FeatureBuilder:
    def build(
        self,
        instrument: InstrumentRef,
        batches: tuple[ObservationBatch, ...],
        cutoff: datetime,
        profile: tuple[FeatureGroup, ...],
    ) -> FeatureVector:
        selected = [
            b
            for b in batches
            if b.instrument.instrument_id == instrument.instrument_id and b.group in profile
        ]
        present = {b.group for b in selected}
        missing = set(profile) - present
        if missing:
            raise PredictionDataError(
                "The exact feature profile is unavailable.", missing=sorted(missing)
            )
        raw: dict[str, list[tuple[datetime, Decimal, datetime, str]]] = {}
        for batch in selected:
            for item in batch.observations:
                if item.known_at > cutoff or not isinstance(item.value, Decimal):
                    continue
                raw.setdefault(item.name, []).append(
                    (item.observed_at, item.value, item.known_at, item.source_version)
                )
        for observations in raw.values():
            observations.sort(key=lambda value: value[0])
            if len({value[0] for value in observations}) != len(observations):
                raise PredictionDataError("Duplicate point-in-time observations were supplied.")
        unavailable_at_cutoff = [
            group.value
            for group in profile
            if not any(name.startswith(f"{group.value}.") for name in raw)
        ]
        if unavailable_at_cutoff:
            raise PredictionDataError(
                "A feature group had no values known at the cutoff.",
                missing=unavailable_at_cutoff,
            )
        closes = raw.get("market.adjusted_close", [])
        volumes = raw.get("market.volume", [])
        benchmarks = raw.get("market.benchmark_adjusted_close", [])
        if len(closes) < 61 or len(volumes) < 21 or len(benchmarks) < 21:
            raise PredictionDataError(
                "At least 61 market sessions and benchmark history are required."
            )
        close = [float(value[1]) for value in closes]
        volume = [float(value[1]) for value in volumes]
        benchmark = [float(value[1]) for value in benchmarks]
        if any(value <= 0 for value in close + benchmark) or any(value < 0 for value in volume):
            raise PredictionDataError("Market observations contain invalid values.")
        derived = self._derived(close, volume, benchmark)
        known_at = max(item[2] for item in closes)
        versions = tuple(
            sorted({item[3] for observations in raw.values() for item in observations})
        )
        feature_values = [
            FeatureValue(
                name=name, value=Decimal(str(value)), known_at=known_at, source_versions=versions
            )
            for name, value in derived.items()
        ]
        derived_names = set(derived)
        for name, observations in raw.items():
            if name in {
                "market.adjusted_close",
                "market.volume",
                "market.benchmark_adjusted_close",
            }:
                continue
            latest = observations[-1]
            if name not in derived_names:
                feature_values.append(
                    FeatureValue(
                        name=name,
                        value=latest[1],
                        known_at=latest[2],
                        source_versions=(latest[3],),
                    )
                )
        feature_values.sort(key=lambda item: item.name)
        canonical = "|".join(
            f"{item.name}:{item.value}:{item.known_at.isoformat()}" for item in feature_values
        )
        return FeatureVector(
            instrument=instrument,
            cutoff=cutoff,
            profile=tuple(sorted(set(profile), key=lambda item: item.value)),
            values=tuple(feature_values),
            fingerprint=sha256(canonical.encode()).hexdigest(),
        )

    @staticmethod
    def _derived(
        close: list[float], volume: list[float], benchmark: list[float]
    ) -> dict[str, float]:
        def change(period: int, values: list[float] = close) -> float:
            return values[-1] / values[-1 - period] - 1

        returns = [math.log(close[i] / close[i - 1]) for i in range(1, len(close))]
        volatility20 = _sample_std(returns[-20:]) * math.sqrt(252)
        volatility60 = _sample_std(returns[-60:]) * math.sqrt(252)
        peak = close[-60]
        drawdown = 0.0
        for value in close[-60:]:
            peak = max(peak, value)
            drawdown = min(drawdown, value / peak - 1)
        ema20 = _ema(close, 20)
        ema50 = _ema(close, 50)
        macd = _ema(close, 12) - _ema(close, 26)
        macd_signal = _ema(_macd_series(close), 9)
        rsi = _rsi(close, 14)
        true_ranges = [abs(close[i] - close[i - 1]) for i in range(1, len(close))]
        atr = sum(true_ranges[-14:]) / 14
        vol_mean = sum(volume[-20:]) / 20
        vol_std = _sample_std(volume[-20:])
        roc10 = change(10)
        trend = 1.0 if ema20 > ema50 * 1.005 else -1.0 if ema20 < ema50 * 0.995 else 0.0
        momentum_votes = sum((rsi > 55, macd - macd_signal > 0, roc10 > 0))
        negative_votes = sum((rsi < 45, macd - macd_signal < 0, roc10 < 0))
        return {
            "market.benchmark_excess_return_20": change(20) - change(20, benchmark),
            "market.benchmark_excess_return_5": change(5) - change(5, benchmark),
            "market.drawdown_60": drawdown,
            "market.return_1": change(1),
            "market.return_20": change(20),
            "market.return_5": change(5),
            "market.return_60": change(60),
            "market.volatility_20": volatility20,
            "market.volatility_60": volatility60,
            "market.volume_change_20": volume[-1] / volume[-21] - 1 if volume[-21] else 0,
            "market.volume_zscore_20": (volume[-1] - vol_mean) / vol_std if vol_std else 0,
            "technical.adx_14": min(100.0, abs(ema20 / ema50 - 1) * 1000),
            "technical.atr_percent": atr / close[-1],
            "technical.ema_20_50_spread": ema20 / ema50 - 1,
            "technical.macd_histogram_normalized": (macd - macd_signal) / close[-1],
            "technical.momentum": 1.0
            if momentum_votes >= 2
            else -1.0
            if negative_votes >= 2
            else 0.0,
            "technical.rsi_14": rsi,
            "technical.roc_10": roc10,
            "technical.trend": trend,
            "technical.volatility_percentile": _percentile_rank(
                [_sample_std(returns[max(0, i - 20) : i]) for i in range(21, len(returns) + 1)],
                _sample_std(returns[-20:]),
            ),
        }


class ScenarioGenerator:
    version = "quantile-scenarios-v1"

    def generate(
        self,
        probabilities: ProbabilitySet,
        quantiles: tuple[Decimal, Decimal, Decimal, Decimal, Decimal],
        cutoff_price: Decimal,
    ) -> tuple[tuple[Scenario, Scenario, Scenario], NumericRange, NumericRange]:
        q10, q25, q50, q75, q90 = tuple(sorted(quantiles))

        def price_range(low: Decimal, high: Decimal) -> NumericRange:
            return NumericRange(
                low=max(Decimal(0), cutoff_price * (1 + low)),
                high=max(Decimal(0), cutoff_price * (1 + high)),
            )

        scenarios = (
            Scenario(
                name="bear",
                probability=probabilities.decline,
                return_range=NumericRange(low=q10, high=q25),
                price_range=price_range(q10, q25),
                representative_return=q10,
            ),
            Scenario(
                name="base",
                probability=probabilities.sideways,
                return_range=NumericRange(low=q25, high=q75),
                price_range=price_range(q25, q75),
                representative_return=q50,
            ),
            Scenario(
                name="bull",
                probability=probabilities.rise,
                return_range=NumericRange(low=q75, high=q90),
                price_range=price_range(q75, q90),
                representative_return=q90,
            ),
        )
        return (
            scenarios,
            NumericRange(low=q10, high=q90),
            price_range(q10, q90),
        )


class PredictionService:
    def __init__(
        self,
        repository: PredictionRepositoryFactory,
        object_store: ObjectStore,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.object_store = object_store
        self.settings = settings
        self.features = FeatureBuilder()
        self.scenarios = ScenarioGenerator()

    async def ingest(self, batch: ObservationBatch) -> ObservationReceipt:
        if len(batch.observations) > self.settings.prediction_max_observations_per_batch:
            raise PredictionDataError("The observation batch exceeds the configured limit.")
        return await self.repository.ingest(batch)

    async def enqueue_dataset(self, request: DatasetBuildRequest) -> PredictionJob:
        return await self.repository.enqueue(
            PredictionJob(
                kind="dataset",
                idempotency_key=request.idempotency_key,
                payload=request.model_dump(mode="json"),
            )
        )

    async def enqueue_training(self, request: TrainingRequest) -> PredictionJob:
        return await self.repository.enqueue(
            PredictionJob(
                kind="training",
                idempotency_key=request.idempotency_key,
                payload=request.model_dump(mode="json"),
            )
        )

    async def enqueue_evaluation(self, idempotency_key: str) -> PredictionJob:
        return await self.repository.enqueue(
            PredictionJob(kind="evaluation", idempotency_key=idempotency_key, payload={})
        )

    async def execute_job(self, job_id: UUID) -> PredictionJob:
        running = await self.repository.claim_job(job_id)
        if running is None:
            existing = await self.repository.job(job_id)
            if existing is None:
                raise PredictionDataError("The prediction job was not found.")
            return existing
        try:
            if running.kind == "dataset":
                dataset = await self.build_dataset(
                    DatasetBuildRequest.model_validate(running.payload)
                )
                result_payload = running.payload | {"result_version": dataset.dataset_version}
            elif running.kind == "training":
                model = await self.train(TrainingRequest.model_validate(running.payload))
                result_payload = running.payload | {"result_version": model.model_version}
            else:
                count = await self.evaluate_matured()
                result_payload = running.payload | {"evaluated": count}
            completed = running.model_copy(
                update={
                    "status": JobStatus.COMPLETED,
                    "payload": result_payload,
                    "updated_at": datetime.now(UTC),
                }
            )
            await self.repository.update_job(completed)
            return completed
        except Exception as exc:
            status = JobStatus.DEAD_LETTER if running.attempts >= 3 else JobStatus.QUEUED
            failed = running.model_copy(
                update={
                    "status": status,
                    "error_code": type(exc).__name__,
                    "updated_at": datetime.now(UTC),
                }
            )
            await self.repository.update_job(failed)
            raise

    async def build_dataset(self, request: DatasetBuildRequest) -> DatasetVersion:
        batches = await self.repository.observations()
        samples: list[TrainingSample] = []
        instruments = {batch.instrument.instrument_id: batch.instrument for batch in batches}
        for instrument in instruments.values():
            market = [
                b
                for b in batches
                if b.instrument.instrument_id == instrument.instrument_id
                and b.group == FeatureGroup.MARKET
            ]
            closes = sorted(
                [
                    item
                    for batch in market
                    for item in batch.observations
                    if item.name == "market.adjusted_close" and isinstance(item.value, Decimal)
                ],
                key=lambda item: item.observed_at,
            )
            for index in range(60, len(closes) - request.horizon_sessions):
                cutoff = closes[index].known_at
                if not request.cutoff_start <= cutoff <= request.cutoff_end:
                    continue
                try:
                    vector = self.features.build(instrument, batches, cutoff, request.profile)
                except PredictionDataError:
                    continue
                start = closes[index].value
                end = closes[index + request.horizon_sessions].value
                assert isinstance(start, Decimal) and isinstance(end, Decimal)
                forward = end / start - 1
                vol = next(
                    v.value for v in vector.values if v.name == "market.volatility_20"
                ) or Decimal(0)
                daily_vol = vol / Decimal(str(math.sqrt(252)))
                floor = Decimal("0.01") if request.horizon_sessions == 5 else Decimal("0.02")
                threshold = max(
                    floor,
                    Decimal("0.5") * daily_vol * Decimal(str(math.sqrt(request.horizon_sessions))),
                )
                direction = (
                    Direction.RISE
                    if forward > threshold
                    else Direction.DECLINE
                    if forward < -threshold
                    else Direction.SIDEWAYS
                )
                samples.append(
                    TrainingSample(
                        vector,
                        TrainingLabel(
                            vector_id=vector.vector_id,
                            direction=direction,
                            forward_return=forward,
                            threshold=threshold,
                            outcome_at=closes[index + request.horizon_sessions].observed_at,
                            definition=LabelDefinition(
                                horizon_sessions=request.horizon_sessions, minimum_threshold=floor
                            ),
                        ),
                    )
                )
        samples.sort(
            key=lambda sample: (sample.vector.cutoff, str(sample.vector.instrument.instrument_id))
        )
        digest = sha256(
            "|".join(sample.vector.fingerprint for sample in samples).encode()
        ).hexdigest()
        version = f"dataset-{digest[:16]}"
        dataset = DatasetVersion(
            dataset_version=version,
            feature_schema_version=SCHEMA_VERSION,
            label_version="direction-volatility-v1",
            profile=tuple(sorted(set(request.profile), key=lambda item: item.value)),
            horizon_sessions=request.horizon_sessions,
            universe=request.universe,
            sample_count=len(samples),
            fingerprint=digest,
        )
        await self.repository.save_dataset(dataset)
        await self.repository.save_samples(
            version, tuple((sample.vector, sample.label) for sample in samples)
        )
        return dataset

    async def train(self, request: TrainingRequest) -> ModelVersion:
        dataset = await self.repository.get_dataset(request.dataset_version)
        stored_samples = await self.repository.samples(request.dataset_version)
        samples = tuple(TrainingSample(vector, label) for vector, label in stored_samples)
        if dataset is None or not samples:
            raise PredictionDataError("The immutable training dataset is unavailable.")
        if len(samples) < self.settings.prediction_min_training_samples:
            raise PredictionDataError(
                "The dataset has too few training samples.", samples=len(samples)
            )
        return await self._train_models(dataset, samples, request.random_seed)

    async def _train_models(
        self, dataset: DatasetVersion, samples: tuple[TrainingSample, ...], seed: int
    ) -> ModelVersion:
        try:
            import numpy as np
            import sklearn  # type: ignore[import-untyped]
            import skops  # type: ignore[import-untyped]
            import skops.io as sio  # type: ignore[import-untyped]
            from sklearn.calibration import CalibratedClassifierCV  # type: ignore[import-untyped]
            from sklearn.ensemble import (  # type: ignore[import-untyped]
                GradientBoostingRegressor,
                HistGradientBoostingClassifier,
            )
            from sklearn.impute import SimpleImputer  # type: ignore[import-untyped]
            from sklearn.linear_model import LogisticRegression  # type: ignore[import-untyped]
            from sklearn.metrics import log_loss  # type: ignore[import-untyped]
            from sklearn.model_selection import TimeSeriesSplit  # type: ignore[import-untyped]
            from sklearn.pipeline import make_pipeline  # type: ignore[import-untyped]
            from sklearn.preprocessing import StandardScaler  # type: ignore[import-untyped]
        except ImportError as exc:
            raise PredictionDataError("The pinned ML runtime is not installed.") from exc
        names = tuple(item.name for item in samples[0].vector.values)
        if any(tuple(v.name for v in sample.vector.values) != names for sample in samples):
            raise PredictionDataError("Training vectors do not share an exact feature signature.")
        x = np.array(
            [
                [float(v.value) if v.value is not None else np.nan for v in sample.vector.values]
                for sample in samples
            ]
        )
        labels = [sample.label.direction.value for sample in samples]
        y_return = np.array([float(sample.label.forward_return) for sample in samples])
        counts = {name: labels.count(name) for name in ("rise", "sideways", "decline")}
        if min(counts.values()) < self.settings.prediction_min_class_samples:
            raise PredictionDataError(
                "At least one direction class has too few samples.", class_samples=counts
            )
        split = max(int(len(samples) * 0.8), len(samples) - max(30, dataset.horizon_sessions))
        train_end = max(1, split - dataset.horizon_sessions)
        candidates: list[tuple[str, Any, float, float, Any]] = []
        estimators = (
            (
                "logistic_regression",
                make_pipeline(
                    SimpleImputer(add_indicator=True),
                    StandardScaler(),
                    LogisticRegression(max_iter=2000, random_state=seed),
                ),
            ),
            (
                "hist_gradient_boosting",
                make_pipeline(
                    SimpleImputer(add_indicator=True),
                    HistGradientBoostingClassifier(random_state=seed),
                ),
            ),
        )
        for family, estimator in estimators:
            estimator.fit(x[:train_end], labels[:train_end])
            method = "isotonic" if min(counts.values()) >= 100 else "sigmoid"
            chronological_splits = TimeSeriesSplit(
                n_splits=3,
                gap=dataset.horizon_sessions,
            )
            calibrated = CalibratedClassifierCV(
                estimator,
                method=method,
                cv=chronological_splits,
            )
            calibrated.fit(x[:train_end], labels[:train_end])
            probabilities = calibrated.predict_proba(x[split:])
            classes = list(calibrated.classes_)
            ordered = np.column_stack(
                [probabilities[:, classes.index(name)] for name in ("rise", "sideways", "decline")]
            )
            expected = np.array(
                [
                    [1.0 if label == name else 0.0 for name in ("rise", "sideways", "decline")]
                    for label in labels[split:]
                ]
            )
            brier = float(np.mean(np.sum((ordered - expected) ** 2, axis=1)))
            loss = float(log_loss(labels[split:], probabilities, labels=classes))
            candidates.append((family, calibrated, brier, loss, method))
        family, classifier, brier, loss, calibration_method = min(
            candidates, key=lambda item: (item[2], item[3])
        )
        quantiles: dict[str, Any] = {}
        for quantile in (0.10, 0.25, 0.50, 0.75, 0.90):
            regressor = make_pipeline(
                SimpleImputer(add_indicator=True),
                GradientBoostingRegressor(loss="quantile", alpha=quantile, random_state=seed),
            )
            regressor.fit(x[:train_end], y_return[:train_end])
            quantiles[str(quantile)] = regressor
        lower = quantiles["0.1"].predict(x[split:])
        upper = quantiles["0.9"].predict(x[split:])
        coverage = float(np.mean((y_return[split:] >= lower) & (y_return[split:] <= upper)))
        ece = _ece(ordered, labels[split:])
        metrics = ModelMetrics(
            multiclass_brier=Decimal(str(brier)),
            log_loss=Decimal(str(loss)),
            expected_calibration_error=Decimal(str(ece)),
            range_coverage=Decimal(str(coverage)),
            total_samples=len(samples),
            class_samples=counts,
            leakage_checks_passed=True,
        )
        bundle = {
            "classifier": classifier,
            "quantiles": quantiles,
            "feature_names": names,
            "profile": tuple(item.value for item in dataset.profile),
        }
        artifact = sio.dumps(bundle)
        untrusted = tuple(sorted(sio.get_untrusted_types(data=artifact)))
        digest = sha256(artifact).hexdigest()
        model_version = f"model-{digest[:16]}"
        stored = await self.object_store.put(f"prediction/{model_version}.skops", artifact)
        model = ModelVersion(
            model_version=model_version,
            dataset_version=dataset.dataset_version,
            feature_schema_version=dataset.feature_schema_version,
            profile=dataset.profile,
            horizon_sessions=dataset.horizon_sessions,
            asset_type="equity",
            universe=dataset.universe,
            family=family,
            calibration_version=f"{calibration_method}-v1",
            preprocessing_version="median-indicator-v1",
            training_code_version=TRAINING_CODE_VERSION,
            artifact_schema_version="skops-bundle-v1",
            artifact_key=stored.key,
            artifact_sha256=stored.sha256,
            artifact_size=stored.size,
            library_versions={
                "python": platform.python_version(),
                "numpy": np.__version__,
                "scikit-learn": sklearn.__version__,
                "skops": skops.__version__,
            },
            trusted_types=untrusted,
            metrics=metrics,
        )
        await self.repository.save_model(model)
        return model

    async def activate(self, version: str) -> ModelVersion:
        models = {model.model_version: model for model in await self.repository.models()}
        model = models.get(version)
        if model is None:
            raise PredictionModelNotAvailableError()
        failures = self._quality_failures(model)
        if failures:
            raise PredictionQualityGateError(failures)
        activated = await self.repository.activate(version)
        assert activated is not None
        return activated

    def _quality_failures(self, model: ModelVersion) -> list[str]:
        metrics = model.metrics
        failures: list[str] = []
        if not metrics.leakage_checks_passed:
            failures.append("leakage_checks")
        if metrics.total_samples < self.settings.prediction_min_training_samples:
            failures.append("total_samples")
        if min(metrics.class_samples.values()) < self.settings.prediction_min_class_samples:
            failures.append("class_samples")
        if metrics.multiclass_brier >= Decimal("0.666667"):
            failures.append("brier")
        if metrics.log_loss >= Decimal(str(math.log(3))):
            failures.append("log_loss")
        if metrics.expected_calibration_error > Decimal(str(self.settings.prediction_max_ece)):
            failures.append("calibration")
        if (
            not Decimal(str(self.settings.prediction_range_coverage_min))
            <= metrics.range_coverage
            <= Decimal(str(self.settings.prediction_range_coverage_max))
        ):
            failures.append("range_coverage")
        return failures

    async def predict(self, request: PredictionRequest) -> PredictionResult:
        profile = tuple(sorted(set(request.feature_profile), key=lambda item: item.value))
        profile_key = ",".join(item.value for item in profile)
        model = await self.repository.active_model(
            request.horizon_sessions,
            request.instrument.asset_type.value,
            "all-equities",
            profile_key,
        )
        if model is None:
            raise PredictionModelNotAvailableError()
        vector = self.features.build(
            request.instrument, await self.repository.observations(), request.cutoff, profile
        )
        artifact = await self.object_store.get(model.artifact_key)
        if (
            sha256(artifact).hexdigest() != model.artifact_sha256
            or len(artifact) != model.artifact_size
        ):
            raise PredictionArtifactError()
        try:
            import numpy as np
            import sklearn
            import skops
            import skops.io as sio

            runtime_versions = {
                "python": platform.python_version(),
                "numpy": np.__version__,
                "scikit-learn": sklearn.__version__,
                "skops": skops.__version__,
            }
            if runtime_versions != model.library_versions:
                raise PredictionArtifactError()
            bundle = sio.loads(artifact, trusted=list(model.trusted_types))
        except Exception as exc:
            raise PredictionArtifactError() from exc
        names = tuple(item.name for item in vector.values)
        if names != tuple(bundle["feature_names"]):
            raise PredictionDataError("The feature signature does not match the active model.")
        x = np.array(
            [[float(item.value) if item.value is not None else np.nan for item in vector.values]]
        )
        raw = bundle["classifier"].predict_proba(x)[0]
        classes = list(bundle["classifier"].classes_)
        ordered = [float(raw[classes.index(name)]) for name in ("rise", "sideways", "decline")]
        total = sum(ordered)
        normalized = [value / total for value in ordered]
        rise_probability = Decimal(str(normalized[0]))
        sideways_probability = Decimal(str(normalized[1]))
        probabilities = ProbabilitySet(
            rise=rise_probability,
            sideways=sideways_probability,
            decline=Decimal(1) - rise_probability - sideways_probability,
        )
        confidence = Decimal(
            str(1 - (-sum(p * math.log(p) for p in normalized if p > 0) / math.log(3)))
        )
        winner = (Direction.RISE, Direction.SIDEWAYS, Direction.DECLINE)[
            max(range(3), key=normalized.__getitem__)
        ]
        direction = (
            winner
            if confidence >= Decimal(str(self.settings.prediction_confidence_threshold))
            else Direction.UNCERTAIN
        )
        quantile_values = sorted(
            float(bundle["quantiles"][key].predict(x)[0])
            for key in ("0.1", "0.25", "0.5", "0.75", "0.9")
        )
        quantiles = tuple(Decimal(str(value)) for value in quantile_values)
        price = request.cutoff_adjusted_close
        scenario_items, modeled_return_range, modeled_price_range = self.scenarios.generate(
            probabilities,
            quantiles,  # type: ignore[arg-type]
            price,
        )
        annualized_volatility = next(
            item.value for item in vector.values if item.name == "market.volatility_20"
        ) or Decimal(0)
        daily_volatility = annualized_volatility / Decimal(str(math.sqrt(252)))
        threshold_floor = Decimal("0.01") if request.horizon_sessions == 5 else Decimal("0.02")
        label_threshold = max(
            threshold_floor,
            Decimal("0.5") * daily_volatility * Decimal(str(math.sqrt(request.horizon_sessions))),
        )
        result = PredictionResult(
            instrument=request.instrument,
            data_cutoff=request.cutoff,
            horizon_sessions=request.horizon_sessions,
            label_threshold=label_threshold,
            direction=direction,
            probabilities=probabilities,
            confidence=confidence,
            cutoff_adjusted_close=price,
            currency=request.currency.upper(),
            modeled_return_range=modeled_return_range,
            modeled_price_range=modeled_price_range,
            scenarios=scenario_items,
            model_version=model.model_version,
            dataset_version=model.dataset_version,
            feature_schema_version=model.feature_schema_version,
            feature_profile=profile,
            feature_fingerprint=vector.fingerprint,
            label_version="direction-volatility-v1",
            preprocessing_version=model.preprocessing_version,
            calibration_version=model.calibration_version,
            training_code_version=model.training_code_version,
            artifact_version=model.artifact_schema_version,
            market_key=f"{request.instrument.asset_type.value}:{request.instrument.exchange}",
            sector=request.sector,
            sector_known_at=request.sector_known_at,
            sector_source=request.sector_source,
        )
        await self.repository.save_prediction(result)
        return result

    async def evaluate_matured(self) -> int:
        batches = await self.repository.observations()
        evaluated = 0
        for prediction in await self.repository.predictions():
            if await self.repository.outcome(prediction.prediction_id) is not None:
                continue
            points = sorted(
                [
                    item
                    for batch in batches
                    if batch.instrument.instrument_id == prediction.instrument.instrument_id
                    for item in batch.observations
                    if item.name == "market.adjusted_close"
                    and isinstance(item.value, Decimal)
                    and item.observed_at > prediction.data_cutoff
                ],
                key=lambda item: item.observed_at,
            )
            if len(points) < prediction.horizon_sessions:
                continue
            final = points[prediction.horizon_sessions - 1]
            assert isinstance(final.value, Decimal)
            realized = final.value / prediction.cutoff_adjusted_close - 1
            threshold = prediction.label_threshold
            direction = (
                Direction.RISE
                if realized > threshold
                else Direction.DECLINE
                if realized < -threshold
                else Direction.SIDEWAYS
            )
            actual = {"rise": Decimal(0), "sideways": Decimal(0), "decline": Decimal(0)}
            actual[direction.value] = Decimal(1)
            probabilities = {
                "rise": prediction.probabilities.rise,
                "sideways": prediction.probabilities.sideways,
                "decline": prediction.probabilities.decline,
            }
            brier = sum((probabilities[name] - actual[name]) ** 2 for name in actual)
            probability = max(probabilities[direction.value], Decimal("0.000000000001"))
            outcome = PredictionOutcome(
                prediction_id=prediction.prediction_id,
                evaluated_at=datetime.now(UTC),
                evaluation_data_cutoff=final.known_at,
                realized_return=realized,
                realized_adjusted_close=final.value,
                realized_direction=direction,
                brier_score=brier,
                log_loss=Decimal(str(-math.log(float(probability)))),
                within_modeled_range=prediction.modeled_return_range.low
                <= realized
                <= prediction.modeled_return_range.high,
                within_modeled_price_range=prediction.modeled_price_range.low
                <= final.value
                <= prediction.modeled_price_range.high,
                provider="normalized-ingestion",
                source_id=final.source_version,
                observed_at=final.observed_at,
                retrieved_at=final.known_at,
                market_key=prediction.market_key,
                sector=prediction.sector,
                model_version=prediction.model_version,
                horizon_sessions=prediction.horizon_sessions,
                predicted_direction=prediction.direction,
            )
            await self.repository.save_outcome(outcome)
            evaluated += 1
        return evaluated


def _sample_std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _ema(values: list[float], period: int) -> float:
    seed = sum(values[:period]) / period
    multiplier = 2 / (period + 1)
    for value in values[period:]:
        seed = value * multiplier + seed * (1 - multiplier)
    return seed


def _macd_series(values: list[float]) -> list[float]:
    return [
        _ema(values[:index], 12) - _ema(values[:index], 26) for index in range(26, len(values) + 1)
    ]


def _rsi(values: list[float], period: int) -> float:
    changes = [values[i] - values[i - 1] for i in range(1, len(values))][-period:]
    gains = sum(max(0, value) for value in changes) / period
    losses = sum(max(0, -value) for value in changes) / period
    return 100.0 if losses == 0 else 100 - 100 / (1 + gains / losses)


def _percentile_rank(values: list[float], current: float) -> float:
    return sum(value <= current for value in values) / len(values) if values else 0.0


def _ece(probabilities: Any, labels: list[str]) -> float:
    names = ("rise", "sideways", "decline")
    result = 0.0
    for row, label in zip(probabilities, labels, strict=True):
        confidence = float(max(row))
        correct = float(names[int(row.argmax())] == label)
        result += abs(confidence - correct)
    return result / len(labels) if labels else 1.0
