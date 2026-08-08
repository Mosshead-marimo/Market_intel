from __future__ import annotations

from tradesentinel.platform.errors import DomainError


class MarketDataError(DomainError):
    def __init__(self, code: str, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(code, message, details=details)


class MarketDataIntegrityError(MarketDataError):
    def __init__(self, reason: str) -> None:
        super().__init__(
            "MARKET_DATA_INVALID",
            "The market-data provider returned inconsistent normalized data.",
            {"reason": reason},
        )


class InsufficientHistoryError(MarketDataError):
    def __init__(self, observations: int) -> None:
        super().__init__(
            "INSUFFICIENT_HISTORY",
            "At least two positive adjusted observations are required.",
            {"observations": observations},
        )


class InsufficientOverlapError(MarketDataError):
    def __init__(self, observations: int) -> None:
        super().__init__(
            "INSUFFICIENT_BENCHMARK_OVERLAP",
            "The instrument and benchmark do not have enough overlapping observations.",
            {"observations": observations},
        )


class CurrencyMismatchError(MarketDataError):
    def __init__(self, currencies: set[str]) -> None:
        super().__init__(
            "MARKET_DATA_CURRENCY_MISMATCH",
            "Compared market series must use the same currency.",
            {"currencies": sorted(currencies)},
        )
