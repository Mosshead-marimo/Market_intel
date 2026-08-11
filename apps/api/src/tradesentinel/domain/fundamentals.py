from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from tradesentinel.domain.instruments import (
    InstrumentCatalogOutput,
    InstrumentRef,
    InstrumentResolveBatchOutput,
)
from tradesentinel.domain.market_data import CacheMetadata, StockQuoteOutput
from tradesentinel.providers.contracts import (
    CompanyProfile,
    FinancialPeriodType,
    FinancialStatement,
    FundamentalFact,
    ProviderMetadata,
)


class FundamentalContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class FundamentalStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    EMPTY = "empty"


class FundamentalConcept(StrEnum):
    REVENUE = "revenue"
    COST_OF_REVENUE = "cost_of_revenue"
    GROSS_PROFIT = "gross_profit"
    OPERATING_INCOME = "operating_income"
    EBIT = "ebit"
    EBITDA = "ebitda"
    NET_INCOME = "net_income"
    DILUTED_EPS = "diluted_eps"
    OPERATING_CASH_FLOW = "operating_cash_flow"
    INVESTING_CASH_FLOW = "investing_cash_flow"
    FINANCING_CASH_FLOW = "financing_cash_flow"
    CAPITAL_EXPENDITURE = "capital_expenditure"
    FREE_CASH_FLOW = "free_cash_flow"
    TOTAL_ASSETS = "total_assets"
    CURRENT_LIABILITIES = "current_liabilities"
    TOTAL_EQUITY = "total_equity"
    TOTAL_DEBT = "total_debt"
    CASH_AND_EQUIVALENTS = "cash_and_equivalents"
    INTEREST_EXPENSE = "interest_expense"
    DILUTED_SHARES = "diluted_shares"
    MARKET_CAP = "market_cap"
    ENTERPRISE_VALUE = "enterprise_value"
    PE_RATIO = "pe_ratio"
    PS_RATIO = "ps_ratio"
    PB_RATIO = "pb_ratio"
    EV_EBITDA = "ev_ebitda"
    EARNINGS_YIELD = "earnings_yield"
    FCF_YIELD = "fcf_yield"
    GROSS_MARGIN = "gross_margin"
    OPERATING_MARGIN = "operating_margin"
    NET_MARGIN = "net_margin"
    FCF_MARGIN = "fcf_margin"
    NET_DEBT = "net_debt"
    DEBT_TO_EQUITY = "debt_to_equity"
    DEBT_TO_EBITDA = "debt_to_ebitda"
    INTEREST_COVERAGE = "interest_coverage"
    ROE = "roe"
    ROCE = "roce"


class FundamentalAnalysisRequest(FundamentalContract):
    query: str = Field(min_length=1, max_length=200)
    exchange: str | None = Field(default=None, min_length=1, max_length=20)
    as_of: datetime = Field(default_factory=lambda: datetime.now(UTC))
    annual_periods: int = Field(default=5, ge=2, le=20)
    quarterly_periods: int = Field(default=8, ge=4, le=40)
    peers: tuple[str, ...] = Field(default=(), max_length=9)

    @field_validator("peers", mode="before")
    @classmethod
    def parse_peers(cls, value: object) -> object:
        if value is None or value == "":
            return ()
        if isinstance(value, str):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        return value

    @model_validator(mode="after")
    def validate_peers(self) -> FundamentalAnalysisRequest:
        normalized = [peer.casefold() for peer in self.peers]
        if len(normalized) != len(set(normalized)):
            raise ValueError("peer queries must be unique")
        return self


class FundamentalDataInput(FundamentalContract):
    instrument: InstrumentRef
    as_of: datetime = Field(default_factory=lambda: datetime.now(UTC))
    annual_periods: int = Field(default=5, ge=2, le=20)
    quarterly_periods: int = Field(default=8, ge=4, le=40)


class FundamentalCacheMetadata(FundamentalContract):
    profile: CacheMetadata
    statements: CacheMetadata
    facts: CacheMetadata


class FundamentalDataset(FundamentalContract):
    instrument: InstrumentRef
    as_of: datetime
    profile: CompanyProfile
    statements: tuple[FinancialStatement, ...]
    facts: tuple[FundamentalFact, ...]
    cache: FundamentalCacheMetadata
    ignored_concepts: tuple[str, ...] = ()


class FundamentalBatchDataInput(FundamentalContract):
    instruments: tuple[InstrumentRef, ...] = Field(min_length=1, max_length=10)
    as_of: datetime = Field(default_factory=lambda: datetime.now(UTC))
    annual_periods: int = Field(default=5, ge=2, le=20)
    quarterly_periods: int = Field(default=8, ge=4, le=40)


class FundamentalBatchDataset(FundamentalContract):
    datasets: tuple[FundamentalDataset, ...]


