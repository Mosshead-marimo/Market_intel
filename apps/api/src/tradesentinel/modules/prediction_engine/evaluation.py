from __future__ import annotations

import asyncio
import math
from collections import defaultdict
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal, cast
from uuid import uuid4

from tradesentinel.domain.prediction import (
    CalibrationBin,
    CohortPerformance,
    ConfusionMatrix,
    Direction,
    EvaluationAttempt,
    EvaluationSchedule,
    EvaluationState,
    ModelPerformanceReport,
    PerformanceFilter,
    PerformanceMetrics,
    PerformanceRebuildResult,
    PredictionEvaluation,
    PredictionOutcome,
    PredictionResult,
)
from tradesentinel.modules.prediction_engine.errors import PredictionDataError
from tradesentinel.modules.prediction_engine.repository import PredictionRepositoryFactory
from tradesentinel.platform.config import Settings
from tradesentinel.providers.contracts import (
    InstrumentReference,
    PriceHistoryRequest,
    ProviderContext,
    ProviderMetadata,
)
from tradesentinel.providers.errors import ProviderError
from tradesentinel.providers.interfaces import MarketDataProvider

ZERO = Decimal(0)
ONE = Decimal(1)
PREDICTED = (Direction.RISE, Direction.SIDEWAYS, Direction.DECLINE, Direction.UNCERTAIN)
ACTUAL = (Direction.RISE, Direction.SIDEWAYS, Direction.DECLINE)


