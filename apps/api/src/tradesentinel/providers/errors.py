from __future__ import annotations

from typing import Any

from tradesentinel.platform.errors import DomainError
from tradesentinel.providers.contracts import ProviderKind


class ProviderError(DomainError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        provider: str | None = None,
        kind: ProviderKind | None = None,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
        status_code: int = 502,
    ) -> None:
        safe_details = dict(details or {})
        if provider is not None:
            safe_details["provider"] = provider
        if kind is not None:
            safe_details["kind"] = kind.value
        super().__init__(
            code,
            message,
            retryable=retryable,
            details=safe_details,
            status_code=status_code,
        )


class ProviderRegistryError(ProviderError):
    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__("PROVIDER_REGISTRY_INVALID", message, details=details, status_code=500)


class ProviderNotFoundError(ProviderError):
    def __init__(self, kind: ProviderKind, provider: str) -> None:
        super().__init__(
            "PROVIDER_NOT_FOUND",
            "A configured provider is not registered.",
            kind=kind,
            provider=provider,
            status_code=500,
        )


class ProviderNotConfiguredError(ProviderError):
    def __init__(self, kind: ProviderKind) -> None:
        super().__init__(
            "PROVIDER_NOT_CONFIGURED",
            "No provider is configured for the required category.",
            kind=kind,
            status_code=503,
        )


class ProviderUnavailableError(ProviderError):
    def __init__(self, provider: str, message: str = "The provider is unavailable.") -> None:
        super().__init__("PROVIDER_UNAVAILABLE", message, provider=provider, retryable=True)


class ProviderTimeoutError(ProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            "PROVIDER_TIMEOUT", "The provider request timed out.", provider=provider, retryable=True
        )


class ProviderRateLimitedError(ProviderError):
    def __init__(self, provider: str, retry_after_seconds: int) -> None:
        super().__init__(
            "PROVIDER_RATE_LIMITED",
            "The provider rate limit was exceeded.",
            provider=provider,
            retryable=True,
            details={"retry_after_seconds": retry_after_seconds},
            status_code=429,
        )


class ProviderAuthenticationError(ProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            "PROVIDER_AUTHENTICATION_FAILED",
            "The provider credentials were rejected.",
            provider=provider,
        )


class ProviderConfigurationError(ProviderError):
    def __init__(self, provider: str, message: str = "The provider is misconfigured.") -> None:
        super().__init__(
            "PROVIDER_CONFIGURATION_INVALID", message, provider=provider, status_code=500
        )


class ProviderOutputError(ProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            "PROVIDER_OUTPUT_INVALID",
            "The provider returned data that failed normalization.",
            provider=provider,
        )


class ProviderInvocationError(ProviderError):
    def __init__(self, provider: str) -> None:
        super().__init__(
            "PROVIDER_INVOCATION_FAILED",
            "The provider request failed.",
            provider=provider,
        )


class ProviderChainExhaustedError(ProviderError):
    def __init__(self, kind: ProviderKind, providers: tuple[str, ...]) -> None:
        super().__init__(
            "PROVIDER_CHAIN_EXHAUSTED",
            "Every configured provider was unavailable.",
            kind=kind,
            retryable=True,
            details={"providers": list(providers)},
            status_code=503,
        )
