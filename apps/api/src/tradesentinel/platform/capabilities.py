from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from tradesentinel.platform.contracts import (
    CapabilityDescriptor,
    CapabilityResult,
    ExecutionContext,
    RetryPolicy,
)


class Capability[InputT: BaseModel](ABC):
    input_model: type[InputT]

    @abstractmethod
    async def execute(self, context: ExecutionContext, payload: InputT) -> CapabilityResult:
        """Execute a validated capability invocation."""


@dataclass(frozen=True)
class RegisteredCapability:
    descriptor: CapabilityDescriptor
    implementation: Capability[Any]
    retry_policy: RetryPolicy
