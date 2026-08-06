from __future__ import annotations

import asyncio
import socket

from tradesentinel.platform.config import get_settings
from tradesentinel.platform.container import build_container
from tradesentinel.platform.events import RedisStreamEventBus


async def run() -> None:
    container = build_container(get_settings())
    try:
        if not isinstance(container.events, RedisStreamEventBus):
            raise RuntimeError("worker requires TRADESENTINEL_EVENT_BACKEND=redis")
        await container.events.consume_forever(
            group="tradesentinel-workers", consumer=socket.gethostname()
        )
    finally:
        await container.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
