from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tradesentinel.platform.contracts import (
    EvidenceRecord,
    EvidenceSource,
    FollowUpQuestion,
    GroundedClaim,
)


class AssistantContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AssistantTask(StrEnum):
    CONVERSATION = "conversation"
    SUMMARY = "summary"
    EXPLANATION = "explanation"
    RESEARCH_SYNTHESIS = "research_synthesis"
    MARKET_THESIS = "market_thesis"
    FOLLOW_UPS = "follow_ups"


class AssistantPlanMode(StrEnum):
    EXECUTE = "execute"
    CLARIFY = "clarify"
    OUT_OF_SCOPE = "out_of_scope"


class PlannedCommand(AssistantContract):
    command: str = Field(pattern=r"^/[a-z][^\r\n]{0,499}$")


class AssistantPlan(AssistantContract):
    mode: AssistantPlanMode
    task: AssistantTask = AssistantTask.CONVERSATION
    commands: tuple[PlannedCommand, ...] = Field(default=(), max_length=4)
    follow_up_questions: tuple[FollowUpQuestion, ...] = Field(default=(), max_length=3)

    @model_validator(mode="after")
    def validate_mode(self) -> AssistantPlan:
        if self.mode == AssistantPlanMode.EXECUTE and not self.commands:
            raise ValueError("execute plans require at least one command")
        if self.mode != AssistantPlanMode.EXECUTE and self.commands:
            raise ValueError("non-execute plans cannot contain commands")
        if self.mode == AssistantPlanMode.CLARIFY and not self.follow_up_questions:
            raise ValueError("clarify plans require follow-up questions")
        commands = [item.command for item in self.commands]
        if len(commands) != len(set(commands)):
            raise ValueError("planned commands must be unique")
        return self


class EvidencePacket(AssistantContract):
    question: str = Field(min_length=1, max_length=20_000)
    records: tuple[EvidenceRecord, ...]
    sources: tuple[EvidenceSource, ...] = ()


class AssistantGenerationInput(AssistantContract):
    question: str = Field(min_length=1, max_length=20_000)
    task: AssistantTask
    evidence: EvidencePacket


class AssistantGeneratedOutput(AssistantContract):
    claims: tuple[GroundedClaim, ...] = ()
    supportive: tuple[GroundedClaim, ...] = ()
    contradictory: tuple[GroundedClaim, ...] = ()
    uncertainties: tuple[GroundedClaim, ...] = ()
    follow_up_questions: tuple[FollowUpQuestion, ...] = Field(default=(), max_length=3)

    @model_validator(mode="after")
    def validate_content(self) -> AssistantGeneratedOutput:
        identifiers = [
            claim.claim_id
            for group in (
                self.claims,
                self.supportive,
                self.contradictory,
                self.uncertainties,
            )
            for claim in group
        ]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("generated claim IDs must be unique")
        return self


class AssistantConversationInput(AssistantContract):
    message: str = Field(min_length=1, max_length=20_000)


class AssistantCapabilityInput(AssistantContract):
    question: str = Field(min_length=1, max_length=20_000)
    evidence: EvidencePacket


class LlmGenerationAudit(AssistantContract):
    id: UUID
    request_id: UUID
    correlation_id: UUID
    run_id: UUID | None = None
    stage: str
    provider: str
    model: str
    prompt_version: str
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    output_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    evidence_ids: tuple[str, ...] = ()
    planned_commands: tuple[str, ...] = ()
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    validation_attempts: int = Field(ge=0, le=2)
    validation_status: str
    failure_code: str | None = None
    created_at: datetime
