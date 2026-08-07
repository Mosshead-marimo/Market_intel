from typing import Any, cast

from tradesentinel.platform.contracts import EventEnvelope, ExecutionContext
from tradesentinel.platform.events import InMemoryEventBus, RedisStreamEventBus


async def test_in_memory_event_bus_is_deterministic() -> None:
    bus = InMemoryEventBus()
    received = []

    async def handler(event: EventEnvelope) -> None:
        received.append(event.name)

    context = ExecutionContext()
    bus.subscribe("test.completed", handler)
    await bus.publish(
        EventEnvelope(name="test.completed", correlation_id=context.correlation_id, producer="test")
    )
    assert received == ["test.completed"]


class FakeRedis:
    def __init__(self, event: EventEnvelope) -> None:
        self.event = event
        self.added: list[tuple[str, dict[str, str]]] = []
        self.acknowledged: list[object] = []

    async def xgroup_create(self, *args: object, **kwargs: object) -> None:
        del args, kwargs

    async def xreadgroup(self, *args: object, **kwargs: object):
        del args, kwargs
        return [
            (
                b"tradesentinel:events",
                [(b"1-0", {b"event": self.event.model_dump_json().encode()})],
            )
        ]

    async def xadd(self, stream: str, fields: dict[str, str]) -> bytes:
        self.added.append((stream, fields))
        return b"2-0"

    async def xack(self, *args: object) -> None:
        self.acknowledged.append(args)


class FakeClaimingRedis(FakeRedis):
    async def xautoclaim(self, *args: object, **kwargs: object):
        del args, kwargs
        return (
            b"0-0",
            [(b"0-1", {b"event": self.event.model_dump_json().encode()})],
            [],
        )

    async def xreadgroup(self, *args: object, **kwargs: object):
        del args, kwargs
        return []


async def test_redis_consumer_dead_letters_permanent_failures() -> None:
    context = ExecutionContext()
    event = EventEnvelope(
        name="test.failed", correlation_id=context.correlation_id, producer="test"
    )
    redis = FakeRedis(event)
    bus = RedisStreamEventBus(cast(Any, redis))

    async def handler(received: EventEnvelope) -> None:
        del received
        raise ValueError("permanent")

    bus.subscribe("test.failed", handler)
    assert await bus.consume_once(group="test", consumer="one", block_ms=0) == 1
    assert redis.added[0][0] == "tradesentinel:events:dead-letter"
    assert redis.acknowledged


async def test_redis_consumer_requeues_transient_failures() -> None:
    context = ExecutionContext()
    event = EventEnvelope(name="test.retry", correlation_id=context.correlation_id, producer="test")
    redis = FakeRedis(event)
    bus = RedisStreamEventBus(cast(Any, redis), max_attempts=3)

    async def handler(received: EventEnvelope) -> None:
        del received
        raise ConnectionError("temporary")

    bus.subscribe("test.retry", handler)
    await bus.consume_once(group="test", consumer="one", block_ms=0)
    assert redis.added[0][0] == "tradesentinel:events"
    assert '"attempt":1' in redis.added[0][1]["event"]


async def test_redis_consumer_reclaims_and_acknowledges_stale_messages() -> None:
    context = ExecutionContext()
    event = EventEnvelope(
        name="test.reclaimed", correlation_id=context.correlation_id, producer="test"
    )
    redis = FakeClaimingRedis(event)
    bus = RedisStreamEventBus(cast(Any, redis))
    received: list[str] = []

    async def handler(received_event: EventEnvelope) -> None:
        received.append(received_event.name)

    bus.subscribe("test.reclaimed", handler)
    assert await bus.consume_once(group="test", consumer="two", block_ms=0) == 1
    assert received == ["test.reclaimed"]
    assert redis.acknowledged[0][-1] == b"0-1"
