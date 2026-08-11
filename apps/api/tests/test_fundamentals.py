from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from support.fake_fundamentals_provider import (
    DeterministicFundamentalsProvider,
    fundamentals_test_settings,
)
from support.fake_market_provider import DeterministicMarketDataProvider
from tradesentinel.api.app import create_app
from tradesentinel.domain.fundamentals import (
    FundamentalAnalysisRequest,
    FundamentalConcept,
    FundamentalDataInput,
    FundamentalDataset,
    FundamentalDatasetInput,
    FundamentalMetric,
    FundamentalPeerComparisonInput,
    FundamentalPeerSelectionInput,
    FundamentalSectionOutput,
    FundamentalSnapshotInput,
    FundamentalStatus,
    FundamentalValuationInput,
)
from tradesentinel.domain.instruments import (
    InstrumentCatalogOutput,
    InstrumentRef,
    InstrumentResolveBatchOutput,
)
from tradesentinel.domain.market_data import StockQuoteInput
from tradesentinel.modules.fundamentals.capability import (
    CashFlowCapability,
    DebtCapability,
    GrowthCapability,
    MarginsCapability,
    ProfitCapability,
    RevenueCapability,
    RoceCapability,
    RoeCapability,
)
from tradesentinel.modules.fundamentals.errors import FundamentalPeersUnavailableError
from tradesentinel.modules.fundamentals.service import FundamentalAnalysisService
from tradesentinel.modules.instrument_resolution.seed import SEED_INSTRUMENTS
from tradesentinel.modules.stock_market_data.service import StockMarketDataService
from tradesentinel.platform.cache import InMemoryCacheStore
from tradesentinel.platform.capabilities import Capability
from tradesentinel.platform.config import Settings
from tradesentinel.platform.contracts import ExecutionContext
from tradesentinel.platform.events import InMemoryEventBus
from tradesentinel.platform.manifest import ManifestParser
from tradesentinel.providers.contracts import FinancialPeriodType, FinancialStatement

AS_OF = datetime(2026, 1, 1, tzinfo=UTC)


def instrument(symbol: str, exchange: str = "NSE") -> InstrumentRef:
    return next(
        item.to_ref()
        for item in SEED_INSTRUMENTS
        if item.symbol == symbol and item.exchange == exchange
    )


def service(cache: InMemoryCacheStore | None = None) -> FundamentalAnalysisService:
    return FundamentalAnalysisService(
        DeterministicFundamentalsProvider(),
        cache or InMemoryCacheStore(),
        Settings(fundamentals_providers=("test-fundamentals",)),
    )


async def dataset(symbol: str = "TCS", exchange: str = "NSE") -> FundamentalDataset:
    return await service().collect(
        ExecutionContext(),
        FundamentalDataInput(instrument=instrument(symbol, exchange), as_of=AS_OF),
    )


def metric(section: FundamentalSectionOutput, concept: FundamentalConcept) -> FundamentalMetric:
    return next(item for item in section.metrics if item.concept == concept.value)


def test_contracts_keep_periods_separate_and_parse_comma_separated_peers() -> None:
    request = FundamentalAnalysisRequest(query="TCS", peers="INFY@NSE, RELIANCE@NSE")
    assert request.peers == ("INFY@NSE", "RELIANCE@NSE")
    with pytest.raises(ValidationError, match="unique"):
        FundamentalAnalysisRequest(query="TCS", peers="INFY,infy")
    with pytest.raises(ValidationError, match="fiscal quarter"):
        FinancialStatement.model_validate(
            {
                "instrument": {
                    "symbol": "TCS",
                    "exchange": "NSE",
                },
                "statement_type": "income",
                "period_type": FinancialPeriodType.QUARTERLY,
                "period_start": "2025-01-01T00:00:00Z",
                "period_end": "2025-03-31T00:00:00Z",
                "items": [],
                "metadata": {
                    "provider": "test",
                    "source_id": "statement",
                    "retrieved_at": "2025-04-01T00:00:00Z",
                },
            }
        )


