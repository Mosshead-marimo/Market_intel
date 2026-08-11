from __future__ import annotations

from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class InstrumentContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AssetType(StrEnum):
    EQUITY = "equity"
    ETF = "etf"
    INDEX = "index"
    FUND = "fund"
    CURRENCY = "currency"
    COMMODITY = "commodity"
    CRYPTO = "crypto"
    OTHER = "other"


class InstrumentRef(InstrumentContract):
    instrument_id: UUID
    symbol: str = Field(min_length=1)
    name: str = Field(min_length=1)
    exchange: str = Field(min_length=1)
    asset_type: AssetType
    currency: str = Field(min_length=1)
    aliases: tuple[str, ...] = ()


class InstrumentMatch(InstrumentContract):
    instrument: InstrumentRef
    confidence: float = Field(ge=0, le=1)
    matched_on: Literal["ticker", "name", "alias"]
    matched_value: str


class InstrumentSearchInput(InstrumentContract):
    query: str = Field(min_length=1, max_length=200)
    exchange: str | None = Field(default=None, min_length=1, max_length=20)
    asset_type: AssetType | None = None
    limit: int = Field(default=20, ge=1, le=50)


class InstrumentAutocompleteInput(InstrumentContract):
    query: str = Field(min_length=1, max_length=200)
    exchange: str | None = Field(default=None, min_length=1, max_length=20)
    asset_type: AssetType | None = None
    limit: int = Field(default=10, ge=1, le=20)


class InstrumentResolveInput(InstrumentContract):
    query: str = Field(min_length=1, max_length=200)
    exchange: str | None = Field(default=None, min_length=1, max_length=20)
    asset_type: AssetType | None = None


class InstrumentSearchOutput(InstrumentContract):
    query: str
    matches: tuple[InstrumentMatch, ...]


class InstrumentAutocompleteOutput(InstrumentContract):
    query: str
    matches: tuple[InstrumentMatch, ...]


class InstrumentResolveOutput(InstrumentContract):
    query: str
    status: Literal["resolved", "ambiguous", "not_found"]
    match: InstrumentMatch | None = None
    candidates: tuple[InstrumentMatch, ...] = ()

    @model_validator(mode="after")
    def validate_status_shape(self) -> InstrumentResolveOutput:
        if self.status == "resolved" and self.match is None:
            raise ValueError("resolved output requires a match")
        if self.status != "resolved" and self.match is not None:
            raise ValueError("only resolved output may contain a match")
        if self.status == "ambiguous" and len(self.candidates) < 2:
            raise ValueError("ambiguous output requires at least two candidates")
        return self


class InstrumentBatchQuery(InstrumentContract):
    query: str = Field(min_length=1, max_length=200)
    exchange: str | None = Field(default=None, min_length=1, max_length=20)


class InstrumentResolveBatchInput(InstrumentContract):
    queries: tuple[InstrumentBatchQuery, ...] = Field(default=(), max_length=9)

    @field_validator("queries", mode="before")
    @classmethod
    def parse_queries(cls, value: object) -> object:
        if value is None or value == "":
            return ()
        if isinstance(value, str):
            parsed = []
            for raw in value.split(","):
                token = raw.strip()
                if not token:
                    continue
                query, separator, exchange = token.rpartition("@")
                parsed.append(
                    {"query": query, "exchange": exchange}
                    if separator and query and exchange
                    else {"query": token}
                )
            return tuple(parsed)
        return value


class InstrumentResolveBatchOutput(InstrumentContract):
    results: tuple[InstrumentResolveOutput, ...]
    instruments: tuple[InstrumentRef, ...]
    unresolved_queries: tuple[str, ...] = ()


class InstrumentCatalogInput(InstrumentContract):
    active_only: Literal[True] = True


class InstrumentCatalogOutput(InstrumentContract):
    instruments: tuple[InstrumentRef, ...]
