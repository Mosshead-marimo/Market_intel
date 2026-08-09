from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from tradesentinel.providers.contracts import (
    ProviderContext,
    ProviderMetadata,
    SentimentObservation,
    SentimentRequest,
)
from tradesentinel.providers.interfaces import SentimentProvider

NOW = datetime(2026, 8, 9, 12, tzinfo=UTC)


class FakeSentimentProvider(SentimentProvider):
    async def collect(
        self, context: ProviderContext, request: SentimentRequest
    ) -> tuple[SentimentObservation, ...]:
        del context, request
        return tuple(
            SentimentObservation(
                source_id=f"discussion-{index}",
                text=text,
                occurred_at=NOW - timedelta(days=days),
                source_type="social",
                engagement_count=index,
                label=label,
                provider_score=score,
                provider_confidence=Decimal("0.8"),
                metadata=ProviderMetadata(
                    provider="fake_sentiment",
                    source_id=f"discussion-{index}",
                    observed_at=NOW - timedelta(days=days),
                    retrieved_at=NOW,
                ),
            )
            for index, (days, text, label, score) in enumerate(
                (
                    (9, "MSFT weak earnings risk", "negative", Decimal("-0.7")),
                    (2, "MSFT strong earnings growth", "positive", Decimal("0.8")),
                    (1, "Microsoft strong earnings growth", "positive", Decimal("0.6")),
                ),
                start=1,
            )
        )
