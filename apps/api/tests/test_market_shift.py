from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from tradesentinel.container import build_container
from tradesentinel.domain.instruments import AssetType, InstrumentRef
from tradesentinel.domain.market_shift import (
    MarketShiftCategory,
    MarketShiftDirection,
    MarketShiftObservation,
    MarketShiftObservationBatch,
    MarketShiftScoreInput,
    MarketShiftWindow,
)
from tradesentinel.modules.market_shift.errors import MarketShiftInputIncompleteError
from tradesentinel.modules.market_shift.repository import InMemoryMarketShiftRepository
from tradesentinel.modules.market_shift.service import MarketShiftScoringService
from tradesentinel.platform.config import Settings


@pytest.fixture
def instrument() -> InstrumentRef:
    return InstrumentRef(
        instrument_id=uuid4(),
        symbol="ACME",
        name="Acme Industries",
        exchange="TEST",
        asset_type=AssetType.EQUITY,
        currency="USD",
    )


def observations(instrument: InstrumentRef, end: datetime) -> tuple[MarketShiftObservation, ...]:
    metrics = {
        MarketShiftCategory.NEWS: ("positive_news_share", "ratio"),
        MarketShiftCategory.PUBLIC_SENTIMENT: ("sentiment_mean", "score"),
        MarketShiftCategory.TECHNICAL_TREND: ("technical_trend_score", "score"),
        MarketShiftCategory.FUNDAMENTALS: ("fundamental_quality_score", "score"),
        MarketShiftCategory.SECTOR: ("sector_breadth", "ratio"),
        MarketShiftCategory.MACRO: ("macro_conditions", "score"),
        MarketShiftCategory.INSTITUTIONAL_ACTIVITY: (
            "institutional_net_flow",
            "ratio",
        ),
    }
    values: list[MarketShiftObservation] = []
    for category, (metric, unit) in metrics.items():
        for period, when, value in (
            ("previous", end - timedelta(days=120), Decimal("0.20")),
            ("current", end - timedelta(hours=1), Decimal("0.50")),
        ):
            values.append(
                MarketShiftObservation(
                    idempotency_key=f"{category.value}:{period}",
                    category=category,
                    instrument_id=instrument.instrument_id,
                    scope=str(instrument.instrument_id),
                    metric=metric,
                    value=value,
                    unit=unit,
                    observed_at=when,
                    known_at=when,
                    retrieved_at=end,
                    source_id=f"{category.value}:{period}",
                    provider="test-provider",
                    source_version="test-v1",
                )
            )
    return tuple(values)


def test_scoring_requires_all_categories(instrument: InstrumentRef) -> None:
    end = datetime(2026, 8, 12, tzinfo=UTC)
    with pytest.raises(MarketShiftInputIncompleteError):
        MarketShiftScoringService().calculate(
            MarketShiftScoreInput(
                instrument=instrument,
                window=MarketShiftWindow.ending_at(end, 90),
                observations=(),
                idempotency_key="missing",
            )
        )


def test_scoring_is_deterministic_evidence_backed_and_non_predictive(
    instrument: InstrumentRef,
) -> None:
    end = datetime(2026, 8, 12, tzinfo=UTC)
    payload = MarketShiftScoreInput(
        instrument=instrument,
        window=MarketShiftWindow.ending_at(end, 90),
        observations=observations(instrument, end),
        idempotency_key="score-v1",
    )
    first = MarketShiftScoringService().calculate(payload)
    second = MarketShiftScoringService().calculate(payload)
    assert first.score == second.score == Decimal("21.00")
    assert first.direction == MarketShiftDirection.IMPROVING
    assert len(first.category_signals) == len(MarketShiftCategory)
    assert len(first.evidence) == len(MarketShiftCategory)
    assert all(driver.evidence_ids for driver in first.catalysts)
    assert "prediction" not in first.model_dump_json().lower()


@pytest.mark.asyncio
async def test_memory_repository_is_idempotent_and_tracks_history(
    instrument: InstrumentRef,
) -> None:
    repository = InMemoryMarketShiftRepository()
    end = datetime(2026, 8, 12, tzinfo=UTC)
    batch = MarketShiftObservationBatch(
        idempotency_key="batch", observations=observations(instrument, end)
    )
    first = await repository.ingest(batch)
    duplicate = await repository.ingest(batch)
    assert first.accepted == 14
    assert duplicate.duplicate is True
    loaded = await repository.observations(instrument.instrument_id, end - timedelta(days=180), end)
    assert len(loaded) == 14


@pytest.mark.asyncio
async def test_module_command_workflow_and_worker_are_discovered() -> None:
    container = build_container(Settings(environment="test"))
    try:
        names = {item.descriptor.name for item in container.capabilities.list()}
        assert "market_shift.calculate" in names
        assert container.commands.get("/market-shift").target.name == "market_shift.request"
        assert container.workflows.get("market_shift.request").steps[-1].id == "calculate"
        assert any(
            worker.__class__.__name__ == "MarketShiftBackgroundWorker"
            for worker in container.loader.background_workers
        )
    finally:
        await container.close()
