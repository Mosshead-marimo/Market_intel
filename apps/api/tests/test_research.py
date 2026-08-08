from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from support.fake_news_provider import FakeNewsProvider
from tradesentinel.api.app import create_app
from tradesentinel.domain.research import (
    EventExtractionInput,
    NewsDeduplicateInput,
    NewsSearchInput,
    ResearchClaim,
    ResearchEventType,
    ResearchEvidenceInput,
    TimestampBasis,
)
from tradesentinel.modules.research.repository import ResearchRepositoryFactory
from tradesentinel.modules.research.service import STRONG_PHRASES, ResearchService, canonical_url
from tradesentinel.platform.config import Settings
from tradesentinel.platform.contracts import ExecutionContext
from tradesentinel.platform.persistence import PersistenceResources


def _settings() -> Settings:
    default_modules = Path(__file__).parents[1] / "src" / "tradesentinel" / "modules"
    provider_module = Path(__file__).parent / "fixtures" / "news_provider"
    return Settings(
        environment="test",
        persistence_backend="memory",
        event_backend="memory",
        cache_backend="memory",
        module_roots=(default_modules, provider_module),
        news_providers=("fake_news",),
    )


def _service(provider: FakeNewsProvider | None = None) -> ResearchService:
    sessions = cast(async_sessionmaker[AsyncSession], None)
    return ResearchService(
        provider or FakeNewsProvider(),
        ResearchRepositoryFactory(PersistenceResources(backend="memory", sessions=sessions)),
        _settings(),
    )


async def test_search_deduplicate_extract_and_evidence_are_deterministic() -> None:
    provider = FakeNewsProvider()
    service = _service(provider)
    context = ExecutionContext()
    searched = await service.search(context, NewsSearchInput(query="Example Corp"))
    assert len(searched.sources) == 5
    assert {source.timestamp_basis for source in searched.sources} == {
        TimestampBasis.PUBLISHED,
        TimestampBasis.RETRIEVED,
    }

    deduplicated = await service.deduplicate(
        NewsDeduplicateInput(query=searched.query, sources=searched.sources)
    )
    assert deduplicated.unique_count == 4
    assert deduplicated.duplicate_groups[0].reason == "canonical_url"

    extracted = await service.extract(
        context,
        EventExtractionInput(query=searched.query, sources=deduplicated.sources),
    )
    confidence_by_type = {event.event_type: event.confidence for event in extracted.events}
    assert confidence_by_type == {
        ResearchEventType.EARNINGS: 0.95,
        ResearchEventType.GUIDANCE: 0.85,
        ResearchEventType.PARTNERSHIP: 0.75,
    }
    assert extracted.unmatched_source_ids == ("fake_news:unmatched-1",)
    assert extracted.document_failures == ("fake_news:unmatched-1",)
    assert all(request.provider == "fake_news" for request in provider.document_requests)
    evidence = await service.evidence(ResearchEvidenceInput(event_id=extracted.events[0].event_id))
    assert evidence.claims[0].source.provider == "fake_news"
    assert evidence.claims[0].provider == "fake_news"
    assert evidence.claims[0].timestamp == evidence.claims[0].source.timestamp


def test_claim_contract_requires_complete_evidence() -> None:
    with pytest.raises(ValidationError):
        ResearchClaim.model_validate({"text": "Unsupported claim"})


def test_url_canonicalization_removes_only_tracking_data() -> None:
    assert canonical_url("HTTPS://EXAMPLE.COM/a/?b=2&utm_source=x&a=1#fragment") == (
        "https://example.com/a?a=1&b=2"
    )


@pytest.mark.parametrize("event_type", tuple(ResearchEventType))
def test_every_event_category_has_a_deterministic_rule(event_type: ResearchEventType) -> None:
    phrase = STRONG_PHRASES[event_type][0]
    assert ResearchService._match(f"Example Corp {phrase}", strong=True) == event_type


async def test_manifest_api_workflow_and_persisted_evidence() -> None:
    app = create_app(_settings())
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            capabilities = (await client.get("/api/v1/capabilities")).json()
            names = {item["name"] for item in capabilities}
            assert {
                "research.news.search",
                "research.news.deduplicate",
                "research.events.extract",
                "research.timeline",
                "research.report",
                "research.evidence",
            } <= names
            commands = (await client.get("/api/v1/commands")).json()
            assert {"/news", "/research", "/sources"} <= {item["name"] for item in commands}
            search = await client.get("/api/v1/research/news?q=Example%20Corp")
            assert search.status_code == 200
            report = await client.post(
                "/api/v1/research/reports", json={"query": "Example Corp", "limit": 20}
            )
            assert report.status_code == 200
            body = report.json()
            assert body["status"] == "partial"
            assert body["coverage"] == {
                "source_count": 4,
                "duplicate_count": 1,
                "event_count": 3,
                "claim_count": 3,
                "unmatched_count": 1,
                "document_failure_count": 1,
            }
            event_id = body["events"][0]["event_id"]
            evidence = await client.get(f"/api/v1/research/events/{event_id}/evidence")
            assert evidence.status_code == 200
            assert evidence.json()["claims"][0]["provider"] == "fake_news"
            assert evidence.json()["claims"][0]["source"]["provider"] == "fake_news"


async def test_provider_free_research_is_discoverable_and_returns_503() -> None:
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
            capabilities = (await client.get("/api/v1/capabilities")).json()
            assert "research.news.search" in {item["name"] for item in capabilities}
            response = await client.get("/api/v1/research/news?q=Example")
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "PROVIDER_NOT_CONFIGURED"