class PredictionEvaluationService:
    def __init__(
        self,
        repository_factory: PredictionRepositoryFactory,
        market_data_provider: MarketDataProvider,
        settings: Settings,
    ) -> None:
        self.repository = repository_factory
        self.market_data = market_data_provider
        self.settings = settings

    async def evaluate_due(self, now: datetime | None = None) -> int:
        current = now or datetime.now(UTC)
        processed = 0
        for candidate in await self.repository.due_schedules(current):
            claimed = await self.repository.claim_schedule(candidate.schedule_id)
            if claimed is None:
                continue
            try:
                await self.evaluate(claimed, current)
            except asyncio.CancelledError:
                raise
            processed += 1
        return processed

    async def evaluate(
        self, schedule: EvaluationSchedule, now: datetime | None = None
    ) -> PredictionEvaluation:
        current = now or datetime.now(UTC)
        prediction = await self.repository.prediction(schedule.prediction_id)
        if prediction is None:
            raise PredictionDataError("The scheduled prediction was not found.")
        existing = await self.repository.outcome(schedule.prediction_id)
        if existing is not None:
            completed = schedule.model_copy(
                update={
                    "state": EvaluationState.EVALUATED,
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "updated_at": current,
                }
            )
            await self.repository.update_schedule(completed)
            return PredictionEvaluation(prediction=prediction, schedule=completed, outcome=existing)

        started = current
        provider_name: str | None = None
        try:
            history = await self.market_data.get_history(
                ProviderContext(
                    request_id=uuid4(), correlation_id=schedule.schedule_id, causation_id=None
                ),
                PriceHistoryRequest(
                    instrument=InstrumentReference(
                        symbol=prediction.instrument.symbol,
                        exchange=prediction.instrument.exchange,
                        identifier=str(prediction.instrument.instrument_id),
                    ),
                    start=prediction.data_cutoff,
                    end=current,
                    interval="1d",
                ),
            )
            provider_name = history.metadata.provider
            if history.currency.upper() != prediction.currency.upper():
                raise PredictionDataError("Evaluation history currency does not match prediction.")
            if history.instrument.symbol.casefold() != prediction.instrument.symbol.casefold():
                raise PredictionDataError(
                    "Evaluation history instrument does not match prediction."
                )
            if (
                history.instrument.exchange is not None
                and history.instrument.exchange.casefold()
                != prediction.instrument.exchange.casefold()
            ):
                raise PredictionDataError("Evaluation history exchange does not match prediction.")
            bars = tuple(bar for bar in history.bars if bar.timestamp > prediction.data_cutoff)
            if len(bars) < prediction.horizon_sessions:
                waiting = self._reschedule(schedule, current, "PREDICTION_OUTCOME_NOT_MATURE")
                await self._record_attempt(waiting, started, current, provider_name)
                return PredictionEvaluation(prediction=prediction, schedule=waiting)
            final = bars[prediction.horizon_sessions - 1]
            if final.adjusted_close <= 0:
                raise PredictionDataError("Evaluation adjusted close must be positive.")
            outcome = _outcome(prediction, final.adjusted_close, final.timestamp, history.metadata)
            await self.repository.save_outcome(outcome)
            completed = schedule.model_copy(
                update={
                    "state": EvaluationState.EVALUATED,
                    "next_check_at": current,
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "last_error_code": None,
                    "updated_at": current,
                }
            )
            await self.repository.update_schedule(completed)
            await self._record_attempt(completed, started, current, provider_name)
            await self.rebuild_metrics()
            return PredictionEvaluation(prediction=prediction, schedule=completed, outcome=outcome)
        except asyncio.CancelledError:
            raise
        except (ProviderError, PredictionDataError) as exc:
            code = getattr(exc, "code", "PREDICTION_EVALUATION_DATA_INVALID")
            retrying = self._reschedule(schedule, current, str(code))
            await self._record_attempt(retrying, started, current, provider_name)
            return PredictionEvaluation(prediction=prediction, schedule=retrying)

    def _reschedule(
        self, schedule: EvaluationSchedule, now: datetime, error_code: str
    ) -> EvaluationSchedule:
        overdue_at = schedule.expected_maturity_at + timedelta(
            days=self.settings.prediction_evaluation_grace_days
        )
        state = (
            EvaluationState.OVERDUE
            if now >= overdue_at
            else (
                EvaluationState.WAITING
                if error_code == "PREDICTION_OUTCOME_NOT_MATURE"
                else EvaluationState.RETRYING
            )
        )
        delay = (
            self.settings.prediction_evaluation_overdue_poll_seconds
            if state == EvaluationState.OVERDUE
            else self.settings.prediction_evaluation_poll_seconds
        )
        updated = schedule.model_copy(
            update={
                "state": state,
                "next_check_at": now + timedelta(seconds=delay),
                "lease_owner": None,
                "lease_expires_at": None,
                "last_error_code": error_code,
                "updated_at": now,
            }
        )
        return updated

    async def _record_attempt(
        self,
        schedule: EvaluationSchedule,
        started: datetime,
        completed: datetime,
        provider: str | None,
    ) -> None:
        await self.repository.update_schedule(schedule)
        await self.repository.save_evaluation_attempt(
            EvaluationAttempt(
                schedule_id=schedule.schedule_id,
                prediction_id=schedule.prediction_id,
                started_at=started,
                completed_at=completed,
                state=schedule.state,
                error_code=schedule.last_error_code,
                provider=provider,
            )
        )

    async def rebuild_metrics(self) -> PerformanceRebuildResult:
        report = await self.performance(PerformanceFilter())
        aggregates = {
            f"{cohort.dimension}:{cohort.key}": cohort.model_dump(mode="json")
            for cohort in report.cohorts
        }
        aggregates["overall:all"] = report.overall.model_dump(mode="json")
        await self.repository.replace_performance_aggregates(aggregates)
        return PerformanceRebuildResult(
            outcomes_processed=report.overall.sample_count,
            aggregates_written=len(aggregates),
        )

    async def performance(self, filters: PerformanceFilter) -> ModelPerformanceReport:
        predictions = {item.prediction_id: item for item in await self.repository.predictions()}
        pairs = [
            (predictions[outcome.prediction_id], outcome)
            for outcome in await self.repository.outcomes()
            if outcome.prediction_id in predictions
            and _matches(predictions[outcome.prediction_id], outcome, filters)
        ]
        schedules = await self.repository.schedules()
        cohorts = _cohorts(pairs)
        metrics, matrix, calibration = _metrics(pairs)
        counts: defaultdict[str, int] = defaultdict(int)
        for item in schedules:
            counts[item.state.value] += 1
        return ModelPerformanceReport(
            data_cutoff=max((outcome.evaluated_at for _, outcome in pairs), default=None),
            filters=filters,
            overall=metrics,
            confusion_matrix=matrix,
            calibration=calibration,
            cohorts=cohorts,
            scheduled=counts[EvaluationState.SCHEDULED.value],
            waiting=counts[EvaluationState.WAITING.value],
            retrying=counts[EvaluationState.RETRYING.value],
            overdue=counts[EvaluationState.OVERDUE.value],
        )


