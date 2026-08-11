from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from tradesentinel.platform.contracts import (
    CommandArgument,
    CommandOption,
    ExecutionTarget,
    RetryPolicy,
    WorkflowDefinition,
)
from tradesentinel.platform.errors import ManifestError


class ManifestModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class CapabilityManifest(ManifestModel):
    name: str
    class_path: str
    version: str | None = None
    description: str
    dependencies: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    provides: tuple[str, ...] = ()
    idempotent: bool = False
    retry: RetryPolicy = Field(default_factory=RetryPolicy)


class ProviderRateLimitManifest(ManifestModel):
    requests: int = Field(default=60, ge=1)
    window_seconds: int = Field(default=60, ge=1)


class ProviderManifest(ManifestModel):
    kind: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(pattern=r"^[a-z][a-z0-9_.-]*$")
    class_path: str
    timeout_ms: int = Field(default=10_000, ge=1, le=300_000)
    rate_limit: ProviderRateLimitManifest = Field(default_factory=ProviderRateLimitManifest)


class CommandManifest(ManifestModel):
    name: str
    description: str
    target: ExecutionTarget
    arguments: tuple[CommandArgument, ...] = ()
    options: tuple[CommandOption, ...] = ()
    examples: tuple[str, ...] = ()
    planner_enabled: bool = True
    side_effect: Literal["read", "write"] = "read"

    @model_validator(mode="after")
    def validate_planner_access(self) -> CommandManifest:
        if self.planner_enabled and self.side_effect != "read":
            raise ValueError("planner-enabled commands must be read-only")
        return self


class IntentManifest(ManifestModel):
    name: str
    description: str
    examples: tuple[str, ...] = ()
    priority: int = 0
    target: ExecutionTarget
    match: Literal["exact", "fallback"] = "exact"
    input_field: str = Field(default="message", pattern=r"^[a-z][a-z0-9_]*$")

    @model_validator(mode="after")
    def validate_matching(self) -> IntentManifest:
        if self.match == "exact" and not self.examples:
            raise ValueError("exact intents require at least one example")
        if self.match == "fallback" and self.examples:
            raise ValueError("fallback intents cannot declare examples")
        return self


class EventConsumerManifest(ManifestModel):
    name: str
    target: ExecutionTarget


class EventsManifest(ManifestModel):
    consumes: tuple[EventConsumerManifest, ...] = ()
    produces: tuple[str, ...] = ()


class ModuleManifest(ManifestModel):
    name: str
    version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
    description: str
    api_router: str | None = None
    capabilities: tuple[CapabilityManifest, ...] = Field(min_length=1)
    providers: tuple[ProviderManifest, ...] = ()
    commands: tuple[CommandManifest, ...] = ()
    intents: tuple[IntentManifest, ...] = ()
    workflows: tuple[WorkflowDefinition, ...] = ()
    events: EventsManifest = Field(default_factory=EventsManifest)

    @model_validator(mode="after")
    def validate_local_names(self) -> ModuleManifest:
        groups = {
            "capability": [item.name for item in self.capabilities],
            "provider": [f"{item.kind}:{item.name}" for item in self.providers],
            "command": [item.name for item in self.commands],
            "intent": [item.name for item in self.intents],
            "workflow": [item.name for item in self.workflows],
        }
        for kind, names in groups.items():
            if len(names) != len(set(names)):
                raise ValueError(f"duplicate {kind} declarations in module {self.name}")
        return self


class ManifestParser:
    def parse(self, path: Path) -> ModuleManifest:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as exc:
            raise ManifestError(
                "The module manifest could not be read.", {"path": str(path)}
            ) from exc
        if not isinstance(raw, dict):
            raise ManifestError(
                "A module manifest must contain a YAML mapping.", {"path": str(path)}
            )
        try:
            return ModuleManifest.model_validate(raw)
        except ValidationError as exc:
            raise ManifestError(
                "The module manifest failed validation.",
                {"path": str(path), "errors": exc.errors(include_url=False)},
            ) from exc
