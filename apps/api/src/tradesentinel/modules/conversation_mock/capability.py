from datetime import UTC, datetime

from tradesentinel.modules.conversation_mock.schemas import MockConversationInput
from tradesentinel.modules.conversation_mock.service import MockConversationService
from tradesentinel.platform.capabilities import Capability
from tradesentinel.platform.contracts import (
    CapabilityResult,
    ExecutionContext,
    MetricGrid,
    MetricItem,
    RunMetadata,
    RunStatus,
    SummaryCard,
)


class MockUnderstandCapability(Capability[MockConversationInput]):
    input_model = MockConversationInput

    def __init__(self, service: MockConversationService) -> None:
        self.service = service

    async def execute(
        self, context: ExecutionContext, payload: MockConversationInput
    ) -> CapabilityResult:
        del context
        started = datetime.now(UTC)
        result = await self.service.understand(payload.message)
        completed = datetime.now(UTC)
        return CapabilityResult(
            capability="",
            status=RunStatus.COMPLETED,
            data=result.model_dump(mode="json"),
            components=(
                MetricGrid(
                    id="mock-understanding",
                    metrics=(MetricItem(label="Words", value=str(result.word_count)),),
                ),
            ),
            metadata=RunMetadata(started_at=started, completed_at=completed),
        )


class MockReplyCapability(Capability[MockConversationInput]):
    input_model = MockConversationInput

    def __init__(self, service: MockConversationService) -> None:
        self.service = service

    async def execute(
        self, context: ExecutionContext, payload: MockConversationInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        result = await self.service.reply(payload.message)
        completed = datetime.now(UTC)
        history_size = len(context.conversation.messages) if context.conversation else 0
        return CapabilityResult(
            capability="",
            status=RunStatus.COMPLETED,
            data={**result.model_dump(mode="json"), "context_messages": history_size},
            summary=result.reply,
            components=(
                SummaryCard(
                    id="mock-response",
                    heading="Mock conversation response",
                    body="No LLM, provider, or market capability was invoked.",
                ),
            ),
            metadata=RunMetadata(started_at=started, completed_at=completed),
        )
