from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from tradesentinel.domain.instruments import AssetType, InstrumentRef
from tradesentinel.modules.instrument_resolution.seed import SEED_INSTRUMENTS
from tradesentinel.platform.persistence import PersistenceResources


class InstrumentRepository(ABC):
    @abstractmethod
    async def list_active(
        self, *, exchange: str | None = None, asset_type: AssetType | None = None
    ) -> tuple[InstrumentRef, ...]: ...


class InMemoryInstrumentRepository(InstrumentRepository):
    def __init__(self) -> None:
        self._instruments = tuple(item.to_ref() for item in SEED_INSTRUMENTS)

    async def list_active(
        self, *, exchange: str | None = None, asset_type: AssetType | None = None
    ) -> tuple[InstrumentRef, ...]:
        exchange_code = exchange.upper() if exchange else None
        return tuple(
            sorted(
                (
                    item
                    for item in self._instruments
                    if (exchange_code is None or item.exchange == exchange_code)
                    and (asset_type is None or item.asset_type == asset_type)
                ),
                key=lambda item: (item.exchange, item.symbol),
            )
        )


class InstrumentBase(DeclarativeBase):
    pass


class InstrumentRecord(InstrumentBase):
    __tablename__ = "instruments"
    __table_args__ = ({"schema": "market"},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(240))
    exchange_code: Mapped[str] = mapped_column(String(20))
    asset_type: Mapped[str] = mapped_column(String(32))
    currency: Mapped[str] = mapped_column(String(12))
    active: Mapped[bool] = mapped_column(Boolean)


class InstrumentAliasRecord(InstrumentBase):
    __tablename__ = "instrument_aliases"
    __table_args__ = ({"schema": "market"},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    instrument_id: Mapped[UUID] = mapped_column(
        ForeignKey("market.instruments.id", ondelete="CASCADE")
    )
    alias: Mapped[str] = mapped_column(String(240))
    position: Mapped[int]


class SqlInstrumentRepository(InstrumentRepository):
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def list_active(
        self, *, exchange: str | None = None, asset_type: AssetType | None = None
    ) -> tuple[InstrumentRef, ...]:
        statement = select(InstrumentRecord).where(InstrumentRecord.active.is_(True))
        if exchange is not None:
            statement = statement.where(InstrumentRecord.exchange_code == exchange.upper())
        if asset_type is not None:
            statement = statement.where(InstrumentRecord.asset_type == asset_type.value)
        statement = statement.order_by(InstrumentRecord.exchange_code, InstrumentRecord.symbol)
        async with self._sessions() as session:
            records = tuple((await session.scalars(statement)).all())
            aliases: dict[UUID, list[str]] = defaultdict(list)
            if records:
                alias_records = (
                    await session.scalars(
                        select(InstrumentAliasRecord)
                        .where(
                            InstrumentAliasRecord.instrument_id.in_(
                                tuple(record.id for record in records)
                            )
                        )
                        .order_by(
                            InstrumentAliasRecord.instrument_id,
                            InstrumentAliasRecord.position,
                        )
                    )
                ).all()
                for alias in alias_records:
                    aliases[alias.instrument_id].append(alias.alias)
        return tuple(
            InstrumentRef(
                instrument_id=record.id,
                symbol=record.symbol,
                name=record.name,
                exchange=record.exchange_code,
                asset_type=AssetType(record.asset_type),
                currency=record.currency,
                aliases=tuple(aliases[record.id]),
            )
            for record in records
        )


class InstrumentRepositoryFactory:
    def __init__(self, resources: PersistenceResources) -> None:
        self._resources = resources

    def create(self) -> InstrumentRepository:
        if self._resources.backend == "postgres":
            return SqlInstrumentRepository(self._resources.sessions)
        return InMemoryInstrumentRepository()
