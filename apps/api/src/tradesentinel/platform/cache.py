from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass
from time import monotonic

from redis.asyncio import Redis


class CacheStore(ABC):
    @abstractmethod
    async def get(self, key: str) -> bytes | None: ...

    @abstractmethod
    async def set(self, key: str, value: bytes, ttl_seconds: int) -> None: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...


@dataclass
class _MemoryEntry:
    value: bytes
    expires_at: float


class InMemoryCacheStore(CacheStore):
    def __init__(self) -> None:
        self._items: dict[str, _MemoryEntry] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> bytes | None:
        async with self._lock:
            entry = self._items.get(key)
            if entry is None:
                return None
            if entry.expires_at <= monotonic():
                self._items.pop(key, None)
                return None
            return entry.value

    async def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        async with self._lock:
            self._items[key] = _MemoryEntry(value, monotonic() + ttl_seconds)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._items.pop(key, None)


class RedisCacheStore(CacheStore):
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def get(self, key: str) -> bytes | None:
        value = await self._redis.get(key)
        if value is None:
            return None
        return value if isinstance(value, bytes) else str(value).encode()

    async def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        await self._redis.set(key, value, ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)
