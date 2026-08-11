from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from tradesentinel.domain.market_data import MarketInterval


class StockOverviewContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class StockOverviewRequest(StockOverviewContract):
    query: str = Field(min_length=1, max_length=200)
    exchange: str | None = Field(default=None, min_length=1, max_length=20)
    as_of: datetime = Field(default_factory=lambda: datetime.now(UTC))
    interval: MarketInterval = MarketInterval.DAILY
    research_limit: int | None = Field(default=None, ge=1, le=100)
    sentiment_window_days: int = Field(default=7, ge=1, le=30)
    sentiment_limit: int = Field(default=100, ge=1, le=500)
    annual_periods: int = Field(default=5, ge=2, le=20)
    quarterly_periods: int = Field(default=8, ge=4, le=40)

    @model_validator(mode="after")
    def validate_as_of(self) -> StockOverviewRequest:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("as_of must include a timezone")
        return self


class StockOverviewWindowInput(StockOverviewContract):
    as_of: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_as_of(self) -> StockOverviewWindowInput:
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("as_of must include a timezone")
        return self


class StockOverviewWindow(StockOverviewContract):
    start: datetime
    end: datetime
    years: int = 5