def _outcome(
    prediction: PredictionResult,
    close: Decimal,
    observed_at: datetime,
    metadata: ProviderMetadata,
) -> PredictionOutcome:
    realized = close / prediction.cutoff_adjusted_close - ONE
    direction = (
        Direction.RISE
        if realized > prediction.label_threshold
        else Direction.DECLINE
        if realized < -prediction.label_threshold
        else Direction.SIDEWAYS
    )
    probabilities = prediction.probabilities.model_dump()
    actual = {name: Decimal(name == direction.value) for name in ("rise", "sideways", "decline")}
    brier = sum((probabilities[name] - actual[name]) ** 2 for name in actual)
    probability = max(probabilities[direction.value], Decimal("0.000000000001"))
    return PredictionOutcome(
        prediction_id=prediction.prediction_id,
        evaluated_at=datetime.now(UTC),
        evaluation_data_cutoff=metadata.retrieved_at,
        realized_return=realized,
        realized_adjusted_close=close,
        realized_direction=direction,
        brier_score=brier,
        log_loss=Decimal(str(-math.log(float(probability)))),
        within_modeled_range=prediction.modeled_return_range.low
        <= realized
        <= prediction.modeled_return_range.high,
        within_modeled_price_range=prediction.modeled_price_range.low
        <= close
        <= prediction.modeled_price_range.high,
        provider=metadata.provider,
        source_id=metadata.source_id,
        observed_at=observed_at,
        retrieved_at=metadata.retrieved_at,
        market_key=prediction.market_key,
        sector=prediction.sector,
        model_version=prediction.model_version,
        horizon_sessions=prediction.horizon_sessions,
        predicted_direction=prediction.direction,
    )


def _matches(
    prediction: PredictionResult, outcome: PredictionOutcome, filters: PerformanceFilter
) -> bool:
    asset_type, exchange = prediction.market_key.split(":", 1)
    return not (
        (filters.model_version and prediction.model_version != filters.model_version)
        or (filters.horizon_sessions and prediction.horizon_sessions != filters.horizon_sessions)
        or (filters.asset_type and asset_type != filters.asset_type)
        or (filters.exchange and exchange != filters.exchange)
        or (filters.sector and prediction.sector != filters.sector)
        or (filters.start and outcome.evaluated_at < filters.start)
        or (filters.end and outcome.evaluated_at >= filters.end)
    )


