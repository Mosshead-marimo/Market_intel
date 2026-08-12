from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import cast
from uuid import NAMESPACE_URL, uuid5

from pydantic import JsonValue

from tradesentinel.domain.market_shift import (
    EmptyMarketShiftInput,
    MarketShiftAttempt,
    MarketShiftHistoryRequest,
    MarketShiftObservationBatch,
    MarketShiftObservationQuery,
    MarketShiftObservationSet,
    MarketShiftReference,
    MarketShiftScheduleResult,
    MarketShiftScoreInput,
    MarketShiftStatus,
    MarketShiftWatchlistEntry,
    MarketShiftWatchlistReference,
    MarketShiftWindow,
)
from tradesentinel.modules.market_shift.errors import (
    MarketShiftInputIncompleteError,
    MarketShiftNotFoundError,
)
from tradesentinel.modules.market_shift.repository import MarketShiftPersistenceService
from tradesentinel.modules.market_shift.service import MarketShiftScoringService
from tradesentinel.modules.market_shift.worker import MarketShiftBackgroundWorker
from tradesentinel.platform.capabilities import Capability
from tradesentinel.platform.contracts import (
    CapabilityResult,
    ComparisonTable,
    ComponentStatus,
    EventEnvelope,
    ExecutionContext,
    MetricGrid,
    MetricItem,
    RiskCard,
    RiskItem,
    RunMetadata,
    RunStatus,
    TableRow,
)
from tradesentinel.platform.events import EventBus


def _result(
    capability: str,
    data: dict[str, JsonValue],
    started: datetime,
    **kwargs: object,
) -> CapabilityResult:
    completed = datetime.now(UTC)
    return CapabilityResult(
        capability=capability,
        status=RunStatus.COMPLETED,
        data=data,
        metadata=RunMetadata(
            started_at=started,
            completed_at=completed,
            duration_ms=max(0, int((completed - started).total_seconds() * 1000)),
        ),
        **kwargs,
    )


class _Base:
    def __init__(self, persistence: MarketShiftPersistenceService, events: EventBus) -> None:
        self.persistence = persistence
        self.events = events

    async def emit(
        self, name: str, context: ExecutionContext, payload: dict[str, JsonValue]
    ) -> None:
        await self.events.publish(
            EventEnvelope(
                name=name,
                producer="market_shift",
                correlation_id=context.correlation_id,
                causation_id=context.causation_id,
                payload=payload,
            )
        )


