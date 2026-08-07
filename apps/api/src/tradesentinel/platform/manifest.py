from __future__ import annotations

from pathlib import Path

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


class CommandManifest(ManifestModel):
    name: str
    description: str
    target: ExecutionTarget
    arguments: tuple[CommandArgument, ...] = ()
    options: tuple[CommandOption, ...] = ()
    examples: tuple[str, ...] = ()


class IntentManifest(ManifestModel):
    name: str
    description: str
    examples: tuple[str, ...] = Field(min_length=1)
    priority: int = 0
    target: ExecutionTarget


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
    capabilities: tuple[CapabilityManifest, ...] = Field(min_length=1)
    commands: tuple[CommandManifest, ...] = ()
    intents: tuple[IntentManifest, ...] = ()
    workflows: tuple[WorkflowDefinition, ...] = ()
    events: EventsManifest = Field(default_factory=EventsManifest)

    @model_validator(mode="after")
    def validate_local_names(self) -> ModuleManifest:
        groups = {
            "capability": [item.name for item in self.capabilities],
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
