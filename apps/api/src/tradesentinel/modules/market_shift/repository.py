from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from tradesentinel.domain.market_shift import (
    MarketShiftAttempt,
    MarketShiftHistoryItem,
    MarketShiftHistoryPage,
    MarketShiftObservation,
    MarketShiftObservationBatch,
    MarketShiftObservationReceipt,
    MarketShiftSnapshot,
    MarketShiftStatus,
    MarketShiftWatchlist,
    MarketShiftWatchlistEntry,
)
from tradesentinel.modules.market_shift.errors import MarketShiftPersistenceError
from tradesentinel.platform.persistence import Base, PersistenceResources


class ObservationRecord(Base):
    __tablename__ = "observations"
    __table_args__ = ({"schema": "market_shift"},)
    observation_id: Mapped[UUID] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    instrument_id: Mapped[UUID | None] = mapped_column(index=True)
    scope: Mapped[str] = mapped_column(String(160), index=True)
    metric: Mapped[str] = mapped_column(String(160), index=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    known_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class CalculationRecord(Base):
    __tablename__ = "calculations"
    __table_args__ = ({"schema": "market_shift"},)
    calculation_id: Mapped[UUID] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), unique=True)
    instrument_id: Mapped[UUID] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class _CalculationDetailRecord:
    record_id: Mapped[UUID] = mapped_column(primary_key=True)
    calculation_id: Mapped[UUID] = mapped_column(
        ForeignKey("market_shift.calculations.calculation_id", ondelete="CASCADE"),
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class CategoryContributionRecord(_CalculationDetailRecord, Base):
    __tablename__ = "category_contributions"
    __table_args__ = ({"schema": "market_shift"},)


class EvidenceLinkRecord(_CalculationDetailRecord, Base):
    __tablename__ = "evidence_links"
    __table_args__ = ({"schema": "market_shift"},)


class CatalystRecord(_CalculationDetailRecord, Base):
    __tablename__ = "catalysts"
    __table_args__ = ({"schema": "market_shift"},)


class RiskRecord(_CalculationDetailRecord, Base):
    __tablename__ = "risks"
    __table_args__ = ({"schema": "market_shift"},)


class NarrativeRecord(_CalculationDetailRecord, Base):
    __tablename__ = "narratives"
    __table_args__ = ({"schema": "market_shift"},)


class WatchlistRecord(Base):
    __tablename__ = "watchlist"
    __table_args__ = ({"schema": "market_shift"},)
    watchlist_id: Mapped[UUID] = mapped_column(primary_key=True)
    instrument_id: Mapped[UUID] = mapped_column(unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    lease_owner: Mapped[str | None] = mapped_column(String(160))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class ScheduleRunRecord(Base):
    __tablename__ = "schedule_runs"
    __table_args__ = ({"schema": "market_shift"},)
    run_id: Mapped[UUID] = mapped_column(primary_key=True)
    watchlist_id: Mapped[UUID] = mapped_column(index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30))
    error_code: Mapped[str | None] = mapped_column(String(120))


class MarketShiftRepository(ABC):
    @abstractmethod
    async def ingest(self, batch: MarketShiftObservationBatch) -> MarketShiftObservationReceipt: ...

    @abstractmethod
    async def observations(
        self, instrument_id: UUID, start: datetime, end: datetime
    ) -> tuple[MarketShiftObservation, ...]: ...

    @abstractmethod
    async def save_attempt(self, attempt: MarketShiftAttempt) -> MarketShiftAttempt: ...

    @abstractmethod
    async def attempt(self, calculation_id: UUID) -> MarketShiftAttempt | None: ...

    @abstractmethod
    async def history(
        self, instrument_id: UUID, cursor: datetime | None, limit: int
    ) -> MarketShiftHistoryPage: ...

    @abstractmethod
    async def save_watchlist(
        self, entry: MarketShiftWatchlistEntry
    ) -> MarketShiftWatchlistEntry: ...

    @abstractmethod
    async def remove_watchlist(self, watchlist_id: UUID) -> bool: ...

    @abstractmethod
    async def watchlist(self) -> MarketShiftWatchlist: ...


def _history_page(values: list[MarketShiftSnapshot], limit: int) -> MarketShiftHistoryPage:
    ordered = sorted(values, key=lambda item: item.generated_at, reverse=True)
    page = ordered[:limit]
    items: list[MarketShiftHistoryItem] = []
    for index, snapshot in enumerate(page):
        previous = ordered[index + 1] if index + 1 < len(ordered) else None
        current_labels = {item.label for item in snapshot.narratives}
        previous_labels = {item.label for item in previous.narratives} if previous else set()
        items.append(
            MarketShiftHistoryItem(
                snapshot=snapshot,
                score_change=snapshot.score - previous.score if previous else None,
                confidence_change=(snapshot.confidence - previous.confidence if previous else None),
                direction_changed=bool(previous and snapshot.direction != previous.direction),
                new_narratives=tuple(sorted(current_labels - previous_labels)),
                retired_narratives=tuple(sorted(previous_labels - current_labels)),
            )
        )
    return MarketShiftHistoryPage(
        items=tuple(items),
        next_cursor=page[-1].generated_at if len(ordered) > limit and page else None,
    )


class InMemoryMarketShiftRepository(MarketShiftRepository):
    def __init__(self) -> None:
        self.observation_records: dict[str, MarketShiftObservation] = {}
        self.attempt_records: dict[UUID, MarketShiftAttempt] = {}
        self.attempt_keys: dict[str, UUID] = {}
        self.watchlist_records: dict[UUID, MarketShiftWatchlistEntry] = {}

    async def ingest(self, batch: MarketShiftObservationBatch) -> MarketShiftObservationReceipt:
        duplicate = all(
            item.idempotency_key in self.observation_records for item in batch.observations
        )
        if duplicate:
            first = next(iter(batch.observations))
            return MarketShiftObservationReceipt(
                batch_id=first.observation_id, accepted=0, duplicate=True
            )
        accepted = 0
        for item in batch.observations:
            if item.idempotency_key not in self.observation_records:
                self.observation_records[item.idempotency_key] = item
                accepted += 1
        return MarketShiftObservationReceipt(batch_id=uuid4(), accepted=accepted)

    async def observations(
        self, instrument_id: UUID, start: datetime, end: datetime
    ) -> tuple[MarketShiftObservation, ...]:
        return tuple(
            sorted(
                (
                    item
                    for item in self.observation_records.values()
                    if item.instrument_id in {None, instrument_id}
                    and start <= item.observed_at < end
                ),
                key=lambda item: (item.observed_at, item.metric, item.source_id),
            )
        )

    async def save_attempt(self, attempt: MarketShiftAttempt) -> MarketShiftAttempt:
        existing_id = self.attempt_keys.get(attempt.idempotency_key)
        if existing_id is not None:
            return self.attempt_records[existing_id]
        self.attempt_records[attempt.calculation_id] = attempt
        self.attempt_keys[attempt.idempotency_key] = attempt.calculation_id
        return attempt

    async def attempt(self, calculation_id: UUID) -> MarketShiftAttempt | None:
        return self.attempt_records.get(calculation_id)

    async def history(
        self, instrument_id: UUID, cursor: datetime | None, limit: int
    ) -> MarketShiftHistoryPage:
        values = [
            item.snapshot
            for item in self.attempt_records.values()
            if item.instrument_id == instrument_id
            and item.snapshot is not None
            and (cursor is None or item.snapshot.generated_at < cursor)
        ]
        return _history_page(values, limit)

    async def save_watchlist(self, entry: MarketShiftWatchlistEntry) -> MarketShiftWatchlistEntry:
        self.watchlist_records[entry.watchlist_id] = entry
        return entry

    async def remove_watchlist(self, watchlist_id: UUID) -> bool:
        return self.watchlist_records.pop(watchlist_id, None) is not None

    async def watchlist(self) -> MarketShiftWatchlist:
        return MarketShiftWatchlist(
            items=tuple(
                sorted(
                    self.watchlist_records.values(),
                    key=lambda item: (
                        item.instrument.exchange,
                        item.instrument.symbol,
                        str(item.watchlist_id),
                    ),
                )
            )
        )


class SqlMarketShiftRepository(MarketShiftRepository):
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def ingest(self, batch: MarketShiftObservationBatch) -> MarketShiftObservationReceipt:
        try:
            accepted = 0
            async with self._sessions.begin() as session:
                for item in batch.observations:
                    existing = await session.scalar(
                        select(ObservationRecord).where(
                            ObservationRecord.idempotency_key == item.idempotency_key
                        )
                    )
                    if existing is not None:
                        continue
                    session.add(
                        ObservationRecord(
                            observation_id=item.observation_id,
                            idempotency_key=item.idempotency_key,
                            category=item.category.value,
                            instrument_id=item.instrument_id,
                            scope=item.scope,
                            metric=item.metric,
                            observed_at=item.observed_at,
                            known_at=item.known_at,
                            payload=item.model_dump(mode="json"),
                        )
                    )
                    accepted += 1
            return MarketShiftObservationReceipt(
                batch_id=uuid4(), accepted=accepted, duplicate=accepted == 0
            )
        except SQLAlchemyError as exc:
            raise MarketShiftPersistenceError() from exc

    async def observations(
        self, instrument_id: UUID, start: datetime, end: datetime
    ) -> tuple[MarketShiftObservation, ...]:
        try:
            async with self._sessions() as session:
                records = (
                    await session.scalars(
                        select(ObservationRecord)
                        .where(
                            ObservationRecord.observed_at >= start,
                            ObservationRecord.observed_at < end,
                            (ObservationRecord.instrument_id == instrument_id)
                            | (ObservationRecord.instrument_id.is_(None)),
                        )
                        .order_by(ObservationRecord.observed_at, ObservationRecord.metric)
                    )
                ).all()
                return tuple(
                    MarketShiftObservation.model_validate(item.payload) for item in records
                )
        except SQLAlchemyError as exc:
            raise MarketShiftPersistenceError() from exc

    async def save_attempt(self, attempt: MarketShiftAttempt) -> MarketShiftAttempt:
        try:
            async with self._sessions.begin() as session:
                existing = await session.scalar(
                    select(CalculationRecord).where(
                        CalculationRecord.idempotency_key == attempt.idempotency_key
                    )
                )
                if existing is not None:
                    return MarketShiftAttempt.model_validate(existing.payload)
                session.add(
                    CalculationRecord(
                        calculation_id=attempt.calculation_id,
                        idempotency_key=attempt.idempotency_key,
                        instrument_id=attempt.instrument_id,
                        status=attempt.status.value,
                        requested_at=attempt.requested_at,
                        completed_at=attempt.completed_at,
                        payload=attempt.model_dump(mode="json"),
                    )
                )
                if attempt.snapshot is not None:
                    detail_sets = (
                        (CategoryContributionRecord, attempt.snapshot.category_signals),
                        (EvidenceLinkRecord, attempt.snapshot.evidence),
                        (CatalystRecord, attempt.snapshot.catalysts),
                        (RiskRecord, attempt.snapshot.risks),
                        (NarrativeRecord, attempt.snapshot.narratives),
                    )
                    for record_type, values in detail_sets:
                        session.add_all(
                            record_type(
                                record_id=uuid4(),
                                calculation_id=attempt.calculation_id,
                                position=position,
                                payload=value.model_dump(mode="json"),
                            )
                            for position, value in enumerate(values)
                        )
            return attempt
        except SQLAlchemyError as exc:
            raise MarketShiftPersistenceError() from exc

    async def attempt(self, calculation_id: UUID) -> MarketShiftAttempt | None:
        try:
            async with self._sessions() as session:
                record = await session.get(CalculationRecord, calculation_id)
                return (
                    MarketShiftAttempt.model_validate(record.payload)
                    if record is not None
                    else None
                )
        except SQLAlchemyError as exc:
            raise MarketShiftPersistenceError() from exc

    async def history(
        self, instrument_id: UUID, cursor: datetime | None, limit: int
    ) -> MarketShiftHistoryPage:
        try:
            async with self._sessions() as session:
                query = select(CalculationRecord).where(
                    CalculationRecord.instrument_id == instrument_id,
                    CalculationRecord.status == MarketShiftStatus.COMPLETED.value,
                )
                if cursor is not None:
                    query = query.where(CalculationRecord.completed_at < cursor)
                records = (
                    await session.scalars(
                        query.order_by(CalculationRecord.completed_at.desc()).limit(limit + 1)
                    )
                ).all()
                snapshots = [
                    attempt.snapshot
                    for record in records
                    if (attempt := MarketShiftAttempt.model_validate(record.payload)).snapshot
                    is not None
                ]
                return _history_page(snapshots, limit)
        except SQLAlchemyError as exc:
            raise MarketShiftPersistenceError() from exc

    async def save_watchlist(self, entry: MarketShiftWatchlistEntry) -> MarketShiftWatchlistEntry:
        try:
            async with self._sessions.begin() as session:
                await session.merge(
                    WatchlistRecord(
                        watchlist_id=entry.watchlist_id,
                        instrument_id=entry.instrument.instrument_id,
                        enabled=entry.enabled,
                        next_run_at=entry.next_run_at,
                        payload=entry.model_dump(mode="json"),
                    )
                )
            return entry
        except SQLAlchemyError as exc:
            raise MarketShiftPersistenceError() from exc

    async def remove_watchlist(self, watchlist_id: UUID) -> bool:
        try:
            async with self._sessions.begin() as session:
                existing = await session.get(WatchlistRecord, watchlist_id)
                if existing is None:
                    return False
                await session.execute(
                    delete(WatchlistRecord).where(WatchlistRecord.watchlist_id == watchlist_id)
                )
                return True
        except SQLAlchemyError as exc:
            raise MarketShiftPersistenceError() from exc

    async def watchlist(self) -> MarketShiftWatchlist:
        try:
            async with self._sessions() as session:
                records = (await session.scalars(select(WatchlistRecord))).all()
                entries = tuple(
                    MarketShiftWatchlistEntry.model_validate(item.payload) for item in records
                )
                return MarketShiftWatchlist(
                    items=tuple(
                        sorted(
                            entries,
                            key=lambda item: (
                                item.instrument.exchange,
                                item.instrument.symbol,
                                str(item.watchlist_id),
                            ),
                        )
                    )
                )
        except SQLAlchemyError as exc:
            raise MarketShiftPersistenceError() from exc


class MarketShiftRepositoryFactory:
    def __init__(self, resources: PersistenceResources) -> None:
        self.resources = resources

    def create(self) -> MarketShiftRepository:
        if self.resources.backend == "postgres":
            return SqlMarketShiftRepository(self.resources.sessions)
        return InMemoryMarketShiftRepository()


class MarketShiftPersistenceService:
    def __init__(self, repository_factory: MarketShiftRepositoryFactory) -> None:
        self.repository = repository_factory.create()
