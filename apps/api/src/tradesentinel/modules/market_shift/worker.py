from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from tradesentinel.domain.market_shift import MarketShiftObservationQuery, MarketShiftScoreInput
from tradesentinel.modules.market_shift.repository import MarketShiftPersistenceService
from tradesentinel.platform.background import BackgroundWorker
from tradesentinel.platform.contracts import (
    CapabilityExecutionRequest,
    CapabilityResult,
    ExecutionContext,
)
from tradesentinel.platform.errors import DomainError
from tradesentinel.platform.gateway import ExecutionGateway


class MarketShiftBackgroundWorker(BackgroundWorker):
    def __init__(
        self, persistence: MarketShiftPersistenceService, gateway: ExecutionGateway
    ) -> None:
        self.persistence = persistence
        self.gateway = gateway

    async def run_once(self) -> int:
        now = datetime.now(UTC)
        watchlist = await self.persistence.repository.watchlist()
        due = [
            item
            for item in watchlist.items
            if item.enabled and (item.next_run_at is None or item.next_run_at <= now)
        ]
        for entry in due:
            context = ExecutionContext(principal_id="market-shift-scheduler")
            try:
                loaded = await self.gateway.execute_request(
                    CapabilityExecutionRequest(
                        capability="market_shift.observations.load",
                        payload=MarketShiftObservationQuery(
                            instrument=entry.instrument,
                            as_of=now,
                            window_days=entry.window_days,
                            idempotency_key=(
                                f"scheduled:{entry.watchlist_id}:{now.date().isoformat()}"
                            ),
                        ).model_dump(mode="json"),
                    ),
                    context,
                )
                load_result = loaded.result
                if isinstance(load_result, CapabilityResult):
                    await self.gateway.execute_request(
                        CapabilityExecutionRequest(
                            capability="market_shift.calculate",
                            payload=MarketShiftScoreInput.model_validate(
                                load_result.data
                            ).model_dump(mode="json"),
                        ),
                        context,
                    )
            except DomainError:
                pass
            await self.persistence.repository.save_watchlist(
                entry.model_copy(
                    update={"last_run_at": now, "next_run_at": now + timedelta(days=1)}
                )
            )
        return len(due)

    async def run_forever(self) -> None:
        while True:
            processed = await self.run_once()
            await asyncio.sleep(1 if processed else 30)
