from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from support.fake_technical_provider import technical_test_settings
from tradesentinel.api.app import create_app
from tradesentinel.domain.instruments import AssetType, InstrumentRef
from tradesentinel.domain.market_data import (
    AdjustedPriceBar,
    CacheMetadata,
    MarketInterval,
    StockHistoryOutput,
)
from tradesentinel.domain.technical import (
    TechnicalCalculationInput,
    TechnicalParameters,
    TechnicalStatus,
    TechnicalWindowInput,
)
from tradesentinel.modules.technical_analysis.capability import RsiCapability
from tradesentinel.modules.technical_analysis.errors import (
    TechnicalDataError,
    TechnicalInsufficientHistoryError,
)
from tradesentinel.modules.technical_analysis.service import TechnicalAnalysisService
from tradesentinel.platform.config import Settings
from tradesentinel.platform.contracts import ExecutionContext
from tradesentinel.platform.events import InMemoryEventBus
from tradesentinel.platform.manifest import ManifestParser
from tradesentinel.providers.contracts import ProviderMetadata

NOW = datetime(2026, 8, 1, tzinfo=UTC)
INSTRUMENT = InstrumentRef(
    instrument_id=UUID("00000000-0000-0000-0000-000000000101"),
    symbol="TEST",
    name="Test Corporation",
    exchange="XTEST",
    asset_type=AssetType.EQUITY,
    currency="USD",
)


def calculation(
    closes: Sequence[Decimal | int | str],
    *,
    parameters: TechnicalParameters | None = None,
    interval: MarketInterval = MarketInterval.DAILY,
    bars: tuple[AdjustedPriceBar, ...] | None = None,
) -> TechnicalCalculationInput:
    converted = tuple(
        AdjustedPriceBar(
            timestamp=NOW + timedelta(days=index),
            open=Decimal(str(value)),
            high=Decimal(str(value)) + Decimal("1"),
            low=Decimal(str(value)) - min(Decimal("1"), Decimal(str(value)) * Decimal("0.5")),
            close=Decimal(str(value)),
            adjusted_close=Decimal(str(value)),
            volume=Decimal("1000"),
        )
        for index, value in enumerate(closes)
    )
    selected = converted if bars is None else bars
    return TechnicalCalculationInput(
        history=StockHistoryOutput(
            instrument=INSTRUMENT,
            interval=interval,
            currency="USD",
            bars=selected,
            provider=ProviderMetadata(
                provider="test-market",
                source_id="test-series",
                observed_at=selected[-1].timestamp if selected else None,
                retrieved_at=NOW,
            ),
            cache=CacheMetadata(
                disposition="miss",
                cached_at=NOW,
                expires_at=NOW + timedelta(hours=6),
            ),
        ),
        requested_start=NOW,
        requested_end=NOW + timedelta(days=max(len(selected), 1)),
        parameters=parameters or TechnicalParameters(),
    )


def test_manifest_declares_every_capability_and_command() -> None:
    manifest = ManifestParser().parse(
        Path("apps/api/src/tradesentinel/modules/technical_analysis/manifest.yaml")
    )
    names = {item.name for item in manifest.capabilities}
    assert names == {
        "technical.window.resolve",
        "technical.rsi",
        "technical.macd",
        "technical.ema",
        "technical.sma",
        "technical.atr",
        "technical.adx",
        "technical.support",
        "technical.resistance",
        "technical.trend",
        "technical.momentum",
        "technical.volatility",
        "technical.snapshot",
    }
    assert {item.name for item in manifest.commands} == {
        "/technical",
        "/rsi",
        "/macd",
        "/ema",
        "/sma",
        "/atr",
        "/adx",
        "/support",
        "/resistance",
        "/trend",
        "/momentum",
        "/volatility",
    }


def test_parameter_relationships_and_range_shape_are_strict() -> None:
    with pytest.raises(ValidationError, match="MACD fast period"):
        TechnicalParameters(macd_fast_period=26, macd_slow_period=26)
    with pytest.raises(ValidationError, match="trend fast period"):
        TechnicalParameters(trend_fast_period=50, trend_slow_period=20)
    with pytest.raises(ValidationError, match="percentile thresholds"):
        TechnicalParameters(
            volatility_low_percentile=Decimal("0.8"),
            volatility_high_percentile=Decimal("0.2"),
        )
    with pytest.raises(ValidationError, match="start and end"):
        TechnicalWindowInput(start=NOW)


