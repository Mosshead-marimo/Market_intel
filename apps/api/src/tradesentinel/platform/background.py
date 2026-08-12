from __future__ import annotations

from abc import ABC, abstractmethod


class BackgroundWorker(ABC):
    @abstractmethod
    async def run_forever(self) -> None: ...
