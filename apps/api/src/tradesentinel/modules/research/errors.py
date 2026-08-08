from __future__ import annotations

from uuid import UUID

from tradesentinel.platform.errors import DomainError


class ResearchEventNotFoundError(DomainError):
    def __init__(self, event_id: UUID) -> None:
        super().__init__(
            "RESEARCH_EVENT_NOT_FOUND",
            "The requested research event was not found.",
            details={"event_id": str(event_id)},
            status_code=404,
        )


class ResearchPersistenceError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "RESEARCH_PERSISTENCE_FAILED",
            "Research evidence could not be persisted.",
            retryable=True,
            status_code=503,
        )
