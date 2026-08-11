from tradesentinel.platform.errors import DomainError


class TechnicalDataError(DomainError):
    def __init__(self, reason: str) -> None:
        super().__init__(
            "TECHNICAL_DATA_INVALID",
            "The normalized history cannot be used for technical calculations.",
            details={"reason": reason},
        )


class TechnicalInsufficientHistoryError(DomainError):
    def __init__(self, indicator: str, required: int, observed: int) -> None:
        super().__init__(
            "TECHNICAL_INSUFFICIENT_HISTORY",
            "The indicator does not have enough observations for its warm-up period.",
            details={"indicator": indicator, "required": required, "observed": observed},
        )
