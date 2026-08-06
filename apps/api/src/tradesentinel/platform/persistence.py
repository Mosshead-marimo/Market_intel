from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import JSON, DateTime, MetaData, String, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from tradesentinel.platform.contracts import CapabilityResult, WorkflowResult

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class WorkflowRunRecord(Base):
    __tablename__ = "workflow_runs"
    __table_args__ = ({"schema": "core"},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    workflow: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class CapabilityRunRecord(Base):
    __tablename__ = "capability_runs"
    __table_args__ = ({"schema": "core"},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    workflow_run_id: Mapped[UUID | None]
    capability: Mapped[str] = mapped_column(String(160))
    status: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON)


class RunRepository(ABC):
    @abstractmethod
    async def save_workflow(self, result: WorkflowResult) -> None: ...

    @abstractmethod
    async def save_capability(self, run_id: UUID, result: CapabilityResult) -> None: ...

    @abstractmethod
    async def get_workflow(self, run_id: UUID) -> WorkflowResult | None: ...


class InMemoryRunRepository(RunRepository):
    def __init__(self) -> None:
        self.workflows: dict[UUID, WorkflowResult] = {}
        self.capabilities: dict[UUID, CapabilityResult] = {}

    async def save_workflow(self, result: WorkflowResult) -> None:
        self.workflows[result.run_id] = result

    async def save_capability(self, run_id: UUID, result: CapabilityResult) -> None:
        self.capabilities[run_id] = result

    async def get_workflow(self, run_id: UUID) -> WorkflowResult | None:
        return self.workflows.get(run_id)


class SqlRunRepository(RunRepository):
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = session_factory

    async def save_workflow(self, result: WorkflowResult) -> None:
        async with self._sessions.begin() as session:
            await session.merge(
                WorkflowRunRecord(
                    id=result.run_id,
                    workflow=result.workflow,
                    status=result.status.value,
                    started_at=result.started_at,
                    completed_at=result.completed_at,
                    result=result.model_dump(mode="json"),
                )
            )

    async def save_capability(self, run_id: UUID, result: CapabilityResult) -> None:
        async with self._sessions.begin() as session:
            await session.merge(
                CapabilityRunRecord(
                    id=run_id,
                    capability=result.capability,
                    status=result.status.value,
                    started_at=result.metadata.started_at,
                    completed_at=result.metadata.completed_at,
                    result=result.model_dump(mode="json"),
                )
            )

    async def get_workflow(self, run_id: UUID) -> WorkflowResult | None:
        async with self._sessions() as session:
            record = await session.scalar(
                select(WorkflowRunRecord).where(WorkflowRunRecord.id == run_id)
            )
            if record is None or record.result is None:
                return None
            return WorkflowResult.model_validate(record.result)


def create_engine(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)
