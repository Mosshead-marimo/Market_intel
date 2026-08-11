from tradesentinel.platform.errors import DomainError


class SentimentWindowError(DomainError):
    def __init__(self) -> None:
        super().__init__("SENTIMENT_WINDOW_INVALID", "The sentiment time window is invalid.")


class SentimentPersistenceError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "SENTIMENT_PERSISTENCE_FAILED",
            "The sentiment analysis could not be persisted.",
            retryable=True,
            status_code=503,
        )
