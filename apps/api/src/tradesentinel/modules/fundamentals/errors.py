from tradesentinel.platform.errors import DomainError


class FundamentalDataError(DomainError):
    def __init__(self, reason: str) -> None:
        super().__init__(
            "FUNDAMENTAL_DATA_INVALID",
            "The normalized financial data cannot be used for fundamental analysis.",
            details={"reason": reason},
        )


class FundamentalPeersUnavailableError(DomainError):
    def __init__(self, reason: str) -> None:
        super().__init__(
            "FUNDAMENTAL_PEERS_UNAVAILABLE",
            "A comparable peer set could not be constructed.",
            details={"reason": reason},
            status_code=422,
        )


class FundamentalCalculationError(DomainError):
    def __init__(self, section: str, reason: str) -> None:
        super().__init__(
            "FUNDAMENTAL_CALCULATION_FAILED",
            "The fundamental calculation could not be completed.",
            details={"section": section, "reason": reason},
            status_code=422,
        )