def test_window_uses_one_calendar_year_and_handles_leap_day() -> None:
    service = TechnicalAnalysisService()
    end = datetime(2024, 2, 29, 15, tzinfo=UTC)
    window = service.window(TechnicalWindowInput(as_of=end))
    assert window.end == end
    assert window.start == datetime(2023, 2, 28, 15, tzinfo=UTC)


def test_adjusted_ohlc_uses_adjusted_close_ratio() -> None:
    bar = AdjustedPriceBar(
        timestamp=NOW,
        open=Decimal("90"),
        high=Decimal("110"),
        low=Decimal("80"),
        close=Decimal("100"),
        adjusted_close=Decimal("50"),
        volume=Decimal("10"),
    )
    adjusted = TechnicalAnalysisService().adjusted_bars(calculation([], bars=(bar,)))[0]
    assert adjusted.open == Decimal("45")
    assert adjusted.high == Decimal("55")
    assert adjusted.low == Decimal("40")
    assert adjusted.close == Decimal("50")
    assert adjusted.volume == Decimal("10")


def test_adjustment_rejects_invalid_and_duplicate_observations() -> None:
    invalid = AdjustedPriceBar(
        timestamp=NOW,
        open=Decimal("10"),
        high=Decimal("9"),
        low=Decimal("8"),
        close=Decimal("10"),
        adjusted_close=Decimal("10"),
    )
    with pytest.raises(TechnicalDataError):
        TechnicalAnalysisService().adjusted_bars(calculation([], bars=(invalid,)))
    valid = invalid.model_copy(update={"high": Decimal("11")})
    with pytest.raises(TechnicalDataError) as error:
        TechnicalAnalysisService().adjusted_bars(calculation([], bars=(valid, valid)))
    assert error.value.details["reason"] == "history timestamps must be unique and ascending"


def test_sma_and_sma_seeded_ema_match_reference_values() -> None:
    params = TechnicalParameters(sma_period=3, ema_period=3)
    request = calculation([1, 2, 3, 4, 5], parameters=params)
    service = TechnicalAnalysisService()
    assert [point.value for point in service.sma(request).series.points] == [
        Decimal("2"),
        Decimal("3"),
        Decimal("4"),
    ]
    assert [point.value for point in service.ema(request).series.points] == [
        Decimal("2"),
        Decimal("3.0"),
        Decimal("4.00"),
    ]


@pytest.mark.parametrize(
    ("closes", "expected"),
    [
        ([10] * 8, Decimal("50")),
        (list(range(10, 18)), Decimal("100")),
        (list(range(18, 10, -1)), Decimal("0")),
    ],
)
def test_wilder_rsi_boundaries(closes: list[int], expected: Decimal) -> None:
    params = TechnicalParameters(rsi_period=3)
    result = TechnicalAnalysisService().rsi(calculation(closes, parameters=params))
    assert result.series.latest == expected


def test_macd_is_sma_seeded_and_aligned() -> None:
    params = TechnicalParameters(
        macd_fast_period=3,
        macd_slow_period=5,
        macd_signal_period=2,
    )
    result = TechnicalAnalysisService().macd(calculation(list(range(1, 12)), parameters=params))
    assert len(result.points) == 6
    assert result.latest.macd == Decimal("1")
    assert result.latest.signal == Decimal("1.00000")
    assert result.latest.histogram == Decimal("0.00000")


def test_wilder_atr_and_adx_on_rising_history() -> None:
    params = TechnicalParameters(atr_period=3, adx_period=3)
    request = calculation(list(range(20, 40)), parameters=params)
    service = TechnicalAnalysisService()
    assert service.atr(request).series.latest == Decimal("2")
    adx = service.adx(request)
    assert adx.latest.adx == Decimal("100")
    assert adx.latest.positive_di > adx.latest.negative_di


def test_support_and_resistance_include_extrema_and_clustered_pivots() -> None:
    params = TechnicalParameters(
        atr_period=3,
        level_lookback=9,
        pivot_span=1,
        pivot_max_levels=3,
        pivot_atr_multiplier=Decimal("1"),
    )
    request = calculation([10, 8, 10, 8, 10, 8, 10, 12, 10], parameters=params)
    service = TechnicalAnalysisService()
    support = service.support(request)
    resistance = service.resistance(request)
    assert support.levels[0].method == "rolling_extreme"
    assert any(level.method == "pivot_cluster" and level.touches >= 2 for level in support.levels)
    assert resistance.levels[0].method == "rolling_extreme"
    assert len(support.levels) <= 4
    assert len(resistance.levels) <= 4


