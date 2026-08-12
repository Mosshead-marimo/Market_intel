from tradesentinel.platform.errors import DomainError


class MarketShiftInputIncompleteError(DomainError):
    def __init__(self, missing: tuple[str, ...]) -> None:
        super().__init__(
            "MARKET_SHIFT_INPUT_INCOMPLETE",
            "A Market Shift score requires current and prior evidence for all input categories.",
            status_code=422,
            details={"missing_categories": list(missing)},
        )


class MarketShiftConfigurationError(DomainError):
    def __init__(self, message: str = "The Market Shift scoring configuration is invalid.") -> None:
        super().__init__("MARKET_SHIFT_CONFIGURATION_INVALID", message, status_code=500)


class MarketShiftNotFoundError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "MARKET_SHIFT_NOT_FOUND",
            "The requested Market Shift calculation was not found.",
            status_code=404,
        )


class MarketShiftPersistenceError(DomainError):
    def __init__(self) -> None:
        super().__init__(
            "MARKET_SHIFT_PERSISTENCE_FAILED",
            "The Market Shift calculation could not be stored safely.",
            status_code=503,
            retryable=True,
        )
