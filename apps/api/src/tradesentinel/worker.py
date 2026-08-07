from __future__ import annotations

import asyncio
import socket

from tradesentinel.container import build_container
from tradesentinel.platform.config import get_settings
from tradesentinel.platform.events import RedisStreamEventBus


async def run() -> None:
    container = build_container(get_settings())
    try:
        if not isinstance(container.events, RedisStreamEventBus):
            raise RuntimeError("worker requires TRADESENTINEL_EVENT_BACKEND=redis")
        async with asyncio.TaskGroup() as group:
            group.create_task(
                container.events.consume_forever(
                    group="tradesentinel-workers", consumer=socket.gethostname()
                )
            )
            group.create_task(container.chat.dispatch_forever())
    finally:
        await container.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
