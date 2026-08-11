from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from tradesentinel.domain.assistant import LlmGenerationAudit
from tradesentinel.platform.persistence import Base, PersistenceResources


class LlmGenerationRecord(Base):
    __tablename__ = "generations"
    __table_args__ = ({"schema": "assistant"},)

    id: Mapped[UUID] = mapped_column(primary_key=True)
    request_id: Mapped[UUID]
    correlation_id: Mapped[UUID]
    run_id: Mapped[UUID | None]
    stage: Mapped[str] = mapped_column(String(80))
    provider: Mapped[str] = mapped_column(String(120))
    model: Mapped[str] = mapped_column(String(160))
    prompt_version: Mapped[str] = mapped_column(String(80))
    input_hash: Mapped[str] = mapped_column(String(64))
    output_hash: Mapped[str] = mapped_column(String(64))
    evidence_ids: Mapped[list[str]] = mapped_column(JSON)
    planned_commands: Mapped[list[str]] = mapped_column(JSON)
    input_tokens: Mapped[int] = mapped_column(Integer)
    output_tokens: Mapped[int] = mapped_column(Integer)
    latency_ms: Mapped[int] = mapped_column(Integer)
    validation_attempts: Mapped[int] = mapped_column(Integer)
    validation_status: Mapped[str] = mapped_column(String(40))
    failure_code: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AssistantAuditRepository(ABC):
    @abstractmethod
    async def save(self, audit: LlmGenerationAudit) -> None: ...


class InMemoryAssistantAuditRepository(AssistantAuditRepository):
    def __init__(self) -> None:
        self.records: list[LlmGenerationAudit] = []

    async def save(self, audit: LlmGenerationAudit) -> None:
        self.records.append(audit)


class SqlAssistantAuditRepository(AssistantAuditRepository):
    def __init__(self, resources: PersistenceResources) -> None:
        self._sessions = resources.sessions

    async def save(self, audit: LlmGenerationAudit) -> None:
        values = audit.model_dump(mode="python")
        values["evidence_ids"] = list(audit.evidence_ids)
        values["planned_commands"] = list(audit.planned_commands)
        async with self._sessions.begin() as session:
            await session.merge(LlmGenerationRecord(**values))


class AssistantAuditRepositoryFactory(AssistantAuditRepository):
    def __init__(self, resources: PersistenceResources) -> None:
        self.implementation: AssistantAuditRepository = (
            SqlAssistantAuditRepository(resources)
            if resources.backend == "postgres"
            else InMemoryAssistantAuditRepository()
        )

    async def save(self, audit: LlmGenerationAudit) -> None:
        await self.implementation.save(audit)
