from __future__ import annotations

from typing import cast

from redis.asyncio import Redis
from tradesentinel.platform.cache import InMemoryCacheStore, RedisCacheStore


async def test_memory_cache_expires_and_deletes(monkeypatch) -> None:
    clock = 100.0
    monkeypatch.setattr("tradesentinel.platform.cache.monotonic", lambda: clock)
    cache = InMemoryCacheStore()
    await cache.set("key", b"value", 10)
    assert await cache.get("key") == b"value"
    clock = 111.0
    assert await cache.get("key") is None
    await cache.set("key", b"new", 10)
    await cache.delete("key")
    assert await cache.get("key") is None


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.expiries: dict[str, int] = {}

    async def get(self, key: str) -> bytes | None:
        return self.values.get(key)

    async def set(self, key: str, value: bytes, *, ex: int) -> None:
        self.values[key] = value
        self.expiries[key] = ex

    async def delete(self, key: str) -> None:
        self.values.pop(key, None)


async def test_redis_cache_uses_expiring_values() -> None:
    redis = FakeRedis()
    cache = RedisCacheStore(cast(Redis, redis))
    await cache.set("key", b"value", 15)
    assert redis.expiries["key"] == 15
    assert await cache.get("key") == b"value"
    await cache.delete("key")
    assert await cache.get("key") is None
