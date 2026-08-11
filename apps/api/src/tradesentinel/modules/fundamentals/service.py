from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from statistics import median
from typing import TypeVar

import structlog
from pydantic import BaseModel, TypeAdapter, ValidationError

from tradesentinel.domain.fundamentals import (
    FundamentalBatchDataInput,
    FundamentalBatchDataset,
    FundamentalCacheMetadata,
    FundamentalConcept,
    FundamentalDataInput,
    FundamentalDataset,
    FundamentalGrowthOutput,
    FundamentalMetric,
    FundamentalMetricPoint,
    FundamentalPeerComparisonInput,
    FundamentalPeerComparisonOutput,
    FundamentalPeerSelectionInput,
    FundamentalPeerSelectionOutput,
    FundamentalSectionOutput,
    FundamentalSnapshot,
    FundamentalSnapshotInput,
    FundamentalStatus,
    FundamentalValuationInput,
    FundamentalValuationOutput,
    GrowthMetric,
    GrowthPoint,
    PeerMetricComparison,
    PeerMetricValue,
    ValuationMetric,
)
from tradesentinel.domain.instruments import InstrumentRef
from tradesentinel.domain.market_data import CacheDisposition, CacheMetadata
from tradesentinel.modules.fundamentals.errors import (
    FundamentalDataError,
    FundamentalPeersUnavailableError,
)
from tradesentinel.platform.cache import CacheStore
from tradesentinel.platform.config import Settings
from tradesentinel.platform.contracts import ExecutionContext
from tradesentinel.providers.contracts import (
    CompanyProfile,
    CompanyProfileRequest,
    FinancialPeriodType,
    FinancialStatement,
    FinancialStatementsRequest,
    FundamentalFact,
    FundamentalFactsRequest,
    InstrumentReference,
    ProviderContext,
)
from tradesentinel.providers.interfaces import FundamentalsProvider

OutputT = TypeVar("OutputT")
ZERO = Decimal(0)
ONE = Decimal(1)
HUNDRED = Decimal(100)

LABELS = {concept.value: concept.value.replace("_", " ").title() for concept in FundamentalConcept}
FLOW_CONCEPTS = {
    FundamentalConcept.REVENUE,
    FundamentalConcept.COST_OF_REVENUE,
    FundamentalConcept.GROSS_PROFIT,
    FundamentalConcept.OPERATING_INCOME,
    FundamentalConcept.EBIT,
    FundamentalConcept.EBITDA,
    FundamentalConcept.NET_INCOME,
    FundamentalConcept.DILUTED_EPS,
    FundamentalConcept.OPERATING_CASH_FLOW,
    FundamentalConcept.INVESTING_CASH_FLOW,
    FundamentalConcept.FINANCING_CASH_FLOW,
    FundamentalConcept.CAPITAL_EXPENDITURE,
}
KNOWN = {concept.value for concept in FundamentalConcept}


