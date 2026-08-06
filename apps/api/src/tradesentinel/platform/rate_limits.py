from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from time import monotonic

from redis.asyncio import Redis


class RateLimiter(ABC):
    @abstractmethod
    async def allow(self, key: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]: ...


class InMemoryRateLimiter(RateLimiter):
    def __init__(self) -> None:
        self._windows: dict[str, tuple[float, int]] = defaultdict(lambda: (monotonic(), 0))

    async def allow(self, key: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
        started, count = self._windows[key]
        now = monotonic()
        if now - started >= window_seconds:
            started, count = now, 0
        count += 1
        self._windows[key] = (started, count)
        retry_after = max(1, int(window_seconds - (now - started)))
        return count <= limit, retry_after


class RedisRateLimiter(RateLimiter):
    def __init__(self, redis: Redis) -> None:
        self.redis = redis

    async def allow(self, key: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
        count = await self.redis.incr(f"tradesentinel:rate:{key}")
        if count == 1:
            await self.redis.expire(f"tradesentinel:rate:{key}", window_seconds)
        ttl = await self.redis.ttl(f"tradesentinel:rate:{key}")
        return count <= limit, max(1, ttl)
