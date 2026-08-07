from __future__ import annotations

import asyncio
import json
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Awaitable, Callable

from redis.asyncio import Redis

from tradesentinel.platform.contracts import EventEnvelope
from tradesentinel.platform.errors import EventBusError
from tradesentinel.platform.retry import is_retryable_error

EventHandler = Callable[[EventEnvelope], Awaitable[None]]


class EventBus(ABC):
    @abstractmethod
    async def publish(self, event: EventEnvelope) -> str:
        """Publish an event and return its transport identifier."""

    @abstractmethod
    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        """Register a local event handler."""


class InMemoryEventBus(EventBus):
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self.events: list[EventEnvelope] = []

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        if handler in self._handlers[event_name]:
            raise EventBusError(
                "EVENT_SUBSCRIPTION_DUPLICATE",
                f"A handler is already subscribed to '{event_name}'.",
            )
        self._handlers[event_name].append(handler)

    async def publish(self, event: EventEnvelope) -> str:
        self.events.append(event)
        for handler in tuple(self._handlers[event.name]):
            await handler(event)
        return str(event.event_id)


class RedisStreamEventBus(EventBus):
    def __init__(
        self,
        redis: Redis,
        *,
        stream: str = "tradesentinel:events",
        dead_letter_stream: str = "tradesentinel:events:dead-letter",
        max_attempts: int = 3,
    ) -> None:
        self.redis = redis
        self.stream = stream
        self.dead_letter_stream = dead_letter_stream
        self.max_attempts = max_attempts
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        if handler in self._handlers[event_name]:
            raise EventBusError(
                "EVENT_SUBSCRIPTION_DUPLICATE",
                f"A handler is already subscribed to '{event_name}'.",
            )
        self._handlers[event_name].append(handler)

    async def publish(self, event: EventEnvelope) -> str:
        try:
            identifier = await self.redis.xadd(
                self.stream,
                {"event": event.model_dump_json()},
            )
        except Exception as exc:
            raise EventBusError(
                "EVENT_PUBLISH_FAILED", "The event could not be published.", retryable=True
            ) from exc
        return identifier.decode() if isinstance(identifier, bytes) else str(identifier)

    async def ensure_group(self, group: str) -> None:
        try:
            await self.redis.xgroup_create(self.stream, group, id="0", mkstream=True)
        except Exception as exc:  # redis has no stable cross-version BUSYGROUP type
            if "BUSYGROUP" not in str(exc):
                raise

    async def consume_once(
        self,
        *,
        group: str,
        consumer: str,
        block_ms: int = 1_000,
    ) -> int:
        await self.ensure_group(group)
        records = await self.redis.xreadgroup(
            group,
            consumer,
            {self.stream: ">"},
            count=10,
            block=block_ms,
        )
        processed = 0
        for _, messages in records:
            for message_id, fields in messages:
                raw = fields.get(b"event") or fields.get("event")
                if isinstance(raw, bytes):
                    raw = raw.decode()
                event = EventEnvelope.model_validate(json.loads(str(raw)))
                try:
                    for handler in tuple(self._handlers[event.name]):
                        await handler(event)
                except Exception as exc:
                    retried = event.model_copy(update={"attempt": event.attempt + 1})
                    if not is_retryable_error(exc) or retried.attempt >= self.max_attempts:
                        await self.redis.xadd(
                            self.dead_letter_stream,
                            {
                                "event": retried.model_dump_json(),
                                "reason": type(exc).__name__,
                            },
                        )
                    else:
                        await self.publish(retried)
                finally:
                    await self.redis.xack(self.stream, group, message_id)
                processed += 1
        return processed

    async def consume_forever(self, *, group: str, consumer: str) -> None:
        while True:
            await self.consume_once(group=group, consumer=consumer)
            await asyncio.sleep(0)
