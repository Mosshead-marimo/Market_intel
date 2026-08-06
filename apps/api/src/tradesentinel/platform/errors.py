from __future__ import annotations

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