async def test_collection_validates_and_caches_provider_results() -> None:
    DeterministicFundamentalsProvider.profile_calls = 0
    DeterministicFundamentalsProvider.statement_calls = 0
    DeterministicFundamentalsProvider.fact_calls = 0
    analyzer = service(InMemoryCacheStore())
    request = FundamentalDataInput(instrument=instrument("TCS"), as_of=AS_OF)
    first = await analyzer.collect(ExecutionContext(), request)
    second = await analyzer.collect(ExecutionContext(), request)
    assert len(first.statements) == 39
    assert first.cache.profile.disposition == "miss"
    assert second.cache.profile.disposition == "hit"
    assert DeterministicFundamentalsProvider.profile_calls == 1
    assert DeterministicFundamentalsProvider.statement_calls == 1
    assert DeterministicFundamentalsProvider.fact_calls == 1


async def test_sections_calculate_trends_margins_returns_and_growth() -> None:
    data = await dataset()
    analyzer = service()
    revenue = analyzer.revenue(data)
    assert len(metric(revenue, FundamentalConcept.REVENUE).annual) == 5
    assert len(metric(revenue, FundamentalConcept.REVENUE).quarterly) == 8

    cash = analyzer.cash_flow(data)
    assert metric(cash, FundamentalConcept.FREE_CASH_FLOW).annual[-1].value == Decimal("210")
    debt = analyzer.debt(data)
    assert metric(debt, FundamentalConcept.NET_DEBT).latest == Decimal("200")
    margins = analyzer.margins(data)
    assert metric(margins, FundamentalConcept.GROSS_MARGIN).latest == Decimal("40.0")
    assert metric(margins, FundamentalConcept.NET_MARGIN).latest == Decimal("15.00")

    roe = metric(analyzer.roe(data), FundamentalConcept.ROE)
    roce = metric(analyzer.roce(data), FundamentalConcept.ROCE)
    assert len(roe.annual) == 4 and len(roe.quarterly) == 4
    assert len(roce.annual) == 4 and len(roce.quarterly) == 4
    assert roe.annual[-1].value == Decimal("210") / Decimal("1175") * Decimal("100")
    assert roce.annual[-1].value == Decimal("252") / Decimal("1375") * Decimal("100")

    growth = analyzer.growth(data)
    revenue_growth = next(
        item for item in growth.metrics if item.concept == FundamentalConcept.REVENUE.value
    )
    assert len(revenue_growth.annual_yoy) == 4
    assert len(revenue_growth.quarterly_yoy) == 4
    assert len(revenue_growth.quarterly_qoq) == 7
    assert revenue_growth.annual_cagr is not None


async def test_each_accounting_capability_executes_independently() -> None:
    data = await dataset()
    analyzer = service()
    events = InMemoryEventBus()
    capabilities: tuple[Capability[FundamentalDatasetInput], ...] = (
        RevenueCapability(analyzer, events),
        ProfitCapability(analyzer, events),
        CashFlowCapability(analyzer, events),
        DebtCapability(analyzer, events),
        MarginsCapability(analyzer, events),
        RoeCapability(analyzer, events),
        RoceCapability(analyzer, events),
        GrowthCapability(analyzer, events),
    )
    for capability in capabilities:
        result = await capability.execute(ExecutionContext(), FundamentalDatasetInput(dataset=data))
        assert result.status in {"completed", "partial"}
        assert result.data


async def test_valuation_distinguishes_calculated_reported_and_reported_only() -> None:
    data = await dataset()
    quote_service = StockMarketDataService(
        DeterministicMarketDataProvider(),
        InMemoryCacheStore(),
        Settings(market_data_providers=("technical-market",)),
    )
    quote = await quote_service.quote(
        ExecutionContext(), StockQuoteInput(instrument=data.instrument)
    )
    analyzer = service()
    valuation = analyzer.valuation(FundamentalValuationInput(dataset=data, quotes=(quote,)))
    market_cap = next(
        item for item in valuation.metrics if item.concept == FundamentalConcept.MARKET_CAP.value
    )
    pe = next(
        item for item in valuation.metrics if item.concept == FundamentalConcept.PE_RATIO.value
    )
    assert market_cap.calculated == Decimal("11000")
    assert pe.calculated == Decimal("11000") / Decimal("183")
    assert pe.reported == Decimal("22")
    assert len(pe.historical_reported) == 3

    reported_only = analyzer.valuation(FundamentalValuationInput(dataset=data))
    assert reported_only.status == FundamentalStatus.PARTIAL
    assert any("Current market data" in warning for warning in reported_only.warnings)
    assert next(
        item for item in reported_only.metrics if item.concept == FundamentalConcept.PE_RATIO.value
    ).reported == Decimal("22")


