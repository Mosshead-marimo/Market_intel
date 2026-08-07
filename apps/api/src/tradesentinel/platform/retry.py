from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

from tradesentinel.platform.contracts import RetryPolicy
from tradesentinel.platform.errors import DomainError, RetryExhaustedError, TransientPlatformError

ResultT = TypeVar("ResultT")


def is_retryable_error(error: Exception) -> bool:
    if isinstance(error, DomainError):
        return error.retryable
    return isinstance(error, (TimeoutError, ConnectionError, TransientPlatformError))


class RetryStrategy:
    def __init__(
        self,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        random_value: Callable[[], float] = random.random,
    ) -> None:
        self._sleep = sleep
        self._random = random_value

    async def execute(
        self,
        operation: Callable[[int], Awaitable[ResultT]],
        policy: RetryPolicy,
    ) -> tuple[ResultT, int]:
        last_error: Exception | None = None
        for attempt in range(1, policy.max_attempts + 1):
            try:
                return await operation(attempt), attempt
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                last_error = exc
                if not is_retryable_error(exc) or attempt >= policy.max_attempts:
                    if attempt > 1 and is_retryable_error(exc):
                        raise RetryExhaustedError(attempt, exc) from exc
                    raise
                delay_ms = min(
                    policy.initial_delay_ms * (policy.multiplier ** (attempt - 1)),
                    policy.max_delay_ms,
                )
                jitter = delay_ms * policy.jitter_ratio * ((self._random() * 2) - 1)
                await self._sleep(max(0, delay_ms + jitter) / 1_000)
        assert last_error is not None
        raise RetryExhaustedError(policy.max_attempts, last_error)
