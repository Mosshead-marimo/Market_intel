from __future__ import annotations

from abc import ABC, abstractmethod

from tradesentinel.platform.contracts import ExecutionContext, IntentDescriptor, IntentMatch
from tradesentinel.platform.errors import IntentAmbiguousError, IntentNotResolvedError


def normalize_intent_text(value: str) -> str:
    return " ".join(value.casefold().split())


class IntentResolver(ABC):
    @abstractmethod
    async def resolve(
        self,
        text: str,
        candidates: tuple[IntentDescriptor, ...],
        context: ExecutionContext,
    ) -> IntentMatch: ...


class ExactExampleIntentResolver(IntentResolver):
    async def resolve(
        self,
        text: str,
        candidates: tuple[IntentDescriptor, ...],
        context: ExecutionContext,
    ) -> IntentMatch:
        del context
        normalized = normalize_intent_text(text)
        matches = [
            candidate
            for candidate in candidates
            if candidate.match == "exact"
            and normalized in {normalize_intent_text(example) for example in candidate.examples}
        ]
        if not matches:
            fallbacks = [candidate for candidate in candidates if candidate.match == "fallback"]
            if not fallbacks:
                raise IntentNotResolvedError()
            fallback = fallbacks[0]
            return IntentMatch(
                intent=fallback.name,
                target=fallback.target,
                confidence=0.0,
                input_field=fallback.input_field,
            )
        highest_priority = max(candidate.priority for candidate in matches)
        winners = [candidate for candidate in matches if candidate.priority == highest_priority]
        targets = {(winner.target.kind, winner.target.name) for winner in winners}
        if len(targets) > 1:
            raise IntentAmbiguousError(sorted(winner.name for winner in winners))
        winner = sorted(winners, key=lambda item: item.name)[0]
        return IntentMatch(
            intent=winner.name,
            target=winner.target,
            confidence=1.0,
            input_field=winner.input_field,
        )