class FundamentalAnalysisService:
    def __init__(
        self,
        provider: FundamentalsProvider,
        cache: CacheStore,
        settings: Settings,
    ) -> None:
        self._provider = provider
        self._cache = cache
        self._settings = settings
        chain = ",".join(settings.fundamentals_providers)
        self._chain_fingerprint = hashlib.sha256(chain.encode()).hexdigest()[:16]

    async def collect(
        self, context: ExecutionContext, request: FundamentalDataInput
    ) -> FundamentalDataset:
        reference = self._reference(request.instrument)
        profile_request = CompanyProfileRequest(instrument=reference)
        statements_request = FinancialStatementsRequest(
            instrument=reference,
            statement_types=("income", "balance_sheet", "cash_flow"),
            annual_periods=request.annual_periods,
            quarterly_periods=request.quarterly_periods,
        )
        facts_request = FundamentalFactsRequest(instrument=reference, as_of=request.as_of)
        profile_result, statements_result, facts_result = await asyncio.gather(
            self._cached(
                "profile",
                profile_request,
                TypeAdapter(CompanyProfile),
                self._settings.fundamentals_profile_cache_ttl_seconds,
                lambda: self._provider.get_company_profile(self._context(context), profile_request),
            ),
            self._cached(
                "statements",
                statements_request,
                TypeAdapter(tuple[FinancialStatement, ...]),
                self._settings.fundamentals_data_cache_ttl_seconds,
                lambda: self._provider.get_financial_statements(
                    self._context(context), statements_request
                ),
            ),
            self._cached(
                "facts",
                facts_request,
                TypeAdapter(tuple[FundamentalFact, ...]),
                self._settings.fundamentals_data_cache_ttl_seconds,
                lambda: self._provider.get_fundamental_facts(self._context(context), facts_request),
            ),
        )
        profile, profile_cache = profile_result
        statements, statements_cache = statements_result
        facts, facts_cache = facts_result
        self._validate_reference(request.instrument, profile.instrument)
        for statement in statements:
            self._validate_reference(request.instrument, statement.instrument)
        for fact in facts:
            self._validate_reference(request.instrument, fact.instrument)
        eligible = tuple(
            statement
            for statement in statements
            if statement.period_end <= request.as_of
            and (statement.filed_at is None or statement.filed_at <= request.as_of)
        )
        self._validate_statement_order(eligible)
        ordered = tuple(
            sorted(
                eligible,
                key=lambda item: (
                    item.period_type.value,
                    item.period_end,
                    item.statement_type,
                ),
            )
        )
        self._validate_statements(ordered)
        ignored = sorted(
            {
                item.concept
                for statement in ordered
                for item in statement.items
                if item.concept not in KNOWN
            }
            | {fact.concept for fact in facts if fact.concept not in KNOWN}
        )
        return FundamentalDataset(
            instrument=request.instrument,
            as_of=request.as_of,
            profile=profile,
            statements=ordered,
            facts=tuple(
                sorted(
                    (
                        fact
                        for fact in facts
                        if fact.period_end is None or fact.period_end <= request.as_of
                    ),
                    key=lambda item: (
                        item.concept,
                        item.period_end or datetime.min.replace(tzinfo=UTC),
                    ),
                )
            ),
            cache=FundamentalCacheMetadata(
                profile=profile_cache, statements=statements_cache, facts=facts_cache
            ),
            ignored_concepts=tuple(ignored),
        )

    async def collect_batch(
        self, context: ExecutionContext, request: FundamentalBatchDataInput
    ) -> FundamentalBatchDataset:
        datasets = await asyncio.gather(
            *(
                self.collect(
                    context,
                    FundamentalDataInput(
                        instrument=instrument,
                        as_of=request.as_of,
                        annual_periods=request.annual_periods,
                        quarterly_periods=request.quarterly_periods,
                    ),
                )
                for instrument in request.instruments
            )
        )
        return FundamentalBatchDataset(datasets=tuple(datasets))

    def revenue(self, dataset: FundamentalDataset) -> FundamentalSectionOutput:
        return self._raw_section(dataset, "revenue", (FundamentalConcept.REVENUE,))

    def profit(self, dataset: FundamentalDataset) -> FundamentalSectionOutput:
        return self._raw_section(
            dataset,
            "profit",
            (
                FundamentalConcept.GROSS_PROFIT,
                FundamentalConcept.OPERATING_INCOME,
                FundamentalConcept.EBIT,
                FundamentalConcept.EBITDA,
                FundamentalConcept.NET_INCOME,
                FundamentalConcept.DILUTED_EPS,
            ),
        )

    def cash_flow(self, dataset: FundamentalDataset) -> FundamentalSectionOutput:
        metrics = [
            self._metric(dataset, concept)
            for concept in (
                FundamentalConcept.OPERATING_CASH_FLOW,
                FundamentalConcept.INVESTING_CASH_FLOW,
                FundamentalConcept.FINANCING_CASH_FLOW,
                FundamentalConcept.CAPITAL_EXPENDITURE,
            )
        ]
        metrics.append(
            self._derived_metric(
                dataset,
                FundamentalConcept.FREE_CASH_FLOW,
                (FundamentalConcept.OPERATING_CASH_FLOW, FundamentalConcept.CAPITAL_EXPENDITURE),
                lambda values: values[0] - values[1] if values[1] >= 0 else None,
                unit="currency",
            )
        )
        return self._section(dataset, "cash_flow", tuple(metrics))

    def debt(self, dataset: FundamentalDataset) -> FundamentalSectionOutput:
        metrics = [
            self._metric(dataset, concept)
            for concept in (
                FundamentalConcept.TOTAL_DEBT,
                FundamentalConcept.CASH_AND_EQUIVALENTS,
                FundamentalConcept.TOTAL_EQUITY,
            )
        ]
        metrics.extend(
            (
                self._derived_metric(
                    dataset,
                    FundamentalConcept.NET_DEBT,
                    (FundamentalConcept.TOTAL_DEBT, FundamentalConcept.CASH_AND_EQUIVALENTS),
                    lambda values: values[0] - values[1],
                    unit="currency",
                ),
                self._derived_metric(
                    dataset,
                    FundamentalConcept.DEBT_TO_EQUITY,
                    (FundamentalConcept.TOTAL_DEBT, FundamentalConcept.TOTAL_EQUITY),
                    lambda values: self._safe_div(values[0], values[1]),
                    unit="ratio",
                ),
                self._derived_metric(
                    dataset,
                    FundamentalConcept.DEBT_TO_EBITDA,
                    (FundamentalConcept.TOTAL_DEBT, FundamentalConcept.EBITDA),
                    lambda values: self._safe_div(values[0], values[1]),
                    unit="ratio",
                ),
                self._derived_metric(
                    dataset,
                    FundamentalConcept.INTEREST_COVERAGE,
                    (FundamentalConcept.EBIT, FundamentalConcept.INTEREST_EXPENSE),
                    lambda values: self._safe_div(values[0], abs(values[1])),
                    unit="ratio",
                ),
            )
        )
        return self._section(dataset, "debt", tuple(metrics))

    def margins(self, dataset: FundamentalDataset) -> FundamentalSectionOutput:
        definitions = (
            (FundamentalConcept.GROSS_MARGIN, FundamentalConcept.GROSS_PROFIT),
            (FundamentalConcept.OPERATING_MARGIN, FundamentalConcept.OPERATING_INCOME),
            (FundamentalConcept.NET_MARGIN, FundamentalConcept.NET_INCOME),
        )
        metrics = [
            self._derived_metric(
                dataset,
                output,
                (numerator, FundamentalConcept.REVENUE),
                lambda values: self._percent(values[0], values[1]),
                unit="percent",
            )
            for output, numerator in definitions
        ]
        free_cash_flow = self.cash_flow(dataset).metrics[-1]
        metrics.append(
            self._combine_metrics(
                dataset,
                FundamentalConcept.FCF_MARGIN,
                free_cash_flow,
                self._metric(dataset, FundamentalConcept.REVENUE),
                lambda left, right: self._percent(left, right),
                "percent",
            )
        )
        return self._section(dataset, "margins", tuple(metrics))

    def roe(self, dataset: FundamentalDataset) -> FundamentalSectionOutput:
        metric = self._return_metric(
            dataset,
            FundamentalConcept.ROE,
            FundamentalConcept.NET_INCOME,
            (FundamentalConcept.TOTAL_EQUITY,),
        )
        return self._section(dataset, "roe", (metric,))

    def roce(self, dataset: FundamentalDataset) -> FundamentalSectionOutput:
        metric = self._return_metric(
            dataset,
            FundamentalConcept.ROCE,
            FundamentalConcept.EBIT,
            (
                FundamentalConcept.TOTAL_EQUITY,
                FundamentalConcept.TOTAL_DEBT,
                FundamentalConcept.CASH_AND_EQUIVALENTS,
            ),
        )
        return self._section(dataset, "roce", (metric,))

    def growth(self, dataset: FundamentalDataset) -> FundamentalGrowthOutput:
        warnings: list[str] = []
        metrics = tuple(
            self._growth_metric(dataset, concept, warnings)
            for concept in (
                FundamentalConcept.REVENUE,
                FundamentalConcept.NET_INCOME,
                FundamentalConcept.DILUTED_EPS,
                FundamentalConcept.FREE_CASH_FLOW,
            )
        )
        available = sum(
            bool(item.annual_yoy or item.quarterly_yoy or item.quarterly_qoq) for item in metrics
        )
        status = self._status(available, len(metrics))
        return FundamentalGrowthOutput(
            instrument=dataset.instrument,
            status=status,
            as_of=dataset.as_of,
            metrics=metrics,
            warnings=tuple(warnings),
            data_cutoff=self._data_cutoff(dataset),
        )

    def valuation(self, request: FundamentalValuationInput) -> FundamentalValuationOutput:
        dataset = request.dataset
        quote = next(
            (
                item
                for item in request.quotes
                if item.instrument.instrument_id == dataset.instrument.instrument_id
            ),
            None,
        )
        warnings: list[str] = []
        calculated: dict[FundamentalConcept, Decimal | None] = {
            concept: None
            for concept in (
                FundamentalConcept.MARKET_CAP,
                FundamentalConcept.ENTERPRISE_VALUE,
                FundamentalConcept.PE_RATIO,
                FundamentalConcept.PS_RATIO,
                FundamentalConcept.PB_RATIO,
                FundamentalConcept.EV_EBITDA,
                FundamentalConcept.EARNINGS_YIELD,
                FundamentalConcept.FCF_YIELD,
            )
        }
        currency = dataset.profile.reporting_currency
        if quote is None:
            warnings.append("Current market data was unavailable; calculated valuation is omitted.")
        elif currency is not None and quote.currency.casefold() != currency.casefold():
            warnings.append(
                "Quote and reporting currencies differ; calculated valuation is omitted."
            )
        else:
            shares = self._latest_value(dataset, FundamentalConcept.DILUTED_SHARES)
            revenue = self._ttm_or_annual(dataset, FundamentalConcept.REVENUE, warnings)
            income = self._ttm_or_annual(dataset, FundamentalConcept.NET_INCOME, warnings)
            ebitda = self._ttm_or_annual(dataset, FundamentalConcept.EBITDA, warnings)
            fcf = self._latest_metric_value(
                self.cash_flow(dataset), FundamentalConcept.FREE_CASH_FLOW
            )
            equity = self._latest_value(dataset, FundamentalConcept.TOTAL_EQUITY)
            debt = self._latest_value(dataset, FundamentalConcept.TOTAL_DEBT)
            cash = self._latest_value(dataset, FundamentalConcept.CASH_AND_EQUIVALENTS)
            if shares is None or shares <= 0:
                warnings.append("Diluted shares were unavailable for calculated valuation.")
            else:
                market_cap = quote.price * shares
                enterprise = (
                    market_cap + debt - cash if debt is not None and cash is not None else None
                )
                calculated[FundamentalConcept.MARKET_CAP] = market_cap
                calculated[FundamentalConcept.ENTERPRISE_VALUE] = enterprise
                calculated[FundamentalConcept.PE_RATIO] = self._safe_div(market_cap, income)
                calculated[FundamentalConcept.PS_RATIO] = self._safe_div(market_cap, revenue)
                calculated[FundamentalConcept.PB_RATIO] = self._safe_div(market_cap, equity)
                calculated[FundamentalConcept.EV_EBITDA] = self._safe_div(enterprise, ebitda)
                calculated[FundamentalConcept.EARNINGS_YIELD] = self._safe_div(income, market_cap)
                calculated[FundamentalConcept.FCF_YIELD] = self._safe_div(fcf, market_cap)
        metrics = tuple(
            ValuationMetric(
                concept=concept.value,
                calculated=calculated[concept],
                reported=self._reported_value(dataset, concept),
                historical_reported=self._reported_history(dataset, concept),
            )
            for concept in calculated
        )
        available = sum(
            item.calculated is not None or item.reported is not None for item in metrics
        )
        return FundamentalValuationOutput(
            instrument=dataset.instrument,
            status=self._status(available, len(metrics)),
            as_of=dataset.as_of,
            currency=currency or (quote.currency if quote is not None else None),
            metrics=metrics,
            warnings=tuple(dict.fromkeys(warnings)),
            data_cutoff=max(
                filter(
                    None,
                    (
                        self._data_cutoff(dataset),
                        quote.as_of if quote is not None else None,
                    ),
                ),
                default=None,
            ),
        )

    def snapshot(self, request: FundamentalSnapshotInput) -> FundamentalSnapshot:
        dataset = request.dataset
        sections = {
            "revenue": self.revenue(dataset),
            "profit": self.profit(dataset),
            "cash_flow": self.cash_flow(dataset),
            "debt": self.debt(dataset),
            "margins": self.margins(dataset),
            "roe": self.roe(dataset),
            "roce": self.roce(dataset),
        }
        growth = self.growth(dataset)
        valuation = self.valuation(
            FundamentalValuationInput(dataset=dataset, quotes=request.quotes)
        )
        statuses = [item.status for item in sections.values()] + [growth.status, valuation.status]
        status = (
            FundamentalStatus.COMPLETED
            if all(item == FundamentalStatus.COMPLETED for item in statuses)
            else FundamentalStatus.EMPTY
            if all(item == FundamentalStatus.EMPTY for item in statuses)
            else FundamentalStatus.PARTIAL
        )
        warnings = tuple(
            dict.fromkeys(
                (
                    *(warning for section in sections.values() for warning in section.warnings),
                    *growth.warnings,
                    *valuation.warnings,
                    *(
                        (f"Ignored unsupported provider concept '{concept}'.")
                        for concept in dataset.ignored_concepts
                    ),
                )
            )
        )
        return FundamentalSnapshot(
            instrument=dataset.instrument,
            status=status,
            as_of=dataset.as_of,
            data_cutoff=self._data_cutoff(dataset),
            profile=dataset.profile,
            revenue=sections["revenue"],
            profit=sections["profit"],
            cash_flow=sections["cash_flow"],
            debt=sections["debt"],
            margins=sections["margins"],
            roe=sections["roe"],
            roce=sections["roce"],
            valuation=valuation,
            growth=growth,
            warnings=warnings,
        )

    async def select_peers(
        self, context: ExecutionContext, request: FundamentalPeerSelectionInput
    ) -> FundamentalPeerSelectionOutput:
        if request.explicit.unresolved_queries:
            raise FundamentalPeersUnavailableError(
                "explicit peers contain unresolved or ambiguous instrument queries"
            )
        target = request.target.instrument
        if request.explicit.instruments:
            peers = request.explicit.instruments
            if any(item.instrument_id == target.instrument_id for item in peers):
                raise FundamentalPeersUnavailableError("the target cannot also be a peer")
            explicit_profiles = await asyncio.gather(
                *(self._profile(context, item) for item in peers)
            )
            legal_names = [profile.legal_name.casefold() for profile, _ in explicit_profiles]
            if request.target.profile.legal_name.casefold() in legal_names or len(
                legal_names
            ) != len(set(legal_names)):
                raise FundamentalPeersUnavailableError(
                    "explicit peers contain duplicate legal entities"
                )
            return FundamentalPeerSelectionOutput(
                target=target,
                peers=peers,
                instruments=(target, *peers),
                mode="explicit",
            )
        candidates = tuple(
            item
            for item in request.catalog.instruments
            if item.instrument_id != target.instrument_id
        )
        profile_results = await asyncio.gather(
            *(self._profile(context, item) for item in candidates),
            return_exceptions=True,
        )
        target_name = request.target.profile.legal_name.casefold()
        target_industry = (request.target.profile.industry or "").casefold()
        target_sector = (request.target.profile.sector or "").casefold()
        ranked: list[tuple[int, int, int, str, str, InstrumentRef]] = []
        for instrument, profile_result in zip(candidates, profile_results, strict=True):
            if isinstance(profile_result, BaseException):
                continue
            profile, _ = profile_result
            if profile.legal_name.casefold() == target_name:
                continue
            industry = (profile.industry or "").casefold()
            sector = (profile.sector or "").casefold()
            group = 0 if target_industry and industry == target_industry else 1
            if group == 1 and (not target_sector or sector != target_sector):
                continue
            ranked.append(
                (
                    group,
                    instrument.currency.casefold() != target.currency.casefold(),
                    instrument.exchange.casefold() != target.exchange.casefold(),
                    instrument.symbol.casefold(),
                    profile.legal_name.casefold(),
                    instrument,
                )
            )
        selected: list[InstrumentRef] = []
        selected_names: set[str] = set()
        for item in sorted(ranked):
            if item[-2] in selected_names:
                continue
            selected_names.add(item[-2])
            selected.append(item[-1])
            if len(selected) == request.maximum_peers:
                break
        peers = tuple(selected)
        if not peers:
            raise FundamentalPeersUnavailableError(
                "no catalog instrument shared the target industry or sector"
            )
        warning = (
            ()
            if len(peers) == request.maximum_peers
            else (f"Only {len(peers)} comparable catalog peers were available.",)
        )
        return FundamentalPeerSelectionOutput(
            target=target,
            peers=peers,
            instruments=(target, *peers),
            mode="automatic",
            warnings=warning,
        )

    def peer_comparison(
        self, request: FundamentalPeerComparisonInput
    ) -> FundamentalPeerComparisonOutput:
        datasets = (request.target, *request.peers)
        quote_by_id = {item.instrument.instrument_id: item for item in request.quotes}
        snapshots = tuple(
            self.snapshot(
                FundamentalSnapshotInput(
                    dataset=dataset,
                    quotes=(quote_by_id[dataset.instrument.instrument_id],)
                    if dataset.instrument.instrument_id in quote_by_id
                    else (),
                )
            )
            for dataset in datasets
        )
        concepts = (
            FundamentalConcept.NET_MARGIN,
            FundamentalConcept.ROE,
            FundamentalConcept.ROCE,
            FundamentalConcept.DEBT_TO_EQUITY,
            FundamentalConcept.PE_RATIO,
            FundamentalConcept.PS_RATIO,
            FundamentalConcept.PB_RATIO,
            FundamentalConcept.EV_EBITDA,
        )
        comparisons: list[PeerMetricComparison] = []
        warnings: list[str] = []
        for concept in concepts:
            raw = tuple(
                (snapshot.instrument, self._snapshot_metric(snapshot, concept))
                for snapshot in snapshots
            )
            present = sorted(value for _, value in raw if value is not None)
            middle = Decimal(str(median(present))) if present else None
            values = tuple(
                PeerMetricValue(
                    instrument=instrument,
                    value=value,
                    percentile=(
                        Decimal(sum(item <= value for item in present)) / Decimal(len(present))
                        if value is not None and present
                        else None
                    ),
                )
                for instrument, value in raw
            )
            if len(present) < 2:
                warnings.append(f"{concept.value} lacked enough peer observations.")
            comparisons.append(
                PeerMetricComparison(concept=concept.value, median=middle, values=values)
            )
        available = sum(item.median is not None for item in comparisons)
        return FundamentalPeerComparisonOutput(
            target=request.target.instrument,
            peers=tuple(item.instrument for item in request.peers),
            status=self._status(available, len(comparisons)),
            as_of=request.target.as_of,
            comparisons=tuple(comparisons),
            warnings=tuple(warnings),
        )

    def _raw_section(
        self,
        dataset: FundamentalDataset,
        section: str,
        concepts: tuple[FundamentalConcept, ...],
    ) -> FundamentalSectionOutput:
        return self._section(
            dataset, section, tuple(self._metric(dataset, item) for item in concepts)
        )

    def _section(
        self,
        dataset: FundamentalDataset,
        section: str,
        metrics: tuple[FundamentalMetric, ...],
    ) -> FundamentalSectionOutput:
        missing = [item.label for item in metrics if item.latest is None]
        warnings = tuple(f"{label} was unavailable." for label in missing)
        available = len(metrics) - len(missing)
        return FundamentalSectionOutput(
            instrument=dataset.instrument,
            section=section,
            status=self._status(available, len(metrics)),
            as_of=dataset.as_of,
            metrics=metrics,
            warnings=warnings,
            data_cutoff=self._data_cutoff(dataset),
        )

    def _metric(
        self, dataset: FundamentalDataset, concept: FundamentalConcept
    ) -> FundamentalMetric:
        points = self._points(dataset, concept)
        annual = tuple(item for item in points if item.period_type == FinancialPeriodType.ANNUAL)
        quarterly = tuple(
            item for item in points if item.period_type == FinancialPeriodType.QUARTERLY
        )
        latest_point = max(points, key=lambda item: item.period_end, default=None)
        unit = latest_point.unit if latest_point is not None else self._default_unit(concept)
        return FundamentalMetric(
            concept=concept.value,
            label=LABELS[concept.value],
            unit=unit,
            latest=latest_point.value if latest_point is not None else None,
            annual=annual,
            quarterly=quarterly,
        )

    def _points(
        self, dataset: FundamentalDataset, concept: FundamentalConcept
    ) -> tuple[FundamentalMetricPoint, ...]:
        points: list[FundamentalMetricPoint] = []
        seen: dict[tuple[FinancialPeriodType, datetime], Decimal | None] = {}
        units: set[str] = set()
        currencies: set[str] = set()
        for statement in dataset.statements:
            matches = [item for item in statement.items if item.concept == concept.value]
            if not matches:
                continue
            if len(matches) > 1:
                raise FundamentalDataError(
                    f"statement contains duplicate concept '{concept.value}'"
                )
            item = matches[0]
            key = (statement.period_type, statement.period_end)
            if key in seen:
                if seen[key] != item.value:
                    raise FundamentalDataError(
                        f"statement contains contradictory concept '{concept.value}'"
                    )
                continue
            seen[key] = item.value
            units.add(item.unit)
            if statement.currency:
                currencies.add(statement.currency.casefold())
            points.append(
                FundamentalMetricPoint(
                    period_type=statement.period_type,
                    period_start=statement.period_start,
                    period_end=statement.period_end,
                    filed_at=statement.filed_at,
                    value=item.value,
                    unit=item.unit,
                    currency=statement.currency,
                    provider=statement.metadata,
                )
            )
        if len(units) > 1:
            raise FundamentalDataError(f"concept '{concept.value}' uses inconsistent units")
        if len(currencies) > 1:
            raise FundamentalDataError(
                f"concept '{concept.value}' uses inconsistent reporting currencies"
            )
        return tuple(sorted(points, key=lambda item: (item.period_type.value, item.period_end)))

    def _derived_metric(
        self,
        dataset: FundamentalDataset,
        output: FundamentalConcept,
        inputs: tuple[FundamentalConcept, ...],
        calculation: Callable[[tuple[Decimal, ...]], Decimal | None],
        *,
        unit: str,
    ) -> FundamentalMetric:
        sources = [self._metric(dataset, concept) for concept in inputs]
        result = self._combine_many(dataset, output, tuple(sources), calculation, unit)
        return result

    def _combine_many(
        self,
        dataset: FundamentalDataset,
        output: FundamentalConcept,
        sources: tuple[FundamentalMetric, ...],
        calculation: Callable[[tuple[Decimal, ...]], Decimal | None],
        unit: str,
    ) -> FundamentalMetric:
        maps = [
            {
                (point.period_type, point.period_end): point
                for point in (*source.annual, *source.quarterly)
                if point.value is not None
            }
            for source in sources
        ]
        keys = set(maps[0]) if maps else set()
        for mapping in maps[1:]:
            keys &= set(mapping)
        points = []
        for key in sorted(keys, key=lambda item: (item[0].value, item[1])):
            source = maps[0][key]
            values = tuple(mapping[key].value for mapping in maps)
            if any(value is None for value in values):
                continue
            result = calculation(tuple(value for value in values if value is not None))
            points.append(
                FundamentalMetricPoint(
                    period_type=source.period_type,
                    period_start=source.period_start,
                    period_end=source.period_end,
                    filed_at=source.filed_at,
                    value=result,
                    unit=unit,
                    currency=source.currency if unit == "currency" else None,
                    provider=source.provider,
                )
            )
        annual = tuple(item for item in points if item.period_type == FinancialPeriodType.ANNUAL)
        quarterly = tuple(
            item for item in points if item.period_type == FinancialPeriodType.QUARTERLY
        )
        latest = max(points, key=lambda item: item.period_end, default=None)
        return FundamentalMetric(
            concept=output.value,
            label=LABELS[output.value],
            unit=unit,
            latest=latest.value if latest is not None else None,
            annual=annual,
            quarterly=quarterly,
        )

    def _combine_metrics(
        self,
        dataset: FundamentalDataset,
        output: FundamentalConcept,
        left: FundamentalMetric,
        right: FundamentalMetric,
        calculation: Callable[[Decimal, Decimal], Decimal | None],
        unit: str,
    ) -> FundamentalMetric:
        return self._combine_many(
            dataset,
            output,
            (left, right),
            lambda values: calculation(values[0], values[1]),
            unit,
        )

    def _return_metric(
        self,
        dataset: FundamentalDataset,
        output: FundamentalConcept,
        numerator: FundamentalConcept,
        denominator_parts: tuple[FundamentalConcept, ...],
    ) -> FundamentalMetric:
        numerator_metric = self._metric(dataset, numerator)
        denominator_metrics = tuple(self._metric(dataset, item) for item in denominator_parts)
        annual = self._return_points(
            numerator_metric.annual,
            tuple(metric.annual for metric in denominator_metrics),
            FinancialPeriodType.ANNUAL,
            lag=1,
            trailing_numerator=1,
        )
        quarterly = self._return_points(
            numerator_metric.quarterly,
            tuple(metric.quarterly for metric in denominator_metrics),
            FinancialPeriodType.QUARTERLY,
            lag=4,
            trailing_numerator=4,
        )
        points = (*annual, *quarterly)
        latest = points[-1].value if points else None
        return FundamentalMetric(
            concept=output.value,
            label=LABELS[output.value],
            unit="percent",
            latest=latest,
            annual=annual,
            quarterly=quarterly,
        )

    def _return_points(
        self,
        numerator_points: tuple[FundamentalMetricPoint, ...],
        denominator_series: tuple[tuple[FundamentalMetricPoint, ...], ...],
        period_type: FinancialPeriodType,
        *,
        lag: int,
        trailing_numerator: int,
    ) -> tuple[FundamentalMetricPoint, ...]:
        numerator = tuple(point for point in numerator_points if point.value is not None)
        numerator_map = {point.period_end: point for point in numerator}
        denominator_maps = tuple(
            {point.period_end: point for point in series if point.value is not None}
            for series in denominator_series
        )
        dates = sorted(set(numerator_map).intersection(*(set(item) for item in denominator_maps)))
        output: list[FundamentalMetricPoint] = []
        for index in range(lag, len(dates)):
            date = dates[index]
            prior_date = dates[index - lag]
            trailing_dates = dates[index - trailing_numerator + 1 : index + 1]
            if len(trailing_dates) != trailing_numerator:
                continue
            current_capital = self._capital(tuple(item[date].value for item in denominator_maps))
            prior_capital = self._capital(
                tuple(item[prior_date].value for item in denominator_maps)
            )
            if current_capital is None or prior_capital is None:
                continue
            numerator_value = sum(
                (
                    value
                    for item in trailing_dates
                    if (value := numerator_map[item].value) is not None
                ),
                ZERO,
            )
            average = (current_capital + prior_capital) / Decimal(2)
            source = numerator_map[date]
            output.append(
                FundamentalMetricPoint(
                    period_type=period_type,
                    period_start=numerator_map[trailing_dates[0]].period_start,
                    period_end=date,
                    filed_at=source.filed_at,
                    value=self._percent(numerator_value, average),
                    unit="percent",
                    provider=source.provider,
                )
            )
        return tuple(output)

    @staticmethod
    def _capital(values: tuple[Decimal | None, ...]) -> Decimal | None:
        if any(value is None for value in values):
            return None
        clean = tuple(value for value in values if value is not None)
        return clean[0] if len(clean) == 1 else clean[0] + clean[1] - clean[2]

    def _growth_metric(
        self,
        dataset: FundamentalDataset,
        concept: FundamentalConcept,
        warnings: list[str],
    ) -> GrowthMetric:
        metric = (
            self.cash_flow(dataset).metrics[-1]
            if concept == FundamentalConcept.FREE_CASH_FLOW
            else self._metric(dataset, concept)
        )
        annual = tuple(item for item in metric.annual if item.value is not None)
        quarterly = tuple(item for item in metric.quarterly if item.value is not None)
        annual_yoy = self._growth_points(annual, 1, "yoy", warnings, concept)
        quarterly_qoq = self._growth_points(quarterly, 1, "qoq", warnings, concept)
        quarterly_yoy = self._growth_points(quarterly, 4, "yoy", warnings, concept)
        cagr = None
        if len(annual) >= 2 and annual[0].value is not None and annual[-1].value is not None:
            first = annual[0].value
            last = annual[-1].value
            years = Decimal(len(annual) - 1)
            if first > 0 and last > 0:
                cagr = ((last / first).ln() / years).exp() - ONE
            else:
                warnings.append(f"{concept.value} CAGR requires positive endpoints.")
        return GrowthMetric(
            concept=concept.value,
            annual_yoy=annual_yoy,
            quarterly_yoy=quarterly_yoy,
            quarterly_qoq=quarterly_qoq,
            annual_cagr=cagr,
        )

    def _growth_points(
        self,
        points: tuple[FundamentalMetricPoint, ...],
        lag: int,
        comparison: str,
        warnings: list[str],
        concept: FundamentalConcept,
    ) -> tuple[GrowthPoint, ...]:
        output = []
        for index in range(lag, len(points)):
            previous = points[index - lag].value
            current = points[index].value
            if previous is None or current is None:
                continue
            percent = None
            if previous != 0 and previous * current > 0:
                percent = current / previous - ONE
            else:
                warnings.append(
                    f"{concept.value} {comparison} percentage is unavailable "
                    "across zero or sign changes."
                )
            output.append(
                GrowthPoint(
                    period_type=points[index].period_type,
                    period_end=points[index].period_end,
                    comparison=comparison,
                    absolute_change=current - previous,
                    percent_change=percent,
                )
            )
        return tuple(output)

    def _ttm_or_annual(
        self,
        dataset: FundamentalDataset,
        concept: FundamentalConcept,
        warnings: list[str],
    ) -> Decimal | None:
        metric = self._metric(dataset, concept)
        quarterly = tuple(item for item in metric.quarterly if item.value is not None)
        if concept in FLOW_CONCEPTS and len(quarterly) >= 4:
            recent = quarterly[-4:]
            span = (recent[-1].period_end - recent[0].period_end).days
            if 250 <= span <= 430:
                return sum((item.value for item in recent if item.value is not None), ZERO)
        annual = tuple(item for item in metric.annual if item.value is not None)
        if annual:
            warnings.append(
                f"{concept.value} used the latest annual value because TTM was incomplete."
            )
            return annual[-1].value
        return None

    def _reported_value(
        self, dataset: FundamentalDataset, concept: FundamentalConcept
    ) -> Decimal | None:
        values = [
            fact
            for fact in dataset.facts
            if fact.concept == concept.value and isinstance(fact.value, Decimal)
        ]
        if not values:
            return None
        latest = max(values, key=lambda item: item.period_end or dataset.as_of)
        return latest.value if isinstance(latest.value, Decimal) else None

    def _reported_history(
        self, dataset: FundamentalDataset, concept: FundamentalConcept
    ) -> tuple[FundamentalMetricPoint, ...]:
        output = []
        for fact in dataset.facts:
            if (
                fact.concept != concept.value
                or not isinstance(fact.value, Decimal)
                or fact.period_end is None
            ):
                continue
            output.append(
                FundamentalMetricPoint(
                    period_type=FinancialPeriodType.ANNUAL,
                    period_end=fact.period_end,
                    value=fact.value,
                    unit=fact.unit or "ratio",
                    provider=fact.metadata,
                )
            )
        return tuple(sorted(output, key=lambda item: item.period_end))

    def _latest_value(
        self, dataset: FundamentalDataset, concept: FundamentalConcept
    ) -> Decimal | None:
        return self._metric(dataset, concept).latest

    @staticmethod
    def _latest_metric_value(
        section: FundamentalSectionOutput, concept: FundamentalConcept
    ) -> Decimal | None:
        return next(
            (item.latest for item in section.metrics if item.concept == concept.value), None
        )

    def _snapshot_metric(
        self, snapshot: FundamentalSnapshot, concept: FundamentalConcept
    ) -> Decimal | None:
        for section in (
            snapshot.revenue,
            snapshot.profit,
            snapshot.cash_flow,
            snapshot.debt,
            snapshot.margins,
            snapshot.roe,
            snapshot.roce,
        ):
            value = self._latest_metric_value(section, concept)
            if value is not None:
                return value
        valuation = next(
            (item for item in snapshot.valuation.metrics if item.concept == concept.value), None
        )
        if valuation is None:
            return None
        return valuation.calculated if valuation.calculated is not None else valuation.reported

    @staticmethod
    def _safe_div(numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
        if numerator is None or denominator is None or denominator <= 0:
            return None
        return numerator / denominator

    def _percent(self, numerator: Decimal | None, denominator: Decimal | None) -> Decimal | None:
        ratio = self._safe_div(numerator, denominator)
        return ratio * HUNDRED if ratio is not None else None

    @staticmethod
    def _default_unit(concept: FundamentalConcept) -> str:
        return (
            "percent"
            if concept.value.endswith("margin")
            or concept in {FundamentalConcept.ROE, FundamentalConcept.ROCE}
            else "ratio"
            if concept.value.endswith("ratio") or concept in {FundamentalConcept.EV_EBITDA}
            else "currency"
        )

    @staticmethod
    def _status(available: int, total: int) -> FundamentalStatus:
        return (
            FundamentalStatus.EMPTY
            if available == 0
            else FundamentalStatus.COMPLETED
            if available == total
            else FundamentalStatus.PARTIAL
        )

    @staticmethod
    def _data_cutoff(dataset: FundamentalDataset) -> datetime | None:
        values = [item.filed_at or item.period_end for item in dataset.statements] + [
            item.metadata.retrieved_at for item in dataset.facts
        ]
        return max(values, default=None)

    def _validate_statements(self, statements: tuple[FinancialStatement, ...]) -> None:
        keys = [(item.statement_type, item.period_type, item.period_end) for item in statements]
        if len(keys) != len(set(keys)):
            raise FundamentalDataError("duplicate normalized financial statements")
        for statement in statements:
            concepts = [item.concept for item in statement.items]
            if len(concepts) != len(set(concepts)):
                raise FundamentalDataError("a financial statement contains duplicate concepts")
            capex = next(
                (
                    item.value
                    for item in statement.items
                    if item.concept == FundamentalConcept.CAPITAL_EXPENDITURE.value
                ),
                None,
            )
            if capex is not None and capex < 0:
                raise FundamentalDataError(
                    "capital_expenditure must be normalized as a positive expenditure"
                )

    @staticmethod
    def _validate_statement_order(statements: tuple[FinancialStatement, ...]) -> None:
        latest: dict[tuple[str, FinancialPeriodType], datetime] = {}
        for statement in statements:
            key = (statement.statement_type, statement.period_type)
            previous = latest.get(key)
            if previous is not None and statement.period_end <= previous:
                raise FundamentalDataError(
                    "financial statement periods must be strictly chronological within each series"
                )
            latest[key] = statement.period_end

    async def _profile(
        self, context: ExecutionContext, instrument: InstrumentRef
    ) -> tuple[CompanyProfile, CacheMetadata]:
        provider_request = CompanyProfileRequest(instrument=self._reference(instrument))
        profile, cache = await self._cached(
            "profile",
            provider_request,
            TypeAdapter(CompanyProfile),
            self._settings.fundamentals_profile_cache_ttl_seconds,
            lambda: self._provider.get_company_profile(self._context(context), provider_request),
        )
        self._validate_reference(instrument, profile.instrument)
        return profile, cache

    async def _cached(
        self,
        operation: str,
        request: BaseModel,
        adapter: TypeAdapter[OutputT],
        ttl_seconds: int,
        fetch: Callable[[], Awaitable[OutputT]],
    ) -> tuple[OutputT, CacheMetadata]:
        key = self._cache_key(operation, request)
        cached = await self._cache.get(key)
        if cached is not None:
            try:
                envelope = json.loads(cached)
                result = adapter.validate_python(envelope["payload"])
                return result, CacheMetadata(
                    disposition=CacheDisposition.HIT,
                    cached_at=datetime.fromisoformat(envelope["cached_at"]),
                    expires_at=datetime.fromisoformat(envelope["expires_at"]),
                )
            except (KeyError, TypeError, ValueError, json.JSONDecodeError, ValidationError):
                await self._cache.delete(key)
                structlog.get_logger().warning("fundamentals_cache_invalid", operation=operation)
        result = await fetch()
        now = datetime.now(UTC)
        expires = datetime.fromtimestamp(now.timestamp() + ttl_seconds, UTC)
        envelope = {
            "cached_at": now.isoformat(),
            "expires_at": expires.isoformat(),
            "payload": adapter.dump_python(result, mode="json"),
        }
        await self._cache.set(
            key,
            json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode(),
            ttl_seconds,
        )
        return result, CacheMetadata(
            disposition=CacheDisposition.MISS, cached_at=now, expires_at=expires
        )

    def _cache_key(self, operation: str, request: BaseModel) -> str:
        canonical = json.dumps(
            request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        return f"tradesentinel:fundamentals:v1:{self._chain_fingerprint}:{operation}:{digest}"

    @staticmethod
    def _reference(instrument: InstrumentRef) -> InstrumentReference:
        return InstrumentReference(
            symbol=instrument.symbol,
            exchange=instrument.exchange,
            identifier=str(instrument.instrument_id),
        )

    @staticmethod
    def _validate_reference(expected: InstrumentRef, actual: InstrumentReference) -> None:
        if actual.symbol.casefold() != expected.symbol.casefold() or (
            actual.exchange is not None
            and actual.exchange.casefold() != expected.exchange.casefold()
        ):
            raise FundamentalDataError("provider instrument does not match the request")

    @staticmethod
    def _context(context: ExecutionContext) -> ProviderContext:
        return ProviderContext(
            request_id=context.request_id,
            correlation_id=context.correlation_id,
            causation_id=context.causation_id,
            capability_run_id=context.capability_run_id,
        )