def test_trend_momentum_and_volatility_are_descriptive() -> None:
    params = TechnicalParameters(
        rsi_period=5,
        macd_fast_period=3,
        macd_slow_period=6,
        macd_signal_period=3,
        atr_period=5,
        adx_period=5,
        momentum_roc_period=3,
        volatility_period=5,
        trend_fast_period=5,
        trend_slow_period=10,
    )
    values = [Decimal(100 + index) + Decimal(index % 3) / Decimal(10) for index in range(40)]
    request = calculation(values, parameters=params)
    service = TechnicalAnalysisService()
    assert service.trend(request).direction == "rising"
    assert service.momentum(request).direction == "positive"
    volatility = service.volatility(request)
    assert volatility.annualized_volatility >= 0
    assert volatility.regime in {"low", "normal", "high"}
    assert volatility.percentile_rank is not None


def test_annualization_changes_with_interval() -> None:
    params = TechnicalParameters(volatility_period=3, atr_period=3)
    values = [100, 101, 99, 103, 102, 107, 105, 110]
    service = TechnicalAnalysisService()
    daily = service.volatility(calculation(values, parameters=params)).annualized_volatility
    weekly = service.volatility(
        calculation(values, parameters=params, interval=MarketInterval.WEEKLY)
    ).annualized_volatility
    monthly = service.volatility(
        calculation(values, parameters=params, interval=MarketInterval.MONTHLY)
    ).annualized_volatility
    assert daily > weekly > monthly


def test_individual_indicator_fails_but_snapshot_is_partial() -> None:
    service = TechnicalAnalysisService()
    request = calculation(list(range(10, 35)))
    with pytest.raises(TechnicalInsufficientHistoryError) as error:
        service.adx(request)
    assert error.value.code == "TECHNICAL_INSUFFICIENT_HISTORY"
    snapshot = service.snapshot(request)
    assert snapshot.status == TechnicalStatus.PARTIAL
    assert snapshot.sma is not None
    assert snapshot.trend is None
    assert snapshot.warnings
    assert snapshot.price_basis == "adjusted_ohlc"
    assert snapshot.calculation_version == "technical-v1"


def test_empty_snapshot_never_invents_indicator_values() -> None:
    snapshot = TechnicalAnalysisService().snapshot(calculation([]))
    assert snapshot.status == TechnicalStatus.EMPTY
    assert snapshot.observation_count == 0
    assert snapshot.rsi is None
    assert snapshot.volatility is None
    assert len(snapshot.warnings) == 11


async def test_capability_emits_correlated_structured_lifecycle_event() -> None:
    bus = InMemoryEventBus()
    capability = RsiCapability(TechnicalAnalysisService(), bus)
    run_id = UUID("00000000-0000-4000-8000-000000000099")
    await capability.execute(
        ExecutionContext(capability_run_id=run_id),
        calculation(list(range(10, 40)), parameters=TechnicalParameters(rsi_period=5)),
    )
    event = bus.events[-1]
    assert event.name == "technical.rsi.completed"
    assert event.payload["status"] == "completed"
    assert event.payload["observation_count"] == 25
    assert event.payload["capability_run_id"] == str(run_id)


async def test_module_routes_and_commands_are_discovered_automatically() -> None:
    app = create_app(technical_test_settings())
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            capabilities = {
                item["name"] for item in (await client.get("/api/v1/capabilities")).json()
            }
            commands = {item["name"] for item in (await client.get("/api/v1/commands")).json()}
            assert "technical.snapshot" in capabilities
            assert {"/technical", "/rsi", "/volatility"} <= commands
            snapshot = await client.post(
                "/api/v1/technical/snapshot",
                json={
                    "query": "TCS",
                    "exchange": "NSE",
                    "as_of": "2026-08-01T00:00:00Z",
                },
            )
            assert snapshot.status_code == 200, snapshot.text
            payload = snapshot.json()
            assert payload["status"] == "completed"
            assert payload["price_basis"] == "adjusted_ohlc"
            assert payload["observation_count"] >= 360
            assert payload["rsi"]["series"]["points"]

            command = await client.post(
                "/api/v1/commands/execute",
                json={"command": "/rsi TCS --exchange NSE --rsi-period 5"},
            )
            assert command.status_code == 200, command.text
            result = command.json()["result"]["steps"]["result"]["data"]
            assert result["series"]["period"] == 5


async def test_unconfigured_market_data_is_a_typed_503() -> None:
    app = create_app(
        Settings(
            environment="test",
            persistence_backend="memory",
            event_backend="memory",
            cache_backend="memory",
        )
    )
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/technical/rsi",
                json={"query": "TCS", "exchange": "NSE"},
            )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROVIDER_NOT_CONFIGURED"
