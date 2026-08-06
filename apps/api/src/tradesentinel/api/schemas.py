from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from tradesentinel.platform.contracts import CapabilityResult, WorkflowResult


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
    result: CapabilityResult


class WorkflowResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    request_id: UUID
    result: WorkflowResult


class RunSourcesResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    run_id: UUID
    sources: tuple[object, ...] = ()
