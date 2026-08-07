from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from uuid import UUID

from pydantic import TypeAdapter
from redis.asyncio import Redis

from tradesentinel.platform.contracts import ChatStreamEvent
from tradesentinel.platform.errors import EventBusError

_EVENT_ADAPTER: TypeAdapter[ChatStreamEvent] = TypeAdapter(ChatStreamEvent)


@dataclass(frozen=True)
class ChatStreamRecord:
    cursor: str
    event: ChatStreamEvent


class ChatStreamStore(ABC):
    @abstractmethod
    async def next_sequence(self, turn_id: UUID) -> int: ...

    @abstractmethod
    async def append(self, turn_id: UUID, event: ChatStreamEvent) -> str: ...

    @abstractmethod
    async def read(
        self, turn_id: UUID, after: str | None, *, block_ms: int
    ) -> tuple[ChatStreamRecord, ...]: ...

    @abstractmethod
    async def exists(self, turn_id: UUID) -> bool: ...


class InMemoryChatStreamStore(ChatStreamStore):
    def __init__(self) -> None:
        self._events: dict[UUID, list[ChatStreamRecord]] = {}
        self._sequences: dict[UUID, int] = {}
        self._condition = asyncio.Condition()

    async def next_sequence(self, turn_id: UUID) -> int:
        async with self._condition:
            value = self._sequences.get(turn_id, 0) + 1
            self._sequences[turn_id] = value
            return value

    async def append(self, turn_id: UUID, event: ChatStreamEvent) -> str:
        async with self._condition:
            records = self._events.setdefault(turn_id, [])
            cursor = str(len(records) + 1)
            records.append(ChatStreamRecord(cursor, event))
            self._condition.notify_all()
            return cursor

    async def read(
        self, turn_id: UUID, after: str | None, *, block_ms: int
    ) -> tuple[ChatStreamRecord, ...]:
        offset = int(after or "0")
        async with self._condition:
            if len(self._events.get(turn_id, ())) <= offset:
                try:
                    await asyncio.wait_for(self._condition.wait(), timeout=max(block_ms, 1) / 1_000)
                except TimeoutError:
                    return ()
            return tuple(self._events.get(turn_id, ())[offset:])

    async def exists(self, turn_id: UUID) -> bool:
        return turn_id in self._events


class RedisChatStreamStore(ChatStreamStore):
    def __init__(self, redis: Redis, *, retention_seconds: int = 86_400) -> None:
        self._redis = redis
        self._retention = retention_seconds

    @staticmethod
    def _key(turn_id: UUID) -> str:
        return f"tradesentinel:chat:turn:{turn_id}:events"

    @staticmethod
    def _sequence_key(turn_id: UUID) -> str:
        return f"tradesentinel:chat:turn:{turn_id}:sequence"

    async def next_sequence(self, turn_id: UUID) -> int:
        try:
            key = self._sequence_key(turn_id)
            value = await self._redis.incr(key)
            await self._redis.expire(key, self._retention)
            return int(value)
        except Exception as exc:
            raise EventBusError(
                "CHAT_STREAM_WRITE_FAILED",
                "The chat stream sequence could not be allocated.",
                retryable=True,
            ) from exc

    async def append(self, turn_id: UUID, event: ChatStreamEvent) -> str:
        try:
            key = self._key(turn_id)
            identifier = await self._redis.xadd(
                key,
                {"event": _EVENT_ADAPTER.dump_json(event).decode()},
                maxlen=2_000,
                approximate=True,
            )
            await self._redis.expire(key, self._retention)
            return identifier.decode() if isinstance(identifier, bytes) else str(identifier)
        except Exception as exc:
            raise EventBusError(
                "CHAT_STREAM_WRITE_FAILED",
                "The chat stream event could not be persisted.",
                retryable=True,
            ) from exc

    async def read(
        self, turn_id: UUID, after: str | None, *, block_ms: int
    ) -> tuple[ChatStreamRecord, ...]:
        try:
            records = await self._redis.xread(
                {self._key(turn_id): after or "0-0"},
                count=100,
                block=block_ms,
            )
        except Exception as exc:
            raise EventBusError(
                "CHAT_STREAM_READ_FAILED",
                "The chat stream could not be read.",
                retryable=True,
            ) from exc
        parsed: list[ChatStreamRecord] = []
        for _, messages in records:
            for identifier, fields in messages:
                raw = fields.get(b"event") or fields.get("event")
                if isinstance(raw, bytes):
                    raw = raw.decode()
                event = _EVENT_ADAPTER.validate_python(json.loads(str(raw)))
                cursor = identifier.decode() if isinstance(identifier, bytes) else str(identifier)
                parsed.append(ChatStreamRecord(cursor, event))
        return tuple(parsed)

    async def exists(self, turn_id: UUID) -> bool:
        return bool(await self._redis.exists(self._key(turn_id)))
