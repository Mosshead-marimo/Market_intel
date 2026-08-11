from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from tradesentinel.api.app import create_app
from tradesentinel.domain.instruments import InstrumentRef
from tradesentinel.domain.sentiment import (
    AggregateSentimentInput,
    CollectDiscussionsInput,
    CompanyDetectionInput,
    NarrativeExtractionInput,
    ShiftDetectionInput,
    SourceWeightInput,
    SpamRemovalInput,
    TrendDetectionInput,
)
from tradesentinel.modules.instrument_resolution.seed import SEED_INSTRUMENTS
from tradesentinel.modules.public_sentiment.service import PublicSentimentService, classify
from tradesentinel.platform.config import Settings
from tradesentinel.platform.contracts import ExecutionContext
from tradesentinel.providers.contracts import (
    ProviderContext,
    ProviderMetadata,
    SentimentObservation,
    SentimentRequest,
)
from tradesentinel.providers.interfaces import SentimentProvider

NOW = datetime(2026, 8, 9, 12, tzinfo=UTC)


class FakeSentimentProvider(SentimentProvider):
    def __init__(self, observations: tuple[SentimentObservation, ...]) -> None:
        self.observations = observations
        self.context: ProviderContext | None = None

    async def collect(
        self, context: ProviderContext, request: SentimentRequest
    ) -> tuple[SentimentObservation, ...]:
        self.context = context
        return tuple(
            item
            for item in self.observations
            if (request.start is None or item.occurred_at >= request.start)
            and (request.end is None or item.occurred_at < request.end)
        )


def instrument(symbol: str = "MSFT") -> InstrumentRef:
    return next(item.to_ref() for item in SEED_INSTRUMENTS if item.symbol == symbol)


def observation(
    source_id: str,
    text: str,
    occurred_at: datetime,
    *,
    author: str | None = None,
    engagement: int = 0,
    provider_spam: bool = False,
    label: str | None = None,
    score: Decimal | None = None,
    confidence: Decimal | None = None,
) -> SentimentObservation:
    return SentimentObservation(
        source_id=source_id,
        text=text,
        occurred_at=occurred_at,
        author_id=author,
        engagement_count=engagement,
        provider_spam=provider_spam,
        label=label,
        provider_score=score,
        provider_confidence=confidence,
        source_type="social",
        metadata=ProviderMetadata(
            provider="fixture",
            source_id=source_id,
            observed_at=occurred_at,
            retrieved_at=NOW,
        ),
    )


def service(*items: SentimentObservation, **settings: object) -> PublicSentimentService:
    values = Settings(_env_file=None).model_dump()
    values.update(settings)
    return PublicSentimentService(
        FakeSentimentProvider(tuple(items)), Settings.model_validate(values)
    )


@pytest.mark.parametrize(
    ("text", "label", "score"),
    [
        ("strong growth and profit", "positive", Decimal("1")),
        ("not strong growth", "negative", Decimal("-1")),
        ("ordinary public discussion", "unknown", None),
    ],
)
def test_lexicon_classification_and_negation(text: str, label: str, score: Decimal | None) -> None:
    result = classify(observation("a", text, NOW), "lexicon-v1")
    assert result.label == label
    assert result.score == score


def test_complete_provider_signal_takes_precedence() -> None:
    result = classify(
        observation(
            "a", "weak loss", NOW, label="positive", score=Decimal("0.7"), confidence=Decimal("0.8")
        ),
        "lexicon-v1",
    )
    assert result.method == "provider"
    assert result.score == Decimal("0.7")


def test_provider_signal_contract_rejects_incomplete_pairs() -> None:
    with pytest.raises(ValueError, match="supplied together"):
        observation("a", "text", NOW, label="positive")
    with pytest.raises(ValueError, match="neutral provider labels"):
        observation(
            "b", "text", NOW, label="neutral", score=Decimal("0.1"), confidence=Decimal("0.8")
        )


@pytest.mark.asyncio
async def test_collection_hashes_author_and_propagates_context() -> None:
    provider = FakeSentimentProvider(
        (observation("a", "MSFT strong growth", NOW, author="secret"),)
    )
    analyzer = PublicSentimentService(provider, Settings(_env_file=None))
    context = ExecutionContext(request_id=uuid4())
    result = await analyzer.collect(
        context, CollectDiscussionsInput(target=instrument(), as_of=NOW + timedelta(seconds=1))
    )
    assert result.discussions[0].author_hash is not None
    assert "secret" not in result.discussions[0].model_dump_json()
    assert provider.context is not None and provider.context.request_id == context.request_id


@pytest.mark.asyncio
async def test_spam_rules_are_independent_and_duplicates_are_stable() -> None:
    items = (
        observation("short", "too short", NOW),
        observation(
            "provider",
            "MSFT normal public discussion",
            NOW + timedelta(seconds=1),
            provider_spam=True,
        ),
        observation("first", "MSFT strong growth outlook", NOW + timedelta(seconds=2)),
        observation("duplicate", "MSFT strong growth outlook", NOW + timedelta(seconds=3)),
        observation("repeat", "MSFT buy buy buy buy buy buy buy now", NOW + timedelta(seconds=4)),
    )
    analyzer = service(*items)
    collected = await analyzer.collect(
        ExecutionContext(request_id=uuid4()),
        CollectDiscussionsInput(target=instrument(), as_of=NOW + timedelta(days=1)),
    )
    result = analyzer.remove_spam(SpamRemovalInput(discussions=collected.discussions))
    reasons = {item.discussion_id: item.reasons for item in result.decisions}
    assert "too_short" in reasons[collected.discussions[0].discussion_id]
    assert any("provider_spam" in item for item in reasons.values())
    assert any("duplicate" in item for item in reasons.values())
    assert any("repeated_tokens" in item for item in reasons.values())


