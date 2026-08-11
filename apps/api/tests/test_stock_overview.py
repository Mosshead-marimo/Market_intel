from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from tradesentinel.api.app import create_app
from tradesentinel.domain.stock_overview import StockOverviewWindowInput
from tradesentinel.modules.stock_overview.service import StockOverviewService
from tradesentinel.platform.config import Settings
from tradesentinel.platform.contracts import RunStatus, WorkflowDefinition
from tradesentinel.platform.manifest import ManifestParser
from tradesentinel.platform.workflows import WorkflowEngine

AS_OF = datetime(2026, 8, 9, 12, tzinfo=UTC)


def overview_settings(*, optional_providers: bool = True) -> Settings:
    tests_root = Path(__file__).parent
    api_root = tests_root.parent
    roots = [
        api_root / "src" / "tradesentinel" / "modules",
        tests_root / "fixtures" / "technical_provider",
    ]
    if optional_providers:
        roots.extend(
            (
                tests_root / "fixtures" / "news_provider",
                tests_root / "fixtures" / "sentiment_provider",
                tests_root / "fixtures" / "fundamentals_provider",
            )
        )
    return Settings(
        environment="test",
        persistence_backend="memory",
        event_backend="memory",
        cache_backend="memory",
        market_data_providers=("technical-market",),
        news_providers=("fake_news",) if optional_providers else (),
        sentiment_providers=("fake_sentiment",) if optional_providers else (),
        fundamentals_providers=("test-fundamentals",) if optional_providers else (),
        module_roots=tuple(roots),
    )


def test_window_uses_five_calendar_years_and_clamps_leap_day() -> None:
    service = StockOverviewService()
    regular = service.window(AS_OF)
    leap = service.window(datetime(2024, 2, 29, 12, tzinfo=UTC))
    assert regular.start == datetime(2021, 8, 9, 12, tzinfo=UTC)
    assert regular.end == AS_OF
    assert leap.start == datetime(2019, 2, 28, 12, tzinfo=UTC)
    assert StockOverviewWindowInput(as_of=AS_OF).as_of == AS_OF


def test_manifest_owns_dag_and_presentation_order() -> None:
    manifest = ManifestParser().parse(
        Path("apps/api/src/tradesentinel/modules/stock_overview/manifest.yaml")
    )
    workflow = manifest.workflows[0]
    assert workflow.name == "stock.overview"
    assert sum(step.capability == "instrument.resolve" for step in workflow.steps) == 1
    assert workflow.presentation is not None
    assert [section.id for section in workflow.presentation.sections] == [
        "instrument",
        "market",
        "research",
        "sentiment",
        "technical",
        "fundamentals",
    ]
    layers = WorkflowEngine().compile(workflow)
    layer_by_step = {
        step.id: layer_index for layer_index, layer in enumerate(layers) for step in layer
    }
    assert layer_by_step["quote"] == layer_by_step["research_search"]
    assert layer_by_step["quote"] == layer_by_step["sentiment_collect"]
    assert layer_by_step["quote"] == layer_by_step["fundamentals_collect"]
    assert layer_by_step["technical"] > layer_by_step["history"]


def test_presentation_rejects_unknown_and_duplicate_step_references() -> None:
    workflow = (
        ManifestParser()
        .parse(Path("apps/api/src/tradesentinel/modules/stock_overview/manifest.yaml"))
        .workflows[0]
    )
    unknown = workflow.model_dump(mode="python")
    unknown["presentation"]["sections"][0]["steps"] = ["not_a_step"]
    with pytest.raises(ValidationError, match="unknown steps"):
        WorkflowDefinition.model_validate(unknown)

    duplicate = workflow.model_dump(mode="python")
    duplicate["presentation"]["sections"][1]["steps"] = ["resolve"]
    with pytest.raises(ValidationError, match="only one section"):
        WorkflowDefinition.model_validate(duplicate)


async def test_overview_all_success_command_api_sections_and_event() -> None:
    app = create_app(overview_settings())
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/stock-overview",
                json={"query": "TCS", "exchange": "NSE", "as_of": AS_OF.isoformat()},
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["status"] in {"completed", "partial"}
            assert [item["id"] for item in body["components"]] == [
                "instrument",
                "market",
                "research",
                "sentiment",
                "technical",
                "fundamentals",
            ]
            assert all(item["type"] == "response_section" for item in body["components"])
            market = body["components"][1]
            assert {item["id"] for item in market["items"]} == {
                "market-quote",
                "market-adjusted-history",
                "market-five-year-performance",
                "market-corporate-actions",
            }
            command = await client.post(
                "/api/v1/commands/execute",
                json={"command": "/overview TCS --exchange NSE --as-of 2026-08-09T12:00:00Z"},
            )
            assert command.status_code == 200, command.text
            assert command.json()["response"]["components"][0]["id"] == "instrument"

        events = getattr(app.state.container.events, "events", ())
        overview_events = [event for event in events if event.name == "stock.overview.completed"]
        assert overview_events
        assert overview_events[-1].payload["sections"]["market"] == "ready"


async def test_optional_provider_absence_returns_partial_sections() -> None:
    app = create_app(overview_settings(optional_providers=False))
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/stock-overview",
                json={"query": "TCS", "exchange": "NSE", "as_of": AS_OF.isoformat()},
            )
            assert response.status_code == 200, response.text
            body = response.json()
            assert body["status"] == RunStatus.PARTIAL
            sections = {
                item["id"]: item
                for item in body["components"]
                if item["type"] == "response_section"
            }
            assert sections["market"]["status"] == "ready"
            assert sections["technical"]["status"] in {"ready", "partial"}
            assert sections["research"]["status"] == "error"
            assert sections["sentiment"]["status"] == "error"
            assert sections["fundamentals"]["status"] == "error"
            assert all(
                any(item["type"] == "warning_banner" for item in sections[name]["items"])
                for name in ("research", "sentiment", "fundamentals")
            )


async def test_required_market_provider_absence_is_typed_503() -> None:
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
                "/api/v1/stock-overview",
                json={"query": "TCS", "exchange": "NSE", "as_of": AS_OF.isoformat()},
            )
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "PROVIDER_NOT_CONFIGURED"
