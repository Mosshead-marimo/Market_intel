from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from tradesentinel.platform.contracts import (
    CapabilityResult,
    RenderedResponse,
    WorkflowResult,
)


class ChatSessionCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="New chat", min_length=1, max_length=120)


class ChatSessionUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, min_length=1, max_length=120)
    archived: bool | None = None

    @model_validator(mode="after")
    def require_change(self) -> ChatSessionUpdateRequest:
        if self.title is None and self.archived is None:
            raise ValueError("at least one session change is required")
        return self


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=20_000)
    session_id: UUID | None = None
    client_message_id: UUID


class CommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command: str = Field(min_length=1, max_length=1_000)
    session_id: UUID | None = None


class WorkflowRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input: dict[str, JsonValue] = Field(default_factory=dict)
    session_id: UUID | None = None


class CommandResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request_id: UUID
    result: CapabilityResult | WorkflowResult
    response: RenderedResponse


class WorkflowResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request_id: UUID
    result: WorkflowResult
    response: RenderedResponse


class RunSourcesResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    run_id: UUID
    sources: tuple[object, ...] = ()