async def test_snapshot_and_peer_selection_are_deterministic_and_non_composite() -> None:
    analyzer = service(InMemoryCacheStore())
    target = await analyzer.collect(
        ExecutionContext(), FundamentalDataInput(instrument=instrument("TCS"), as_of=AS_OF)
    )
    empty_explicit = InstrumentResolveBatchOutput(results=(), instruments=())
    catalog = InstrumentCatalogOutput(instruments=tuple(item.to_ref() for item in SEED_INSTRUMENTS))
    selected = await analyzer.select_peers(
        ExecutionContext(),
        FundamentalPeerSelectionInput(
            target=target, explicit=empty_explicit, catalog=catalog, maximum_peers=5
        ),
    )
    assert selected.mode == "automatic"
    assert selected.peers[0].symbol == "INFY"
    assert len(selected.peers) <= 5
    assert len({item.symbol for item in selected.peers}) == len(selected.peers)

    peer_data = await analyzer.collect(
        ExecutionContext(),
        FundamentalDataInput(instrument=selected.peers[0], as_of=AS_OF),
    )
    comparison = analyzer.peer_comparison(
        FundamentalPeerComparisonInput(target=target, peers=(peer_data,))
    )
    assert comparison.status in {FundamentalStatus.COMPLETED, FundamentalStatus.PARTIAL}
    assert all(item.concept != FundamentalConcept.REVENUE.value for item in comparison.comparisons)
    assert all("score" not in item.concept for item in comparison.comparisons)
    assert all(
        value.percentile is None or Decimal(0) <= value.percentile <= Decimal(1)
        for comparison_metric in comparison.comparisons
        for value in comparison_metric.values
    )

    duplicate = InstrumentResolveBatchOutput(results=(), instruments=(instrument("TCS", "BSE"),))
    with pytest.raises(FundamentalPeersUnavailableError):
        await analyzer.select_peers(
            ExecutionContext(),
            FundamentalPeerSelectionInput(target=target, explicit=duplicate, catalog=catalog),
        )

    snapshot = analyzer.snapshot(FundamentalSnapshotInput(dataset=target))
    assert snapshot.calculation_version == "fundamentals-v1"
    assert snapshot.status == FundamentalStatus.PARTIAL


def test_manifest_registers_all_capabilities_commands_and_workflows() -> None:
    manifest = ManifestParser().parse(
        Path("apps/api/src/tradesentinel/modules/fundamentals/manifest.yaml")
    )
    assert len(manifest.capabilities) == 14
    assert {item.name for item in manifest.commands} == {
        "/fundamentals",
        "/revenue",
        "/profit",
        "/cash-flow",
        "/debt",
        "/margins",
        "/roe",
        "/roce",
        "/valuation",
        "/growth",
        "/peer-compare",
    }
    assert len(manifest.workflows) == 11


async def test_module_routes_commands_and_lazy_provider_error() -> None:
    app = create_app(fundamentals_test_settings())
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/fundamentals/snapshot",
                json={"query": "TCS", "exchange": "NSE", "as_of": AS_OF.isoformat()},
            )
            assert response.status_code == 200, response.text
            assert response.json()["instrument"]["symbol"] == "TCS"
            assert response.json()["revenue"]["metrics"][0]["annual"]
            for path in (
                "revenue",
                "profit",
                "cash-flow",
                "debt",
                "margins",
                "roe",
                "roce",
                "valuation",
                "growth",
                "peer-comparison",
            ):
                route_response = await client.post(
                    f"/api/v1/fundamentals/{path}",
                    json={"query": "TCS", "exchange": "NSE", "as_of": AS_OF.isoformat()},
                )
                assert route_response.status_code == 200, (path, route_response.text)
            commands = await client.get("/api/v1/commands")
            assert "/fundamentals" in {item["name"] for item in commands.json()}
            command = await client.post(
                "/api/v1/commands/execute",
                json={"command": "/revenue TCS --exchange NSE"},
            )
            assert command.status_code == 200, command.text

    providerless = create_app(
        Settings(
            environment="test",
            persistence_backend="memory",
            event_backend="memory",
            cache_backend="memory",
        )
    )
    async with providerless.router.lifespan_context(providerless):
        async with AsyncClient(
            transport=ASGITransport(app=providerless), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/fundamentals/revenue", json={"query": "TCS", "exchange": "NSE"}
            )
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "PROVIDER_NOT_CONFIGURED"
