from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String, delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from tradesentinel.domain.research import (
    ResearchClaim,
    ResearchEvent,
    ResearchEvidenceOutput,
    ResearchSource,
)
from tradesentinel.modules.research.errors import (
    ResearchEventNotFoundError,
    ResearchPersistenceError,
)
from tradesentinel.platform.persistence import PersistenceResources


class ResearchRepository(ABC):
    @abstractmethod
    async def save(
        self, sources: tuple[ResearchSource, ...], events: tuple[ResearchEvent, ...]
    ) -> None: ...

    @abstractmethod
    async def evidence(self, event_id: UUID) -> ResearchEvidenceOutput: ...


class InMemoryResearchRepository(ResearchRepository):
    def __init__(self) -> None:
        self.sources: dict[tuple[str, str], ResearchSource] = {}
        self.events: dict[UUID, ResearchEvent] = {}

    async def save(
        self, sources: tuple[ResearchSource, ...], events: tuple[ResearchEvent, ...]
    ) -> None:
        for source in sources:
            self.sources[(source.provider, source.source_id)] = source
        for event in events:
            self.events[event.event_id] = event

    async def evidence(self, event_id: UUID) -> ResearchEvidenceOutput:
        event = self.events.get(event_id)
        if event is None:
            raise ResearchEventNotFoundError(event_id)
        claims = event.claims
        sources = tuple({claim.source.source_id: claim.source for claim in claims}.values())
        return ResearchEvidenceOutput(event=event, sources=sources, claims=claims)


class ResearchBase(DeclarativeBase):
    pass


class SourceRecord(ResearchBase):
    __tablename__ = "sources"
    __table_args__ = ({"schema": "research"},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(120))
    provider_source_id: Mapped[str] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(1000))
    url: Mapped[str] = mapped_column(String(2000))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    document_hash: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class DocumentRecord(ResearchBase):
    __tablename__ = "documents"
    __table_args__ = ({"schema": "research"},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    source_id: Mapped[UUID] = mapped_column(ForeignKey("research.sources.id", ondelete="CASCADE"))
    content_hash: Mapped[str] = mapped_column(String(64))
    content_type: Mapped[str] = mapped_column(String(120), default="unknown")
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EventRecord(ResearchBase):
    __tablename__ = "events"
    __table_args__ = ({"schema": "research"},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    query: Mapped[str] = mapped_column(String(500))
    event_type: Mapped[str] = mapped_column(String(64))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


class EventSourceRecord(ResearchBase):
    __tablename__ = "event_sources"
    __table_args__ = ({"schema": "research"},)
    event_id: Mapped[UUID] = mapped_column(
        ForeignKey("research.events.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[UUID] = mapped_column(
        ForeignKey("research.sources.id", ondelete="CASCADE"), primary_key=True
    )


class ClaimRecord(ResearchBase):
    __tablename__ = "claims"
    __table_args__ = ({"schema": "research"},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    event_id: Mapped[UUID] = mapped_column(ForeignKey("research.events.id", ondelete="CASCADE"))
    source_id: Mapped[UUID] = mapped_column(ForeignKey("research.sources.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(120))
    evidence_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(Float)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)


def _source_uuid(source: ResearchSource) -> UUID:
    from uuid import NAMESPACE_URL, uuid5

    return uuid5(NAMESPACE_URL, f"research-source:{source.provider}:{source.source_id}")


class SqlResearchRepository(ResearchRepository):
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    @asynccontextmanager
    async def _transaction(self) -> AsyncIterator[AsyncSession]:
        try:
            async with self._sessions.begin() as session:
                yield session
        except SQLAlchemyError as exc:
            raise ResearchPersistenceError() from exc

    async def save(
        self, sources: tuple[ResearchSource, ...], events: tuple[ResearchEvent, ...]
    ) -> None:
        async with self._transaction() as session:
            for source in sources:
                source_id = _source_uuid(source)
                await session.merge(
                    SourceRecord(
                        id=source_id,
                        provider=source.provider,
                        provider_source_id=source.provider_source_id,
                        title=source.title,
                        url=str(source.url),
                        published_at=source.published_at,
                        retrieved_at=source.retrieved_at,
                        document_hash=source.document_hash,
                        payload=source.model_dump(mode="json"),
                    )
                )
                if source.document_hash is not None:
                    await session.merge(
                        DocumentRecord(
                            id=source_id,
                            source_id=source_id,
                            content_hash=source.document_hash,
                            content_type="untrusted",
                            retrieved_at=source.retrieved_at,
                        )
                    )
            for event in events:
                await session.merge(
                    EventRecord(
                        id=event.event_id,
                        fingerprint=str(event.event_id),
                        query=event.query,
                        event_type=event.event_type.value,
                        observed_at=event.observed_at,
                        confidence=event.confidence,
                        payload=event.model_dump(mode="json"),
                    )
                )
                await session.execute(
                    delete(EventSourceRecord).where(EventSourceRecord.event_id == event.event_id)
                )
                await session.execute(
                    delete(ClaimRecord).where(ClaimRecord.event_id == event.event_id)
                )
                linked_sources: set[UUID] = set()
                for claim in event.claims:
                    source_id = _source_uuid(claim.source)
                    if source_id not in linked_sources:
                        session.add(EventSourceRecord(event_id=event.event_id, source_id=source_id))
                        linked_sources.add(source_id)
                    session.add(
                        ClaimRecord(
                            id=claim.claim_id,
                            event_id=event.event_id,
                            source_id=source_id,
                            provider=claim.source.provider,
                            evidence_at=claim.timestamp,
                            confidence=claim.confidence,
                            payload=claim.model_dump(mode="json"),
                        )
                    )

    async def evidence(self, event_id: UUID) -> ResearchEvidenceOutput:
        async with self._transaction() as session:
            record = await session.scalar(select(EventRecord).where(EventRecord.id == event_id))
            if record is None:
                raise ResearchEventNotFoundError(event_id)
            event = ResearchEvent.model_validate(record.payload)
            claims = tuple(
                ResearchClaim.model_validate(item.payload)
                for item in (
                    await session.scalars(
                        select(ClaimRecord)
                        .where(ClaimRecord.event_id == event_id)
                        .order_by(ClaimRecord.evidence_at, ClaimRecord.id)
                    )
                ).all()
            )
            return ResearchEvidenceOutput(
                event=event,
                sources=tuple({claim.source.source_id: claim.source for claim in claims}.values()),
                claims=claims,
            )


class ResearchRepositoryFactory:
    def __init__(self, resources: PersistenceResources) -> None:
        self._resources = resources

    def create(self) -> ResearchRepository:
        if self._resources.backend == "postgres":
            return SqlResearchRepository(self._resources.sessions)
        return InMemoryResearchRepository()