def _metrics(
    pairs: Iterable[tuple[PredictionResult, PredictionOutcome]],
) -> tuple[PerformanceMetrics, ConfusionMatrix, tuple[CalibrationBin, ...]]:
    values = tuple(pairs)
    matrix = [[0, 0, 0] for _ in PREDICTED]
    calls = correct = 0
    for prediction, outcome in values:
        matrix[PREDICTED.index(prediction.direction)][ACTUAL.index(outcome.realized_direction)] += 1
        if prediction.direction != Direction.UNCERTAIN:
            calls += 1
            correct += int(prediction.direction == outcome.realized_direction)
    bins = _calibration(values)
    ece = ZERO
    total_bin_samples = sum(item.samples for item in bins)
    for item in bins:
        if (
            item.samples
            and item.mean_probability is not None
            and item.observed_frequency is not None
        ):
            ece += (
                Decimal(item.samples)
                / Decimal(total_bin_samples)
                * abs(item.mean_probability - item.observed_frequency)
            )
    widths = [
        (prediction.modeled_price_range.high - prediction.modeled_price_range.low)
        / prediction.cutoff_adjusted_close
        for prediction, _ in values
    ]
    count = len(values)
    metrics = PerformanceMetrics(
        sample_count=count,
        directional_calls=calls,
        directional_coverage=Decimal(calls) / Decimal(count) if count else None,
        directional_accuracy=Decimal(correct) / Decimal(calls) if calls else None,
        multiclass_brier=_average(item.brier_score for _, item in values),
        log_loss=_average(item.log_loss for _, item in values),
        expected_calibration_error=ece if count else None,
        return_range_accuracy=_average(Decimal(item.within_modeled_range) for _, item in values),
        price_range_accuracy=_average(
            Decimal(item.within_modeled_price_range) for _, item in values
        ),
        normalized_interval_width=_average(widths),
    )
    return metrics, ConfusionMatrix(counts=tuple(tuple(row) for row in matrix)), bins


def _calibration(
    values: tuple[tuple[PredictionResult, PredictionOutcome], ...],
) -> tuple[CalibrationBin, ...]:
    result: list[CalibrationBin] = []
    class_names: tuple[Literal["rise", "sideways", "decline"], ...] = (
        "rise",
        "sideways",
        "decline",
    )
    for class_name in class_names:
        for index in range(10):
            low = Decimal(index) / Decimal(10)
            high = Decimal(index + 1) / Decimal(10)
            samples = []
            for prediction, outcome in values:
                probability = getattr(prediction.probabilities, class_name)
                if low <= probability < high or (index == 9 and probability == ONE):
                    samples.append(
                        (probability, Decimal(outcome.realized_direction.value == class_name))
                    )
            result.append(
                CalibrationBin(
                    class_name=class_name,
                    lower_bound=low,
                    upper_bound=high,
                    samples=len(samples),
                    mean_probability=_average(item[0] for item in samples),
                    observed_frequency=_average(item[1] for item in samples),
                )
            )
    return tuple(result)


def _cohorts(
    values: list[tuple[PredictionResult, PredictionOutcome]],
) -> tuple[CohortPerformance, ...]:
    groups: dict[tuple[str, str], list[tuple[PredictionResult, PredictionOutcome]]] = defaultdict(
        list
    )
    now = datetime.now(UTC)
    for pair in values:
        prediction, outcome = pair
        groups[("model", prediction.model_version)].append(pair)
        groups[("market", prediction.market_key)].append(pair)
        groups[("horizon", str(prediction.horizon_sessions))].append(pair)
        groups[("calendar", f"day:{outcome.evaluated_at.date().isoformat()}")].append(pair)
        if prediction.sector:
            groups[("sector", prediction.sector)].append(pair)
        for days in (30, 90, 365):
            if outcome.evaluated_at >= now - timedelta(days=days):
                groups[("calendar", f"{days}d")].append(pair)
    ordered = sorted(values, key=lambda item: item[1].evaluated_at, reverse=True)
    for count in (50, 100, 250):
        groups[("count", str(count))].extend(ordered[:count])
    return tuple(
        CohortPerformance(
            dimension=cast(
                Literal["overall", "model", "market", "sector", "horizon", "calendar", "count"],
                dimension,
            ),
            key=key,
            metrics=_metrics(items)[0],
        )
        for (dimension, key), items in sorted(groups.items())
    )


def _average(values: Iterable[Decimal]) -> Decimal | None:
    items = tuple(values)
    return sum(items, ZERO) / Decimal(len(items)) if items else None
