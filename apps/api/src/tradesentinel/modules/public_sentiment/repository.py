from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from tradesentinel.domain.sentiment import (
    CompanyDetectionOutput,
    Discussion,
    NarrativeList,
    SentimentShift,
    SentimentSnapshot,
    SentimentTrend,
    SourceWeightOutput,
    SpamRemovalOutput,
)
from tradesentinel.modules.public_sentiment.errors import SentimentPersistenceError
from tradesentinel.platform.persistence import PersistenceResources


class SentimentRepository(ABC):
    @abstractmethod
    async def save_discussions(self, discussions: tuple[Discussion, ...]) -> None: ...

    @abstractmethod
    async def save(self, kind: str, record_id: UUID, payload: dict[str, Any]) -> None: ...


class InMemorySentimentRepository(SentimentRepository):
    def __init__(self) -> None:
        self.records: dict[tuple[str, UUID], dict[str, Any]] = {}

    async def save(self, kind: str, record_id: UUID, payload: dict[str, Any]) -> None:
        self.records[(kind, record_id)] = payload

    async def save_discussions(self, discussions: tuple[Discussion, ...]) -> None:
        for discussion in discussions:
            self.records[("discussion", discussion.discussion_id)] = discussion.model_dump(
                mode="json"
            )


class SentimentBase(DeclarativeBase):
    """Declarative metadata owned by the public-sentiment module."""


class DiscussionRecord(SentimentBase):
    __tablename__ = "discussions"
    __table_args__ = ({"schema": "sentiment"},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(120))
    provider_source_id: Mapped[str] = mapped_column(String(500))
    occurred_at: Mapped[Any] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str] = mapped_column(String(64))
    author_hash: Mapped[str | None] = mapped_column(String(64))
    text_excerpt: Mapped[str] = mapped_column(String(2000))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class SpamRecord(SentimentBase):
    __tablename__ = "spam_decisions"
    __table_args__ = ({"schema": "sentiment"},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class MentionRecord(SentimentBase):
    __tablename__ = "company_mentions"
    __table_args__ = ({"schema": "sentiment"},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class WeightRecord(SentimentBase):
    __tablename__ = "source_weights"
    __table_args__ = ({"schema": "sentiment"},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class SnapshotRecord(SentimentBase):
    __tablename__ = "snapshots"
    __table_args__ = ({"schema": "sentiment"},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class NarrativeRecord(SentimentBase):
    __tablename__ = "narratives"
    __table_args__ = ({"schema": "sentiment"},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class TrendRecord(SentimentBase):
    __tablename__ = "trends"
    __table_args__ = ({"schema": "sentiment"},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class ShiftRecord(SentimentBase):
    __tablename__ = "shifts"
    __table_args__ = ({"schema": "sentiment"},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


RECORD_TYPES = {
    "spam": SpamRecord,
    "detection": MentionRecord,
    "weight": WeightRecord,
    "snapshot": SnapshotRecord,
    "narrative": NarrativeRecord,
    "trend": TrendRecord,
    "shift": ShiftRecord,
}


class SqlSentimentRepository(SentimentRepository):
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def save(self, kind: str, record_id: UUID, payload: dict[str, Any]) -> None:
        try:
            async with self._sessions.begin() as session:
                record_type = RECORD_TYPES[kind]
                await session.merge(record_type(id=record_id, payload=payload))
        except SQLAlchemyError as exc:
            raise SentimentPersistenceError() from exc

    async def save_discussions(self, discussions: tuple[Discussion, ...]) -> None:
        try:
            async with self._sessions.begin() as session:
                for value in discussions:
                    await session.merge(
                        DiscussionRecord(
                            id=value.discussion_id,
                            provider=value.evidence.provider,
                            provider_source_id=value.provider_source_id,
                            occurred_at=value.occurred_at,
                            content_hash=value.content_hash,
                            author_hash=value.author_hash,
                            text_excerpt=value.text_excerpt,
                            payload=value.model_dump(mode="json"),
                        )
                    )
        except SQLAlchemyError as exc:
            raise SentimentPersistenceError() from exc


class SentimentRepositoryFactory:
    def __init__(self, resources: PersistenceResources) -> None:
        self._resources = resources

    def create(self) -> SentimentRepository:
        if self._resources.backend == "postgres":
            return SqlSentimentRepository(self._resources.sessions)
        return InMemorySentimentRepository()


class SentimentPersistenceService:
    def __init__(self, repository_factory: SentimentRepositoryFactory) -> None:
        self._repository = repository_factory.create()

    async def discussions(self, values: tuple[Discussion, ...]) -> None:
        await self._repository.save_discussions(values)

    async def snapshot(self, value: SentimentSnapshot) -> None:
        await self._repository.save("snapshot", value.snapshot_id, value.model_dump(mode="json"))

    async def detection(self, value: CompanyDetectionOutput) -> None:
        for item in value.discussions:
            await self._repository.save(
                "detection", item.discussion.discussion_id, item.model_dump(mode="json")
            )

    async def spam(self, value: SpamRemovalOutput) -> None:
        for item in value.decisions:
            await self._repository.save("spam", item.discussion_id, item.model_dump(mode="json"))

    async def weights(self, value: SourceWeightOutput) -> None:
        for item in value.observations:
            await self._repository.save(
                "weight", item.discussion.discussion_id, item.model_dump(mode="json")
            )

    async def narratives(self, value: NarrativeList) -> None:
        for item in value.narratives:
            await self._repository.save(
                "narrative", item.narrative_id, item.model_dump(mode="json")
            )

    async def trend(self, value: SentimentTrend) -> None:
        identifier = uuid_for(
            value.target.instrument_id,
            "trend",
            value.buckets[-1].day.isoformat() if value.buckets else "empty",
        )
        await self._repository.save("trend", identifier, value.model_dump(mode="json"))

    async def shift(self, value: SentimentShift) -> None:
        identifier = uuid_for(value.target.instrument_id, "shift", str(value.shift_score))
        await self._repository.save("shift", identifier, value.model_dump(mode="json"))


def uuid_for(instrument_id: UUID, kind: str, discriminator: str) -> UUID:
    from uuid import NAMESPACE_URL, uuid5

    return uuid5(NAMESPACE_URL, f"sentiment:{instrument_id}:{kind}:{discriminator}")
