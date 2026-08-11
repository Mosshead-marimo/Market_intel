from datetime import UTC, datetime
from typing import cast

from pydantic import JsonValue

from tradesentinel.domain.stock_overview import (
    StockOverviewWindowInput,
)
from tradesentinel.modules.stock_overview.service import StockOverviewService
from tradesentinel.platform.capabilities import Capability
from tradesentinel.platform.contracts import (
    CapabilityResult,
    ExecutionContext,
    RunMetadata,
    RunStatus,
)


class WindowCapability(Capability[StockOverviewWindowInput]):
    input_model = StockOverviewWindowInput

    def __init__(self, service: StockOverviewService) -> None:
        self._service = service

    async def execute(
        self, context: ExecutionContext, payload: StockOverviewWindowInput
    ) -> CapabilityResult:
        del context
        started = datetime.now(UTC)
        output = self._service.window(payload.as_of)
        return CapabilityResult(
            capability="stock.overview.window",
            status=RunStatus.COMPLETED,
            data=cast(dict[str, JsonValue], output.model_dump(mode="json")),
            metadata=RunMetadata(
                started_at=started,
                completed_at=datetime.now(UTC),
                data_cutoff=output.end,
            ),
        )
