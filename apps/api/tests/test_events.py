from tradesentinel.platform.contracts import EventEnvelope, ExecutionContext
from tradesentinel.platform.events import InMemoryEventBus


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
