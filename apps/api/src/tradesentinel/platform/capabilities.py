from __future__ import annotations

from abc import ABC, abstractmethod

from pydantic import BaseModel

from tradesentinel.platform.contracts import (
    CapabilityDescriptor,
    CapabilityResult,
    ExecutionContext,
)


class Capability[InputT: BaseModel](ABC):
    descriptor: CapabilityDescriptor
    input_model: type[InputT]

    @abstractmethod
    async def execute(self, context: ExecutionContext, payload: InputT) -> CapabilityResult:
        """Execute a validated capability invocation."""

    async def invoke(self, context: ExecutionContext, raw_payload: object) -> CapabilityResult:
        payload = self.input_model.model_validate(raw_payload)
        return await self.execute(context, payload)
