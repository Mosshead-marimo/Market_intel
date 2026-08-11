from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from tradesentinel.platform.config import Settings
from tradesentinel.providers.contracts import (
    CompanyProfile,
    CompanyProfileRequest,
    FinancialLineItem,
    FinancialPeriodType,
    FinancialStatement,
    FinancialStatementsRequest,
    FundamentalFact,
    FundamentalFactsRequest,
    ProviderContext,
    ProviderMetadata,
)
from tradesentinel.providers.interfaces import FundamentalsProvider

from support.fake_market_provider import metadata


def fundamental_metadata(source: str, observed: datetime) -> ProviderMetadata:
    return metadata(source, observed).model_copy(update={"provider": "test-fundamentals"})


def _classification(symbol: str) -> tuple[str, str]:
    return {
        "TCS": ("Technology", "IT Services"),
        "INFY": ("Technology", "IT Services"),
        "MSFT": ("Technology", "Software"),
        "AAPL": ("Technology", "Hardware"),
        "GOOGL": ("Technology", "Internet Services"),
        "AMZN": ("Consumer", "Retail"),
        "RELIANCE": ("Energy", "Energy Conglomerate"),
        "HDFCBANK": ("Financials", "Banking"),
    }.get(symbol, ("Diversified", "General"))


class DeterministicFundamentalsProvider(FundamentalsProvider):
    profile_calls = 0
    statement_calls = 0
    fact_calls = 0

    async def get_company_profile(
        self, context: ProviderContext, request: CompanyProfileRequest
    ) -> CompanyProfile:
        del context
        type(self).profile_calls += 1
        observed = datetime(2026, 1, 1, tzinfo=UTC)
        sector, industry = _classification(request.instrument.symbol)
        currency = "USD" if request.instrument.exchange in {"NASDAQ", "NYSE"} else "INR"
        return CompanyProfile(
            instrument=request.instrument,
            legal_name=f"{request.instrument.symbol} Holdings Limited",
            sector=sector,
            industry=industry,
            reporting_currency=currency,
            metadata=fundamental_metadata("profile", observed),
        )

    async def get_financial_statements(
        self, context: ProviderContext, request: FinancialStatementsRequest
    ) -> tuple[FinancialStatement, ...]:
        del context
        type(self).statement_calls += 1
        currency = "USD" if request.instrument.exchange in {"NASDAQ", "NYSE"} else "INR"
        statements: list[FinancialStatement] = []
        annual_start = 2026 - request.annual_periods
        for offset, year in enumerate(range(annual_start, 2026)):
            revenue = Decimal(1000 + offset * 100)
            statements.extend(
                self._period_statements(
                    request,
                    FinancialPeriodType.ANNUAL,
                    datetime(year, 1, 1, tzinfo=UTC),
                    datetime(year, 12, 31, tzinfo=UTC),
                    year,
                    None,
                    revenue,
                    currency,
                    Decimal(1000 + offset * 50),
                )
            )
        quarters = []
        for year in (2024, 2025):
            for quarter, month in enumerate((3, 6, 9, 12), start=1):
                quarters.append((year, quarter, month))
        quarters = quarters[-request.quarterly_periods :]
        for offset, (year, quarter, month) in enumerate(quarters):
            start_month = month - 2
            statements.extend(
                self._period_statements(
                    request,
                    FinancialPeriodType.QUARTERLY,
                    datetime(year, start_month, 1, tzinfo=UTC),
                    datetime(year, month, 28, tzinfo=UTC),
                    year,
                    quarter,
                    Decimal(250 + offset * 10),
                    currency,
                    Decimal(1200 + offset * 10),
                )
            )
        return tuple(statements)

    @staticmethod
    def _period_statements(
        request: FinancialStatementsRequest,
        period_type: FinancialPeriodType,
        start: datetime,
        end: datetime,
        fiscal_year: int,
        fiscal_quarter: int | None,
        revenue: Decimal,
        currency: str,
        equity: Decimal,
    ) -> tuple[FinancialStatement, ...]:
        meta = fundamental_metadata(f"statement-{period_type.value}-{end.date()}", end)
        common = {
            "instrument": request.instrument,
            "period_type": period_type,
            "period_start": start,
            "period_end": end,
            "filed_at": end,
            "fiscal_year": fiscal_year,
            "fiscal_quarter": fiscal_quarter,
            "currency": currency,
            "metadata": meta,
        }

        def money(concept: str, value: Decimal) -> FinancialLineItem:
            return FinancialLineItem(concept=concept, value=value, unit="currency")

        income = FinancialStatement(
            statement_type="income",
            items=(
                money("revenue", revenue),
                money("cost_of_revenue", revenue * Decimal("0.6")),
                money("gross_profit", revenue * Decimal("0.4")),
                money("operating_income", revenue * Decimal("0.2")),
                money("ebit", revenue * Decimal("0.18")),
                money("ebitda", revenue * Decimal("0.22")),
                money("net_income", revenue * Decimal("0.15")),
                FinancialLineItem(
                    concept="diluted_eps",
                    value=revenue * Decimal("0.0015"),
                    unit="currency_per_share",
                ),
                money("interest_expense", revenue * Decimal("0.02")),
            ),
            **common,
        )
        cash_flow = FinancialStatement(
            statement_type="cash_flow",
            items=(
                money("operating_cash_flow", revenue * Decimal("0.2")),
                money("investing_cash_flow", -revenue * Decimal("0.08")),
                money("financing_cash_flow", -revenue * Decimal("0.04")),
                money("capital_expenditure", revenue * Decimal("0.05")),
            ),
            **common,
        )
        balance = FinancialStatement(
            statement_type="balance_sheet",
            items=(
                money("total_assets", equity + Decimal(800)),
                money("current_liabilities", Decimal(400)),
                money("total_equity", equity),
                money("total_debt", Decimal(300)),
                money("cash_and_equivalents", Decimal(100)),
                FinancialLineItem(concept="diluted_shares", value=Decimal(100), unit="shares"),
            ),
            **common,
        )
        return income, cash_flow, balance

    async def get_fundamental_facts(
        self, context: ProviderContext, request: FundamentalFactsRequest
    ) -> tuple[FundamentalFact, ...]:
        del context
        type(self).fact_calls += 1
        output = []
        for year, pe in ((2023, "18"), (2024, "20"), (2025, "22")):
            observed = datetime(year, 12, 31, tzinfo=UTC)
            for concept, value in (
                ("pe_ratio", Decimal(pe)),
                ("ps_ratio", Decimal("3")),
                ("pb_ratio", Decimal("4")),
                ("ev_ebitda", Decimal("12")),
            ):
                output.append(
                    FundamentalFact(
                        instrument=request.instrument,
                        concept=concept,
                        value=value,
                        unit="ratio",
                        period_end=observed,
                        metadata=fundamental_metadata(f"fact-{concept}-{year}", observed),
                    )
                )
        return tuple(output)


def fundamentals_test_settings() -> Settings:
    tests_root = Path(__file__).parents[1]
    api_root = tests_root.parent
    return Settings(
        environment="test",
        persistence_backend="memory",
        event_backend="memory",
        cache_backend="memory",
        fundamentals_providers=("test-fundamentals",),
        market_data_providers=("technical-market",),
        module_roots=(
            api_root / "src" / "tradesentinel" / "modules",
            tests_root / "fixtures" / "fundamentals_provider",
            tests_root / "fixtures" / "technical_provider",
        ),
    )
