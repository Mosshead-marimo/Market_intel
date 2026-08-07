from datetime import UTC, datetime

from tradesentinel.modules.system.schemas import PingInput
from tradesentinel.modules.system.service import SystemService
from tradesentinel.platform.capabilities import Capability
from tradesentinel.platform.contracts import (
    CapabilityResult,
    ExecutionContext,
    RunMetadata,
    RunStatus,
    SummaryCard,
)


class SystemPingCapability(Capability[PingInput]):
    input_model = PingInput

    def __init__(self, service: SystemService) -> None:
        self.service = service

    async def execute(self, context: ExecutionContext, payload: PingInput) -> CapabilityResult:
        started = datetime.now(UTC)
        output = await self.service.ping(payload)
        completed = datetime.now(UTC)
        return CapabilityResult(
            capability="",
            status=RunStatus.COMPLETED,
            data=output.model_dump(mode="json"),
            summary="TradeSentinel platform is responding.",
            components=(
                SummaryCard(
                    id="system-status",
                    heading="Platform online",
                    body=f"The {output.service} capability runtime replied {output.reply}.",
                ),
            ),
            metadata=RunMetadata(
                started_at=started,
                completed_at=completed,
                duration_ms=max(0, int((completed - started).total_seconds() * 1000)),
                freshness="fresh",
            ),
        )
