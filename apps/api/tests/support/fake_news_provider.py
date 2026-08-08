from __future__ import annotations

from datetime import UTC, datetime

from tradesentinel.providers.contracts import (
    FreshnessStatus,
    LicenseClassification,
    NewsArticle,
    NewsDocument,
    NewsDocumentRequest,
    NewsSearchRequest,
    ProviderContext,
    ProviderMetadata,
)
from tradesentinel.providers.errors import ProviderUnavailableError
from tradesentinel.providers.interfaces import NewsProvider

NOW = datetime(2026, 8, 8, 10, 0, tzinfo=UTC)


def metadata(source_id: str) -> ProviderMetadata:
    return ProviderMetadata(
        provider="fake_news",
        source_id=source_id,
        observed_at=NOW,
        retrieved_at=NOW,
        timezone="UTC",
        license=LicenseClassification.REDISTRIBUTABLE,
        freshness=FreshnessStatus.FRESH,
    )


class FakeNewsProvider(NewsProvider):
    def __init__(self) -> None:
        self.document_requests: list[NewsDocumentRequest] = []

    async def search(
        self, context: ProviderContext, request: NewsSearchRequest
    ) -> tuple[NewsArticle, ...]:
        del context, request
        return (
            NewsArticle(
                source_id="earnings-1",
                title="Example Corp reports earnings above prior quarter",
                url="https://news.example.test/earnings?utm_source=test",
                published_at=NOW,
                summary="Revenue rose during the quarter.",
                metadata=metadata("earnings-1"),
            ),
            NewsArticle(
                source_id="earnings-copy",
                title="Example Corp reports earnings above prior quarter",
                url="https://news.example.test/earnings?utm_medium=copy",
                published_at=NOW,
                summary="Duplicate wire copy.",
                metadata=metadata("earnings-copy"),
            ),
            NewsArticle(
                source_id="guidance-1",
                title="Example Corp business update",
                url="https://news.example.test/guidance",
                published_at=NOW,
                summary="The company raises guidance for the year.",
                metadata=metadata("guidance-1"),
            ),
            NewsArticle(
                source_id="document-1",
                title="Example Corp files a company notice",
                url="https://news.example.test/document",
                published_at=None,
                metadata=metadata("document-1"),
            ),
            NewsArticle(
                source_id="unmatched-1",
                title="Example Corp general profile",
                url="https://news.example.test/profile",
                published_at=None,
                metadata=metadata("unmatched-1"),
            ),
        )

    async def get_document(
        self, context: ProviderContext, request: NewsDocumentRequest
    ) -> NewsDocument:
        del context
        self.document_requests.append(request)
        if request.source_id == "unmatched-1":
            raise ProviderUnavailableError("fake_news")
        return NewsDocument(
            source_id=request.source_id,
            title="Example Corp files a company notice",
            url="https://news.example.test/document",
            content="Example Corp enters a strategic partnership with a supplier.",
            content_type="text/plain",
            published_at=None,
            metadata=metadata(request.source_id),
        )
