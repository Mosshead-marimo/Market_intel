from __future__ import annotations

from tradesentinel.domain.assistant import (
    AssistantCapabilityInput,
    AssistantConversationInput,
    AssistantGenerationInput,
    AssistantTask,
)
from tradesentinel.modules.llm_assistant.service import LlmAssistantService
from tradesentinel.platform.capabilities import Capability
from tradesentinel.platform.contracts import CapabilityResult, ExecutionContext


class ConversationCapability(Capability[AssistantConversationInput]):
    input_model = AssistantConversationInput

    def __init__(self, service: LlmAssistantService) -> None:
        self._service = service

    async def execute(
        self, context: ExecutionContext, payload: AssistantConversationInput
    ) -> CapabilityResult:
        return await self._service.conversation(context, payload.message)


class _GroundedCapability(Capability[AssistantCapabilityInput]):
    input_model = AssistantCapabilityInput
    task: AssistantTask
    capability_name: str

    def __init__(self, service: LlmAssistantService) -> None:
        self._service = service

    async def execute(
        self, context: ExecutionContext, payload: AssistantCapabilityInput
    ) -> CapabilityResult:
        return await self._service.generate(
            context,
            AssistantGenerationInput(
                question=payload.question,
                task=self.task,
                evidence=payload.evidence,
            ),
            self.capability_name,
        )


class SummarizeCapability(_GroundedCapability):
    task = AssistantTask.SUMMARY
    capability_name = "assistant.summarize"


class ExplainCapability(_GroundedCapability):
    task = AssistantTask.EXPLANATION
    capability_name = "assistant.explain"


class ResearchSynthesisCapability(_GroundedCapability):
    task = AssistantTask.RESEARCH_SYNTHESIS
    capability_name = "assistant.research_synthesize"


class MarketThesisCapability(_GroundedCapability):
    task = AssistantTask.MARKET_THESIS
    capability_name = "assistant.market_thesis"


class FollowUpsCapability(_GroundedCapability):
    task = AssistantTask.FOLLOW_UPS
    capability_name = "assistant.followups"
