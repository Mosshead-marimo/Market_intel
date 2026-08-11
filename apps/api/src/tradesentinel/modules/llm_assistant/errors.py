from tradesentinel.platform.errors import DomainError


class LlmNotConfiguredError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "LLM_NOT_CONFIGURED",
            "No language model provider is configured.",
            status_code=503,
        )


class LlmPlanInvalidError(DomainError):
    def __init__(
        self, message: str = "The language model produced an invalid execution plan."
    ) -> None:
        super().__init__("LLM_PLAN_INVALID", message)


class LlmOutputInvalidError(DomainError):
    def __init__(self, provider: str | None = None) -> None:
        super().__init__(
            "LLM_OUTPUT_INVALID",
            "The generated response failed validation.",
            details={"provider": provider} if provider else None,
            status_code=502,
        )


class LlmEvidenceValidationError(DomainError):
    def __init__(self, violations: tuple[str, ...]) -> None:
        super().__init__(
            "LLM_EVIDENCE_VALIDATION_FAILED",
            "The generated response contained unsupported statements.",
            details={"violations": list(violations)},
            status_code=502,
        )


class LlmProviderUnavailableError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "LLM_PROVIDER_UNAVAILABLE",
            "Every configured language model provider is unavailable.",
            retryable=True,
            status_code=503,
        )


class LlmTimeoutError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "LLM_TIMEOUT",
            "The language model request timed out.",
            retryable=True,
            status_code=503,
        )


class LlmRateLimitedError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "LLM_RATE_LIMITED",
            "The language model rate limit was exceeded.",
            retryable=True,
            status_code=429,
        )


class LlmAuthenticationError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "LLM_AUTHENTICATION_FAILED",
            "The language model credentials were rejected.",
            status_code=502,
        )
