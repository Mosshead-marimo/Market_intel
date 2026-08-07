from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from tradesentinel.platform.contracts import (
    ApiErrorDetail,
    ChatMessage,
    ChatMessageStatus,
    ChatRole,
    ChatSession,
    ChatSessionDetail,
    ChatSessionPage,
    ChatSessionStatus,
    ChatTurn,
    ChatTurnStatus,
    ConversationContext,
    ConversationContextMessage,
    RenderedResponse,
)
from tradesentinel.platform.errors import (
    ChatTurnActiveError,
    ChatTurnNotFoundError,
    SessionArchivedError,
    SessionNotFoundError,
)
from tradesentinel.platform.persistence import Base

ACTIVE_TURN_STATUSES = (
    ChatTurnStatus.QUEUED.value,
    ChatTurnStatus.PLANNING.value,
    ChatTurnStatus.EXECUTING.value,
    ChatTurnStatus.RENDERING.value,
)


class ChatSessionRecord(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = ({"schema": "core", "extend_existing": True},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    principal_id: Mapped[str] = mapped_column(String(160), index=True)
    title: Mapped[str | None] = mapped_column(String(240))
    status: Mapped[str] = mapped_column(String(32))
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ChatMessageRecord(Base):
    __tablename__ = "chat_messages"
    __table_args__ = ({"schema": "core", "extend_existing": True},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("core.chat_sessions.id", ondelete="CASCADE"), index=True
    )
    turn_id: Mapped[UUID] = mapped_column(index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32))
    rendered_response: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChatTurnRecord(Base):
    __tablename__ = "chat_turns"
    __table_args__ = ({"schema": "core"},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("core.chat_sessions.id", ondelete="CASCADE"), index=True
    )
    principal_id: Mapped[str] = mapped_column(String(160), index=True)
    client_message_id: Mapped[UUID] = mapped_column(unique=True)
    user_message_id: Mapped[UUID] = mapped_column(ForeignKey("core.chat_messages.id"))
    assistant_message_id: Mapped[UUID | None] = mapped_column(ForeignKey("core.chat_messages.id"))
    status: Mapped[str] = mapped_column(String(32), index=True)
    request_id: Mapped[UUID]
    correlation_id: Mapped[UUID]
    run_id: Mapped[UUID | None]
    attempt: Mapped[int] = mapped_column(Integer)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ChatOutboxRecord(Base):
    __tablename__ = "chat_outbox"
    __table_args__ = ({"schema": "core"},)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    turn_id: Mapped[UUID] = mapped_column(ForeignKey("core.chat_turns.id"), unique=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


@dataclass(frozen=True)
class ChatAcceptance:
    session: ChatSession
    turn: ChatTurn
    created: bool


@dataclass(frozen=True)
class PendingChatEvent:
    id: UUID
    turn_id: UUID
    principal_id: str
    request_id: UUID
    correlation_id: UUID


class ChatRepository(ABC):
    @abstractmethod
    async def create_session(self, principal_id: str, title: str = "New chat") -> ChatSession: ...

    @abstractmethod
    async def list_sessions(
        self, principal_id: str, *, archived: bool, cursor: str | None, limit: int
    ) -> ChatSessionPage: ...

    @abstractmethod
    async def get_session(self, principal_id: str, session_id: UUID) -> ChatSessionDetail: ...

    @abstractmethod
    async def update_session(
        self,
        principal_id: str,
        session_id: UUID,
        *,
        title: str | None,
        archived: bool | None,
    ) -> ChatSession: ...

    @abstractmethod
    async def accept_turn(
        self,
        principal_id: str,
        *,
        session_id: UUID | None,
        client_message_id: UUID,
        content: str,
        request_id: UUID,
        correlation_id: UUID,
    ) -> ChatAcceptance: ...

    @abstractmethod
    async def get_turn(self, principal_id: str, turn_id: UUID) -> ChatTurn: ...

    @abstractmethod
    async def claim_turn(self, principal_id: str, turn_id: UUID) -> ChatTurn | None: ...

    @abstractmethod
    async def set_turn_status(
        self, principal_id: str, turn_id: UUID, status: ChatTurnStatus
    ) -> ChatTurn: ...

    @abstractmethod
    async def get_context(
        self, principal_id: str, session_id: UUID, turn_id: UUID, limit: int
    ) -> ConversationContext: ...

    @abstractmethod
    async def complete_turn(
        self,
        principal_id: str,
        turn_id: UUID,
        response: RenderedResponse,
    ) -> tuple[ChatTurn, ChatMessage]: ...

    @abstractmethod
    async def fail_turn(
        self, principal_id: str, turn_id: UUID, error: ApiErrorDetail
    ) -> ChatTurn: ...

    @abstractmethod
    async def pending_events(self, limit: int = 50) -> tuple[PendingChatEvent, ...]: ...

    @abstractmethod
    async def mark_published(self, event_id: UUID) -> None: ...


def _title(content: str) -> str:
    normalized = " ".join(content.split())
    return normalized[:60] if normalized else "New chat"


class InMemoryChatRepository(ChatRepository):
    def __init__(self) -> None:
        self.sessions: dict[UUID, tuple[str, ChatSession]] = {}
        self.messages: dict[UUID, list[ChatMessage]] = {}
        self.turns: dict[UUID, tuple[str, ChatTurn]] = {}
        self.by_client_message: dict[tuple[str, UUID], UUID] = {}
        self.outbox: dict[UUID, PendingChatEvent] = {}
        self._lock = asyncio.Lock()

    async def create_session(self, principal_id: str, title: str = "New chat") -> ChatSession:
        now = datetime.now(UTC)
        session = ChatSession(
            id=uuid4(),
            title=title,
            status=ChatSessionStatus.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        async with self._lock:
            self.sessions[session.id] = (principal_id, session)
            self.messages[session.id] = []
        return session

    async def list_sessions(
        self, principal_id: str, *, archived: bool, cursor: str | None, limit: int
    ) -> ChatSessionPage:
        offset = int(cursor or "0")
        expected = ChatSessionStatus.ARCHIVED if archived else ChatSessionStatus.ACTIVE
        items = sorted(
            (
                session
                for owner, session in self.sessions.values()
                if owner == principal_id and session.status == expected
            ),
            key=lambda session: (session.updated_at, str(session.id)),
            reverse=True,
        )
        page = items[offset : offset + limit]
        next_cursor = str(offset + limit) if offset + limit < len(items) else None
        return ChatSessionPage(items=tuple(page), next_cursor=next_cursor)

    def _owned_session(self, principal_id: str, session_id: UUID) -> ChatSession:
        owned = self.sessions.get(session_id)
        if owned is None or owned[0] != principal_id:
            raise SessionNotFoundError()
        return owned[1]

    async def get_session(self, principal_id: str, session_id: UUID) -> ChatSessionDetail:
        session = self._owned_session(principal_id, session_id)
        active = next(
            (
                turn
                for owner, turn in self.turns.values()
                if owner == principal_id
                and turn.session_id == session_id
                and turn.status.value in ACTIVE_TURN_STATUSES
            ),
            None,
        )
        return ChatSessionDetail(
            session=session,
            messages=tuple(self.messages.get(session_id, ())),
            active_turn=active,
        )

    async def update_session(
        self,
        principal_id: str,
        session_id: UUID,
        *,
        title: str | None,
        archived: bool | None,
    ) -> ChatSession:
        current = self._owned_session(principal_id, session_id)
        if archived and any(
            owner == principal_id
            and turn.session_id == session_id
            and turn.status.value in ACTIVE_TURN_STATUSES
            for owner, turn in self.turns.values()
        ):
            raise ChatTurnActiveError()
        now = datetime.now(UTC)
        status = current.status
        archived_at = current.archived_at
        if archived is not None:
            status = ChatSessionStatus.ARCHIVED if archived else ChatSessionStatus.ACTIVE
            archived_at = now if archived else None
        updated = current.model_copy(
            update={
                "title": title if title is not None else current.title,
                "status": status,
                "archived_at": archived_at,
                "updated_at": now,
            }
        )
        self.sessions[session_id] = (principal_id, updated)
        return updated

    async def accept_turn(
        self,
        principal_id: str,
        *,
        session_id: UUID | None,
        client_message_id: UUID,
        content: str,
        request_id: UUID,
        correlation_id: UUID,
    ) -> ChatAcceptance:
        async with self._lock:
            existing_id = self.by_client_message.get((principal_id, client_message_id))
            if existing_id is not None:
                existing = self.turns[existing_id][1]
                session = self._owned_session(principal_id, existing.session_id)
                return ChatAcceptance(session=session, turn=existing, created=False)
            if session_id is None:
                now = datetime.now(UTC)
                session = ChatSession(
                    id=uuid4(),
                    title=_title(content),
                    status=ChatSessionStatus.ACTIVE,
                    created_at=now,
                    updated_at=now,
                )
                self.sessions[session.id] = (principal_id, session)
                self.messages[session.id] = []
            else:
                session = self._owned_session(principal_id, session_id)
            if session.status == ChatSessionStatus.ARCHIVED:
                raise SessionArchivedError()
            if any(
                owner == principal_id
                and turn.session_id == session.id
                and turn.status.value in ACTIVE_TURN_STATUSES
                for owner, turn in self.turns.values()
            ):
                raise ChatTurnActiveError()
            now = datetime.now(UTC)
            turn_id = uuid4()
            message = ChatMessage(
                id=uuid4(),
                session_id=session.id,
                turn_id=turn_id,
                role=ChatRole.USER,
                content=content,
                status=ChatMessageStatus.COMPLETED,
                created_at=now,
                completed_at=now,
            )
            turn = ChatTurn(
                id=turn_id,
                session_id=session.id,
                client_message_id=client_message_id,
                user_message_id=message.id,
                status=ChatTurnStatus.QUEUED,
                request_id=request_id,
                correlation_id=correlation_id,
                created_at=now,
            )
            session = session.model_copy(
                update={
                    "updated_at": now,
                    "title": _title(content) if not self.messages[session.id] else session.title,
                }
            )
            self.sessions[session.id] = (principal_id, session)
            self.messages[session.id].append(message)
            self.turns[turn.id] = (principal_id, turn)
            self.by_client_message[(principal_id, client_message_id)] = turn.id
            event = PendingChatEvent(uuid4(), turn.id, principal_id, request_id, correlation_id)
            self.outbox[event.id] = event
            return ChatAcceptance(session=session, turn=turn, created=True)

    async def get_turn(self, principal_id: str, turn_id: UUID) -> ChatTurn:
        owned = self.turns.get(turn_id)
        if owned is None or owned[0] != principal_id:
            raise ChatTurnNotFoundError()
        return owned[1]

    async def claim_turn(self, principal_id: str, turn_id: UUID) -> ChatTurn | None:
        async with self._lock:
            turn = await self.get_turn(principal_id, turn_id)
            now = datetime.now(UTC)
            reclaimable = (
                turn.status.value in ACTIVE_TURN_STATUSES
                and turn.lease_expires_at is not None
                and turn.lease_expires_at <= now
            )
            if turn.status != ChatTurnStatus.QUEUED and not reclaimable:
                return None
            claimed = turn.model_copy(
                update={
                    "status": ChatTurnStatus.PLANNING,
                    "started_at": turn.started_at or now,
                    "attempt": turn.attempt + 1,
                    "lease_expires_at": now + timedelta(minutes=5),
                }
            )
            self.turns[turn_id] = (principal_id, claimed)
            return claimed

    async def set_turn_status(
        self, principal_id: str, turn_id: UUID, status: ChatTurnStatus
    ) -> ChatTurn:
        async with self._lock:
            turn = await self.get_turn(principal_id, turn_id)
            updated = turn.model_copy(
                update={
                    "status": status,
                    "lease_expires_at": datetime.now(UTC) + timedelta(minutes=5),
                }
            )
            self.turns[turn_id] = (principal_id, updated)
            return updated

    async def get_context(
        self, principal_id: str, session_id: UUID, turn_id: UUID, limit: int
    ) -> ConversationContext:
        self._owned_session(principal_id, session_id)
        messages = self.messages.get(session_id, [])[-limit:]
        return ConversationContext(
            session_id=session_id,
            turn_id=turn_id,
            messages=tuple(
                ConversationContextMessage(
                    id=message.id,
                    role=message.role,
                    content=message.content,
                    created_at=message.created_at,
                )
                for message in messages
            ),
        )

    async def complete_turn(
        self, principal_id: str, turn_id: UUID, response: RenderedResponse
    ) -> tuple[ChatTurn, ChatMessage]:
        async with self._lock:
            turn = await self.get_turn(principal_id, turn_id)
            now = datetime.now(UTC)
            status = (
                ChatTurnStatus.PARTIAL
                if response.status.value == "partial"
                else ChatTurnStatus.COMPLETED
            )
            message_status = (
                ChatMessageStatus.PARTIAL
                if status == ChatTurnStatus.PARTIAL
                else ChatMessageStatus.COMPLETED
            )
            message = ChatMessage(
                id=uuid4(),
                session_id=turn.session_id,
                turn_id=turn.id,
                role=ChatRole.ASSISTANT,
                content=response.text,
                status=message_status,
                response=response,
                created_at=now,
                completed_at=now,
            )
            completed = turn.model_copy(
                update={
                    "assistant_message_id": message.id,
                    "status": status,
                    "run_id": response.run_id,
                    "lease_expires_at": None,
                    "completed_at": now,
                }
            )
            self.turns[turn.id] = (principal_id, completed)
            self.messages[turn.session_id].append(message)
            owner, session = self.sessions[turn.session_id]
            self.sessions[turn.session_id] = (owner, session.model_copy(update={"updated_at": now}))
            return completed, message

    async def fail_turn(self, principal_id: str, turn_id: UUID, error: ApiErrorDetail) -> ChatTurn:
        async with self._lock:
            turn = await self.get_turn(principal_id, turn_id)
            now = datetime.now(UTC)
            message = ChatMessage(
                id=uuid4(),
                session_id=turn.session_id,
                turn_id=turn.id,
                role=ChatRole.ASSISTANT,
                content=error.message,
                status=ChatMessageStatus.FAILED,
                error=error,
                created_at=now,
                completed_at=now,
            )
            failed = turn.model_copy(
                update={
                    "assistant_message_id": message.id,
                    "status": ChatTurnStatus.FAILED,
                    "error": error,
                    "lease_expires_at": None,
                    "completed_at": now,
                }
            )
            self.turns[turn.id] = (principal_id, failed)
            self.messages[turn.session_id].append(message)
            return failed

    async def pending_events(self, limit: int = 50) -> tuple[PendingChatEvent, ...]:
        return tuple(list(self.outbox.values())[:limit])

    async def mark_published(self, event_id: UUID) -> None:
        self.outbox.pop(event_id, None)


class SqlChatRepository(ChatRepository):
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    @staticmethod
    def _session(record: ChatSessionRecord) -> ChatSession:
        return ChatSession(
            id=record.id,
            title=record.title or "New chat",
            status=ChatSessionStatus(record.status),
            created_at=record.created_at,
            updated_at=record.updated_at,
            archived_at=record.archived_at,
        )

    @staticmethod
    def _turn(record: ChatTurnRecord) -> ChatTurn:
        return ChatTurn(
            id=record.id,
            session_id=record.session_id,
            client_message_id=record.client_message_id,
            user_message_id=record.user_message_id,
            assistant_message_id=record.assistant_message_id,
            status=ChatTurnStatus(record.status),
            request_id=record.request_id,
            correlation_id=record.correlation_id,
            run_id=record.run_id,
            attempt=record.attempt,
            lease_expires_at=record.lease_expires_at,
            error=ApiErrorDetail.model_validate(record.error) if record.error else None,
            created_at=record.created_at,
            started_at=record.started_at,
            completed_at=record.completed_at,
        )

    @staticmethod
    def _message(record: ChatMessageRecord) -> ChatMessage:
        return ChatMessage(
            id=record.id,
            session_id=record.session_id,
            turn_id=record.turn_id,
            role=ChatRole(record.role),
            content=record.content,
            status=ChatMessageStatus(record.status),
            response=(
                RenderedResponse.model_validate(record.rendered_response)
                if record.rendered_response
                else None
            ),
            error=ApiErrorDetail.model_validate(record.error) if record.error else None,
            created_at=record.created_at,
            completed_at=record.completed_at,
        )

    async def create_session(self, principal_id: str, title: str = "New chat") -> ChatSession:
        now = datetime.now(UTC)
        record = ChatSessionRecord(
            id=uuid4(),
            principal_id=principal_id,
            title=title,
            status=ChatSessionStatus.ACTIVE.value,
            archived_at=None,
            created_at=now,
            updated_at=now,
        )
        async with self._sessions.begin() as session:
            session.add(record)
        return self._session(record)

    async def list_sessions(
        self, principal_id: str, *, archived: bool, cursor: str | None, limit: int
    ) -> ChatSessionPage:
        offset = int(cursor or "0")
        expected = ChatSessionStatus.ARCHIVED if archived else ChatSessionStatus.ACTIVE
        async with self._sessions() as session:
            records = (
                await session.scalars(
                    select(ChatSessionRecord)
                    .where(
                        ChatSessionRecord.principal_id == principal_id,
                        ChatSessionRecord.status == expected.value,
                    )
                    .order_by(ChatSessionRecord.updated_at.desc(), ChatSessionRecord.id.desc())
                    .offset(offset)
                    .limit(limit + 1)
                )
            ).all()
        next_cursor = str(offset + limit) if len(records) > limit else None
        return ChatSessionPage(
            items=tuple(self._session(record) for record in records[:limit]),
            next_cursor=next_cursor,
        )

    async def _owned(
        self, session: AsyncSession, principal_id: str, session_id: UUID
    ) -> ChatSessionRecord:
        record = await session.scalar(
            select(ChatSessionRecord).where(
                ChatSessionRecord.id == session_id,
                ChatSessionRecord.principal_id == principal_id,
            )
        )
        if record is None:
            raise SessionNotFoundError()
        return record

    async def get_session(self, principal_id: str, session_id: UUID) -> ChatSessionDetail:
        async with self._sessions() as session:
            record = await self._owned(session, principal_id, session_id)
            messages = (
                await session.scalars(
                    select(ChatMessageRecord)
                    .where(ChatMessageRecord.session_id == session_id)
                    .order_by(ChatMessageRecord.sequence)
                )
            ).all()
            active_record = await session.scalar(
                select(ChatTurnRecord).where(
                    ChatTurnRecord.session_id == session_id,
                    ChatTurnRecord.status.in_(ACTIVE_TURN_STATUSES),
                )
            )
            return ChatSessionDetail(
                session=self._session(record),
                messages=tuple(self._message(message) for message in messages),
                active_turn=self._turn(active_record) if active_record else None,
            )

    async def update_session(
        self,
        principal_id: str,
        session_id: UUID,
        *,
        title: str | None,
        archived: bool | None,
    ) -> ChatSession:
        async with self._sessions.begin() as session:
            record = await self._owned(session, principal_id, session_id)
            if archived:
                active = await session.scalar(
                    select(ChatTurnRecord.id).where(
                        ChatTurnRecord.session_id == session_id,
                        ChatTurnRecord.status.in_(ACTIVE_TURN_STATUSES),
                    )
                )
                if active is not None:
                    raise ChatTurnActiveError()
            now = datetime.now(UTC)
            if title is not None:
                record.title = title
            if archived is not None:
                record.status = (
                    ChatSessionStatus.ARCHIVED.value if archived else ChatSessionStatus.ACTIVE.value
                )
                record.archived_at = now if archived else None
            record.updated_at = now
        return self._session(record)

    async def accept_turn(
        self,
        principal_id: str,
        *,
        session_id: UUID | None,
        client_message_id: UUID,
        content: str,
        request_id: UUID,
        correlation_id: UUID,
    ) -> ChatAcceptance:
        async with self._sessions.begin() as session:
            existing = await session.scalar(
                select(ChatTurnRecord).where(
                    ChatTurnRecord.principal_id == principal_id,
                    ChatTurnRecord.client_message_id == client_message_id,
                )
            )
            if existing is not None:
                session_record = await self._owned(session, principal_id, existing.session_id)
                return ChatAcceptance(self._session(session_record), self._turn(existing), False)
            now = datetime.now(UTC)
            if session_id is None:
                session_record = ChatSessionRecord(
                    id=uuid4(),
                    principal_id=principal_id,
                    title=_title(content),
                    status=ChatSessionStatus.ACTIVE.value,
                    archived_at=None,
                    created_at=now,
                    updated_at=now,
                )
                session.add(session_record)
                await session.flush()
            else:
                session_record = await self._owned(session, principal_id, session_id)
            if session_record.status == ChatSessionStatus.ARCHIVED.value:
                raise SessionArchivedError()
            active = await session.scalar(
                select(ChatTurnRecord.id).where(
                    ChatTurnRecord.session_id == session_record.id,
                    ChatTurnRecord.status.in_(ACTIVE_TURN_STATUSES),
                )
            )
            if active is not None:
                raise ChatTurnActiveError()
            sequence = await session.scalar(
                select(func.coalesce(func.max(ChatMessageRecord.sequence), 0)).where(
                    ChatMessageRecord.session_id == session_record.id
                )
            )
            turn_id = uuid4()
            message_id = uuid4()
            message = ChatMessageRecord(
                id=message_id,
                session_id=session_record.id,
                turn_id=turn_id,
                sequence=int(sequence or 0) + 1,
                role=ChatRole.USER.value,
                content=content,
                status=ChatMessageStatus.COMPLETED.value,
                rendered_response=None,
                error=None,
                created_at=now,
                completed_at=now,
            )
            turn_record = ChatTurnRecord(
                id=turn_id,
                session_id=session_record.id,
                principal_id=principal_id,
                client_message_id=client_message_id,
                user_message_id=message_id,
                assistant_message_id=None,
                status=ChatTurnStatus.QUEUED.value,
                request_id=request_id,
                correlation_id=correlation_id,
                run_id=None,
                attempt=0,
                lease_expires_at=None,
                error=None,
                created_at=now,
                started_at=None,
                completed_at=None,
            )
            event_id = uuid4()
            outbox = ChatOutboxRecord(
                id=event_id,
                turn_id=turn_id,
                payload={
                    "turn_id": str(turn_id),
                    "principal_id": principal_id,
                    "request_id": str(request_id),
                    "correlation_id": str(correlation_id),
                },
                created_at=now,
                published_at=None,
            )
            session_record.updated_at = now
            session.add(message)
            await session.flush()
            session.add(turn_record)
            await session.flush()
            session.add(outbox)
        return ChatAcceptance(self._session(session_record), self._turn(turn_record), True)

    async def get_turn(self, principal_id: str, turn_id: UUID) -> ChatTurn:
        async with self._sessions() as session:
            record = await session.scalar(
                select(ChatTurnRecord).where(
                    ChatTurnRecord.id == turn_id,
                    ChatTurnRecord.principal_id == principal_id,
                )
            )
            if record is None:
                raise ChatTurnNotFoundError()
            return self._turn(record)

    async def claim_turn(self, principal_id: str, turn_id: UUID) -> ChatTurn | None:
        async with self._sessions.begin() as session:
            record = await session.scalar(
                select(ChatTurnRecord)
                .where(
                    ChatTurnRecord.id == turn_id,
                    ChatTurnRecord.principal_id == principal_id,
                )
                .with_for_update()
            )
            if record is None:
                raise ChatTurnNotFoundError()
            now = datetime.now(UTC)
            reclaimable = (
                record.status in ACTIVE_TURN_STATUSES
                and record.lease_expires_at is not None
                and record.lease_expires_at <= now
            )
            if record.status != ChatTurnStatus.QUEUED.value and not reclaimable:
                return None
            record.status = ChatTurnStatus.PLANNING.value
            record.started_at = record.started_at or now
            record.attempt += 1
            record.lease_expires_at = now + timedelta(minutes=5)
        return self._turn(record)

    async def set_turn_status(
        self, principal_id: str, turn_id: UUID, status: ChatTurnStatus
    ) -> ChatTurn:
        async with self._sessions.begin() as session:
            record = await session.scalar(
                select(ChatTurnRecord).where(
                    ChatTurnRecord.id == turn_id,
                    ChatTurnRecord.principal_id == principal_id,
                )
            )
            if record is None:
                raise ChatTurnNotFoundError()
            record.status = status.value
            record.lease_expires_at = datetime.now(UTC) + timedelta(minutes=5)
        return self._turn(record)

    async def get_context(
        self, principal_id: str, session_id: UUID, turn_id: UUID, limit: int
    ) -> ConversationContext:
        async with self._sessions() as session:
            await self._owned(session, principal_id, session_id)
            records = list(
                (
                    await session.scalars(
                        select(ChatMessageRecord)
                        .where(ChatMessageRecord.session_id == session_id)
                        .order_by(ChatMessageRecord.sequence.desc())
                        .limit(limit)
                    )
                ).all()
            )
        records.reverse()
        return ConversationContext(
            session_id=session_id,
            turn_id=turn_id,
            messages=tuple(
                ConversationContextMessage(
                    id=record.id,
                    role=ChatRole(record.role),
                    content=record.content,
                    created_at=record.created_at,
                )
                for record in records
            ),
        )

    async def complete_turn(
        self, principal_id: str, turn_id: UUID, response: RenderedResponse
    ) -> tuple[ChatTurn, ChatMessage]:
        async with self._sessions.begin() as session:
            record = await session.scalar(
                select(ChatTurnRecord)
                .where(
                    ChatTurnRecord.id == turn_id,
                    ChatTurnRecord.principal_id == principal_id,
                )
                .with_for_update()
            )
            if record is None:
                raise ChatTurnNotFoundError()
            sequence = await session.scalar(
                select(func.coalesce(func.max(ChatMessageRecord.sequence), 0)).where(
                    ChatMessageRecord.session_id == record.session_id
                )
            )
            now = datetime.now(UTC)
            partial = response.status.value == "partial"
            message_record = ChatMessageRecord(
                id=uuid4(),
                session_id=record.session_id,
                turn_id=record.id,
                sequence=int(sequence or 0) + 1,
                role=ChatRole.ASSISTANT.value,
                content=response.text,
                status=(
                    ChatMessageStatus.PARTIAL.value
                    if partial
                    else ChatMessageStatus.COMPLETED.value
                ),
                rendered_response=response.model_dump(mode="json"),
                error=None,
                created_at=now,
                completed_at=now,
            )
            session.add(message_record)
            await session.flush()
            record.assistant_message_id = message_record.id
            record.status = (
                ChatTurnStatus.PARTIAL.value if partial else ChatTurnStatus.COMPLETED.value
            )
            record.run_id = response.run_id
            record.lease_expires_at = None
            record.completed_at = now
            session_record = await session.get(ChatSessionRecord, record.session_id)
            if session_record is not None:
                session_record.updated_at = now
        return self._turn(record), self._message(message_record)

    async def fail_turn(self, principal_id: str, turn_id: UUID, error: ApiErrorDetail) -> ChatTurn:
        async with self._sessions.begin() as session:
            record = await session.scalar(
                select(ChatTurnRecord)
                .where(
                    ChatTurnRecord.id == turn_id,
                    ChatTurnRecord.principal_id == principal_id,
                )
                .with_for_update()
            )
            if record is None:
                raise ChatTurnNotFoundError()
            sequence = await session.scalar(
                select(func.coalesce(func.max(ChatMessageRecord.sequence), 0)).where(
                    ChatMessageRecord.session_id == record.session_id
                )
            )
            now = datetime.now(UTC)
            message = ChatMessageRecord(
                id=uuid4(),
                session_id=record.session_id,
                turn_id=record.id,
                sequence=int(sequence or 0) + 1,
                role=ChatRole.ASSISTANT.value,
                content=error.message,
                status=ChatMessageStatus.FAILED.value,
                rendered_response=None,
                error=error.model_dump(mode="json"),
                created_at=now,
                completed_at=now,
            )
            session.add(message)
            await session.flush()
            record.assistant_message_id = message.id
            record.status = ChatTurnStatus.FAILED.value
            record.error = error.model_dump(mode="json")
            record.lease_expires_at = None
            record.completed_at = now
        return self._turn(record)

    async def pending_events(self, limit: int = 50) -> tuple[PendingChatEvent, ...]:
        async with self._sessions() as session:
            records = (
                await session.scalars(
                    select(ChatOutboxRecord)
                    .where(ChatOutboxRecord.published_at.is_(None))
                    .order_by(ChatOutboxRecord.created_at)
                    .limit(limit)
                )
            ).all()
        return tuple(
            PendingChatEvent(
                id=record.id,
                turn_id=record.turn_id,
                principal_id=str(record.payload["principal_id"]),
                request_id=UUID(str(record.payload["request_id"])),
                correlation_id=UUID(str(record.payload["correlation_id"])),
            )
            for record in records
        )

    async def mark_published(self, event_id: UUID) -> None:
        async with self._sessions.begin() as session:
            record = await session.get(ChatOutboxRecord, event_id)
            if record is not None:
                record.published_at = datetime.now(UTC)