class FundamentalDatasetInput(FundamentalContract):
    dataset: FundamentalDataset


class FundamentalMetricPoint(FundamentalContract):
    period_type: FinancialPeriodType
    period_start: datetime | None = None
    period_end: datetime
    filed_at: datetime | None = None
    value: Decimal | None
    unit: str
    currency: str | None = None
    provider: ProviderMetadata


class FundamentalMetric(FundamentalContract):
    concept: str
    label: str
    unit: str
    latest: Decimal | None = None
    annual: tuple[FundamentalMetricPoint, ...] = ()
    quarterly: tuple[FundamentalMetricPoint, ...] = ()


class FundamentalSectionOutput(FundamentalContract):
    instrument: InstrumentRef
    section: Literal["revenue", "profit", "cash_flow", "debt", "margins", "roe", "roce"]
    status: FundamentalStatus
    as_of: datetime
    metrics: tuple[FundamentalMetric, ...]
    warnings: tuple[str, ...] = ()
    data_cutoff: datetime | None = None


class GrowthPoint(FundamentalContract):
    period_type: FinancialPeriodType
    period_end: datetime
    comparison: Literal["yoy", "qoq"]
    absolute_change: Decimal | None
    percent_change: Decimal | None


class GrowthMetric(FundamentalContract):
    concept: str
    annual_yoy: tuple[GrowthPoint, ...] = ()
    quarterly_yoy: tuple[GrowthPoint, ...] = ()
    quarterly_qoq: tuple[GrowthPoint, ...] = ()
    annual_cagr: Decimal | None = None


class FundamentalGrowthOutput(FundamentalContract):
    instrument: InstrumentRef
    status: FundamentalStatus
    as_of: datetime
    metrics: tuple[GrowthMetric, ...]
    warnings: tuple[str, ...] = ()
    data_cutoff: datetime | None = None


class ValuationMetric(FundamentalContract):
    concept: str
    calculated: Decimal | None = None
    reported: Decimal | None = None
    historical_reported: tuple[FundamentalMetricPoint, ...] = ()


class FundamentalValuationInput(FundamentalContract):
    dataset: FundamentalDataset
    quotes: tuple[StockQuoteOutput, ...] = ()


class FundamentalValuationOutput(FundamentalContract):
    instrument: InstrumentRef
    status: FundamentalStatus
    as_of: datetime
    currency: str | None = None
    metrics: tuple[ValuationMetric, ...]
    warnings: tuple[str, ...] = ()
    data_cutoff: datetime | None = None


class FundamentalSnapshotInput(FundamentalValuationInput):
    """Complete normalized input for an aggregate snapshot."""


class FundamentalSnapshot(FundamentalContract):
    instrument: InstrumentRef
    status: FundamentalStatus
    as_of: datetime
    data_cutoff: datetime | None = None
    calculation_version: Literal["fundamentals-v1"] = "fundamentals-v1"
    profile: CompanyProfile
    revenue: FundamentalSectionOutput
    profit: FundamentalSectionOutput
    cash_flow: FundamentalSectionOutput
    debt: FundamentalSectionOutput
    margins: FundamentalSectionOutput
    roe: FundamentalSectionOutput
    roce: FundamentalSectionOutput
    valuation: FundamentalValuationOutput
    growth: FundamentalGrowthOutput
    warnings: tuple[str, ...] = ()


class FundamentalPeerSelectionInput(FundamentalContract):
    target: FundamentalDataset
    explicit: InstrumentResolveBatchOutput
    catalog: InstrumentCatalogOutput
    maximum_peers: int = Field(default=5, ge=1, le=9)


class FundamentalPeerSelectionOutput(FundamentalContract):
    target: InstrumentRef
    peers: tuple[InstrumentRef, ...]
    instruments: tuple[InstrumentRef, ...]
    mode: Literal["explicit", "automatic"]
    warnings: tuple[str, ...] = ()


class FundamentalPeerComparisonInput(FundamentalContract):
    target: FundamentalDataset
    peers: tuple[FundamentalDataset, ...] = Field(min_length=1, max_length=9)
    quotes: tuple[StockQuoteOutput, ...] = ()


class PeerMetricValue(FundamentalContract):
    instrument: InstrumentRef
    value: Decimal | None
    percentile: Decimal | None = Field(default=None, ge=0, le=1)


class PeerMetricComparison(FundamentalContract):
    concept: str
    median: Decimal | None
    values: tuple[PeerMetricValue, ...]


class FundamentalPeerComparisonOutput(FundamentalContract):
    target: InstrumentRef
    peers: tuple[InstrumentRef, ...]
    status: FundamentalStatus
    as_of: datetime
    comparisons: tuple[PeerMetricComparison, ...]
    warnings: tuple[str, ...] = ()
