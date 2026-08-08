from __future__ import annotations

from collections.abc import Sequence
from typing import Any


class DomainError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
        status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}
        self.status_code = status_code


class RegistryError(DomainError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__("REGISTRY_INVALID", message, details=details, status_code=500)


class ManifestError(DomainError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__("MANIFEST_INVALID", message, details=details, status_code=500)


class DiscoveryError(DomainError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__("MODULE_DISCOVERY_FAILED", message, details=details, status_code=500)


class DependencyResolutionError(DomainError):
    def __init__(self, dependency: str, reason: str) -> None:
        super().__init__(
            "DEPENDENCY_RESOLUTION_FAILED",
            f"Dependency '{dependency}' could not be resolved.",
            details={"dependency": dependency, "reason": reason},
            status_code=500,
        )


class CommandSyntaxError(DomainError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__("COMMAND_INVALID", message, details=details)


class IntentNotResolvedError(DomainError):
    def __init__(self) -> None:
        super().__init__("INTENT_NOT_RESOLVED", "No registered intent matched the request.")


class IntentAmbiguousError(DomainError):
    def __init__(self, intents: list[str]) -> None:
        super().__init__(
            "INTENT_AMBIGUOUS",
            "More than one registered intent matched the request.",
            details={"intents": intents},
        )


class PermissionDeniedError(DomainError):
    def __init__(self, permissions: list[str]) -> None:
        super().__init__(
            "PERMISSION_DENIED",
            "The execution context does not grant the required permissions.",
            details={"missing_permissions": permissions},
            status_code=403,
        )


class PayloadValidationError(DomainError):
    def __init__(self, errors: Sequence[object]) -> None:
        super().__init__(
            "PAYLOAD_INVALID",
            "The capability payload is invalid.",
            details={"errors": list(errors)},
        )


class CapabilityOutputError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "CAPABILITY_OUTPUT_INVALID",
            "The capability returned an invalid result.",
            status_code=500,
        )


class WorkflowCompilationError(DomainError):
    def __init__(self, message: str) -> None:
        super().__init__("WORKFLOW_INVALID", message, status_code=500)


class WorkflowInputBindingError(DomainError):
    def __init__(self, step: str, destination: str, source: str) -> None:
        super().__init__(
            "WORKFLOW_INPUT_BINDING_FAILED",
            "A workflow step input could not be resolved.",
            details={"step": step, "destination": destination, "source": source},
        )


class RetryExhaustedError(DomainError):
    def __init__(self, attempts: int, last_error: Exception) -> None:
        super().__init__(
            "RETRY_EXHAUSTED",
            "The operation failed after all retry attempts.",
            retryable=False,
            details={"attempts": attempts, "last_error_type": type(last_error).__name__},
            status_code=503,
        )


class TransientPlatformError(DomainError):
    def __init__(self, message: str) -> None:
        super().__init__("TRANSIENT_PLATFORM_ERROR", message, retryable=True, status_code=503)


class InternalExecutionError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "EXECUTION_FAILED",
            "The execution could not be completed.",
            retryable=False,
            status_code=500,
        )


class EventBusError(DomainError):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(code, message, retryable=retryable, status_code=500)


class CapabilityNotInstalledError(DomainError):
    def __init__(self, capability: str) -> None:
        super().__init__(
            "CAPABILITY_NOT_INSTALLED",
            f"The '{capability}' capability is not installed.",
            details={"capability": capability},
            status_code=501,
        )


class RateLimitError(DomainError):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "RATE_LIMITED",
            "The request rate limit has been exceeded.",
            retryable=True,
            details={"retry_after_seconds": retry_after_seconds},
            status_code=429,
        )


class SessionNotFoundError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "SESSION_NOT_FOUND", "The requested chat session was not found.", status_code=404
        )


class SessionArchivedError(DomainError):
    def __init__(self) -> None:
        super().__init__("SESSION_ARCHIVED", "The chat session is archived.", status_code=409)


class ChatTurnActiveError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "CHAT_TURN_ACTIVE",
            "Another message is already being processed for this session.",
            status_code=409,
        )


class ChatTurnNotFoundError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "CHAT_TURN_NOT_FOUND", "The requested chat turn was not found.", status_code=404
        )


class ChatStreamExpiredError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "CHAT_STREAM_EXPIRED",
            "The replay stream has expired; retrieve the completed turn instead.",
            status_code=410,
        )


class ChatQueueError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "CHAT_QUEUE_UNAVAILABLE",
            "The message was saved but could not be queued for execution.",
            retryable=True,
            status_code=503,
        )