class IngestObservationsCapability(_Base, Capability[MarketShiftObservationBatch]):
    input_model = MarketShiftObservationBatch

    async def execute(
        self, context: ExecutionContext, payload: MarketShiftObservationBatch
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        receipt = await self.persistence.repository.ingest(payload)
        await self.emit(
            "market_shift.observations.ingested",
            context,
            {"batch_id": str(receipt.batch_id), "accepted": receipt.accepted},
        )
        return _result(
            "market_shift.observations.ingest",
            cast(dict[str, JsonValue], receipt.model_dump(mode="json")),
            started,
        )


class LoadObservationsCapability(_Base, Capability[MarketShiftObservationQuery]):
    input_model = MarketShiftObservationQuery

    async def execute(
        self, context: ExecutionContext, payload: MarketShiftObservationQuery
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        window = MarketShiftWindow.ending_at(payload.as_of, payload.window_days)
        values = await self.persistence.repository.observations(
            payload.instrument.instrument_id, window.previous_start, window.end
        )
        idempotency_key = payload.idempotency_key or (
            f"{payload.instrument.instrument_id}:{window.end.isoformat()}:{payload.window_days}"
        )
        output = MarketShiftObservationSet(
            instrument=payload.instrument,
            window=window,
            observations=values,
            idempotency_key=idempotency_key,
        )
        return _result(
            "market_shift.observations.load",
            cast(dict[str, JsonValue], output.model_dump(mode="json")),
            started,
        )


class CalculateMarketShiftCapability(_Base, Capability[MarketShiftScoreInput]):
    input_model = MarketShiftScoreInput

    def __init__(
        self,
        persistence: MarketShiftPersistenceService,
        events: EventBus,
        scoring: MarketShiftScoringService,
    ) -> None:
        super().__init__(persistence, events)
        self.scoring = scoring

    async def execute(
        self, context: ExecutionContext, payload: MarketShiftScoreInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        calculation_id = uuid5(NAMESPACE_URL, f"market-shift:{payload.idempotency_key}")
        try:
            snapshot = self.scoring.calculate(payload)
        except MarketShiftInputIncompleteError as exc:
            await self.persistence.repository.save_attempt(
                MarketShiftAttempt(
                    calculation_id=calculation_id,
                    status=MarketShiftStatus.FAILED,
                    instrument_id=payload.instrument.instrument_id,
                    requested_at=started,
                    completed_at=datetime.now(UTC),
                    idempotency_key=payload.idempotency_key,
                    error_code=exc.code,
                    error_message=exc.message,
                )
            )
            raise
        attempt = await self.persistence.repository.save_attempt(
            MarketShiftAttempt(
                calculation_id=snapshot.calculation_id,
                status=MarketShiftStatus.COMPLETED,
                instrument_id=payload.instrument.instrument_id,
                requested_at=started,
                completed_at=datetime.now(UTC),
                idempotency_key=payload.idempotency_key,
                snapshot=snapshot,
            )
        )
        snapshot = attempt.snapshot or snapshot
        category_table = ComparisonTable(
            id="market-shift-contributions",
            title="Market narrative contributions",
            columns=("Category", "Score", "Weight", "Contribution", "Confidence"),
            rows=tuple(
                TableRow(
                    cells=(
                        signal.category.value.replace("_", " ").title(),
                        str(signal.score),
                        str(signal.weight),
                        str(signal.weighted_contribution),
                        str(signal.confidence),
                    )
                )
                for signal in snapshot.category_signals
            ),
        )
        metrics = MetricGrid(
            id="market-shift-score",
            title="Market Shift",
            metrics=(
                MetricItem(label="Score", value=str(snapshot.score), detail="Range -100 to 100"),
                MetricItem(label="Direction", value=snapshot.direction.value),
                MetricItem(
                    label="Confidence",
                    value=str(snapshot.confidence),
                    detail="Evidence quality, not probability",
                ),
            ),
        )
        risk_card = RiskCard(
            id="market-shift-risks",
            title="Observed narrative risks",
            status=ComponentStatus.EMPTY if not snapshot.risks else ComponentStatus.READY,
            risks=tuple(
                RiskItem(
                    label=item.label,
                    severity="high" if abs(item.contribution) >= Decimal("0.10") else "medium",
                    description=f"Observed contribution {item.contribution}; not a price forecast.",
                )
                for item in snapshot.risks
            ),
        )
        await self.emit(
            "market_shift.completed",
            context,
            {
                "calculation_id": str(snapshot.calculation_id),
                "instrument_id": str(snapshot.instrument.instrument_id),
                "score": str(snapshot.score),
                "direction": snapshot.direction.value,
                "confidence": str(snapshot.confidence),
                "evidence_count": len(snapshot.evidence),
            },
        )
        return _result(
            "market_shift.calculate",
            cast(dict[str, JsonValue], snapshot.model_dump(mode="json")),
            started,
            components=(metrics, category_table, risk_card),
            summary=(
                f"Observed market narrative is {snapshot.direction.value}; "
                f"Market Shift Score {snapshot.score}. This is not a price prediction."
            ),
        )


class ReadMarketShiftCapability(_Base, Capability[MarketShiftReference]):
    input_model = MarketShiftReference

    async def execute(
        self, context: ExecutionContext, payload: MarketShiftReference
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        attempt = await self.persistence.repository.attempt(payload.calculation_id)
        if attempt is None:
            raise MarketShiftNotFoundError()
        return _result(
            "market_shift.read",
            cast(dict[str, JsonValue], attempt.model_dump(mode="json")),
            started,
        )


class ReadHistoryCapability(_Base, Capability[MarketShiftHistoryRequest]):
    input_model = MarketShiftHistoryRequest

    async def execute(
        self, context: ExecutionContext, payload: MarketShiftHistoryRequest
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        history = await self.persistence.repository.history(
            payload.instrument_id, payload.cursor, payload.limit
        )
        return _result(
            "market_shift.history",
            cast(dict[str, JsonValue], history.model_dump(mode="json")),
            started,
        )


class SaveWatchlistCapability(_Base, Capability[MarketShiftWatchlistEntry]):
    input_model = MarketShiftWatchlistEntry

    async def execute(
        self, context: ExecutionContext, payload: MarketShiftWatchlistEntry
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        saved = await self.persistence.repository.save_watchlist(payload)
        return _result(
            "market_shift.watchlist.save",
            cast(dict[str, JsonValue], saved.model_dump(mode="json")),
            started,
        )


class RemoveWatchlistCapability(_Base, Capability[MarketShiftWatchlistReference]):
    input_model = MarketShiftWatchlistReference

    async def execute(
        self, context: ExecutionContext, payload: MarketShiftWatchlistReference
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        removed = await self.persistence.repository.remove_watchlist(payload.watchlist_id)
        return _result("market_shift.watchlist.remove", {"removed": removed}, started)


class ListWatchlistCapability(_Base, Capability[EmptyMarketShiftInput]):
    input_model = EmptyMarketShiftInput

    async def execute(
        self, context: ExecutionContext, payload: EmptyMarketShiftInput
    ) -> CapabilityResult:
        del payload
        started = datetime.now(UTC)
        watchlist = await self.persistence.repository.watchlist()
        return _result(
            "market_shift.watchlist.list",
            cast(dict[str, JsonValue], watchlist.model_dump(mode="json")),
            started,
        )


class RunScheduleCapability(_Base, Capability[EmptyMarketShiftInput]):
    input_model = EmptyMarketShiftInput

    def __init__(
        self,
        persistence: MarketShiftPersistenceService,
        events: EventBus,
        worker: MarketShiftBackgroundWorker,
    ) -> None:
        super().__init__(persistence, events)
        self.worker = worker

    async def execute(
        self, context: ExecutionContext, payload: EmptyMarketShiftInput
    ) -> CapabilityResult:
        del payload
        started = datetime.now(UTC)
        output = MarketShiftScheduleResult(processed=await self.worker.run_once())
        await self.emit(
            "market_shift.schedule.completed",
            context,
            {"processed": output.processed},
        )
        return _result(
            "market_shift.schedule.run",
            cast(dict[str, JsonValue], output.model_dump(mode="json")),
            started,
        )