@pytest.mark.asyncio
async def test_catalog_detection_target_filter_and_co_mentions() -> None:
    analyzer = service(observation("a", "$MSFT partners with Apple on products", NOW))
    collected = await analyzer.collect(
        ExecutionContext(request_id=uuid4()),
        CollectDiscussionsInput(target=instrument(), as_of=NOW + timedelta(hours=1)),
    )
    result = analyzer.detect_companies(
        CompanyDetectionInput(
            target=instrument(),
            catalog=tuple(item.to_ref() for item in SEED_INSTRUMENTS),
            discussions=collected.discussions,
        )
    )
    assert len(result.relevant) == 1
    assert any(item.symbol == "AAPL" for item in result.co_mentions)


@pytest.mark.asyncio
async def test_weight_aggregate_narrative_trend_and_shift() -> None:
    items = (
        observation("old", "MSFT weak earnings risk", NOW - timedelta(days=8), engagement=0),
        observation(
            "one", "MSFT strong earnings growth", NOW - timedelta(days=2), engagement=10_000
        ),
        observation("two", "MSFT strong earnings growth", NOW - timedelta(days=1), engagement=2),
    )
    analyzer = service(*items, sentiment_minimum_mentions=1)
    collected = await analyzer.collect(
        ExecutionContext(request_id=uuid4()),
        CollectDiscussionsInput(target=instrument(), as_of=NOW),
    )
    detected = analyzer.detect_companies(
        CompanyDetectionInput(
            target=instrument(),
            catalog=tuple(item.to_ref() for item in SEED_INSTRUMENTS),
            discussions=collected.discussions,
        )
    )
    weighted = analyzer.weight_sources(SourceWeightInput(discussions=detected.relevant))
    assert max(item.engagement_multiplier for item in weighted.observations) <= Decimal("1.5")
    snapshot = analyzer.aggregate(
        AggregateSentimentInput(
            target=instrument(),
            observations=weighted.observations,
            previous_start=collected.previous_start,
            current_start=collected.current_start,
            end=collected.end,
            co_mentions=detected.co_mentions,
        )
    )
    assert snapshot.current.mean_score is not None and snapshot.current.mean_score > 0
    narratives = analyzer.narratives(
        NarrativeExtractionInput(
            target=instrument(),
            observations=weighted.observations,
            current_start=collected.current_start,
            end=collected.end,
        )
    )
    assert any(item.topic == "earnings" for item in narratives.narratives)
    assert any(item.method == "ngram" for item in narratives.narratives)
    trend = analyzer.trend(
        TrendDetectionInput(
            target=instrument(),
            observations=weighted.observations,
            start=collected.previous_start,
            end=collected.end,
        )
    )
    assert trend.direction in {"improving", "stable", "deteriorating"}
    shift = analyzer.shift(ShiftDetectionInput(snapshot=snapshot))
    assert shift.shift_score is not None and Decimal("-1") <= shift.shift_score <= Decimal("1")


def test_unknown_text_is_excluded_and_empty_is_explicit() -> None:
    analyzer = service(sentiment_minimum_mentions=2)
    snapshot = analyzer.aggregate(
        AggregateSentimentInput(
            target=instrument(),
            observations=(),
            previous_start=NOW - timedelta(days=14),
            current_start=NOW - timedelta(days=7),
            end=NOW,
        )
    )
    assert snapshot.status == "empty"
    assert snapshot.current.mean_score is None
    assert analyzer.shift(ShiftDetectionInput(snapshot=snapshot)).shift_score is None


@pytest.mark.asyncio
async def test_module_is_discovered_and_provider_free_execution_is_503(
    client: AsyncClient,
) -> None:
    capabilities = (await client.get("/api/v1/capabilities")).json()
    assert "sentiment.aggregate" in {item["name"] for item in capabilities}
    response = await client.post("/api/v1/sentiment/analyze", json={"query": "MSFT"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "PROVIDER_NOT_CONFIGURED"


def test_module_has_no_external_llm_prediction_or_private_instrument_imports() -> None:
    root = Path("apps/api/src/tradesentinel/modules/public_sentiment")
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.glob("*.py"))
    forbidden = (
        "import httpx",
        "import requests",
        "import openai",
        "import langchain",
        "from tradesentinel.modules.instrument_resolution",
    )
    assert not [token for token in forbidden if token in source.casefold()]


@pytest.mark.asyncio
async def test_complete_workflow_executes_with_manifest_provider() -> None:
    tests_root = Path(__file__).parent
    app = create_app(
        Settings(
            environment="test",
            persistence_backend="memory",
            event_backend="memory",
            cache_backend="memory",
            sentiment_providers=("fake_sentiment",),
            sentiment_minimum_mentions=1,
            module_roots=(
                tests_root.parent / "src" / "tradesentinel" / "modules",
                tests_root / "fixtures" / "sentiment_provider",
            ),
        )
    )
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/sentiment/analyze",
                json={"query": "MSFT", "as_of": NOW.isoformat(), "window_days": 7},
            )
    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"]["target"]["symbol"] == "MSFT"
    assert body["snapshot"]["current"]["mean_score"] is not None
    assert body["shift"]["shift_score"] is not None
