from __future__ import annotations

import hashlib
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import NAMESPACE_URL, uuid5

from tradesentinel.domain.research import (
    ConfidenceBasis,
    DuplicateGroup,
    EventExtractionInput,
    EventExtractionOutput,
    NewsDeduplicateInput,
    NewsDeduplicateOutput,
    NewsSearchInput,
    NewsSearchOutput,
    ResearchClaim,
    ResearchCoverage,
    ResearchEvent,
    ResearchEventType,
    ResearchEvidenceInput,
    ResearchEvidenceOutput,
    ResearchReportInput,
    ResearchReportOutput,
    ResearchSource,
    ResearchTimelineInput,
    ResearchTimelineOutput,
    TimestampBasis,
)
from tradesentinel.modules.research.repository import ResearchRepositoryFactory
from tradesentinel.platform.config import Settings
from tradesentinel.platform.contracts import ExecutionContext
from tradesentinel.providers.contracts import (
    NewsArticle,
    NewsDocumentRequest,
    NewsSearchRequest,
    ProviderContext,
)
from tradesentinel.providers.errors import ProviderError
from tradesentinel.providers.interfaces import NewsProvider

TRACKING_PARAMETERS = {"fbclid", "gclid", "mc_cid", "mc_eid"}

STRONG_PHRASES: dict[ResearchEventType, tuple[str, ...]] = {
    ResearchEventType.EARNINGS: ("reports earnings", "quarterly results", "earnings results"),
    ResearchEventType.GUIDANCE: ("raises guidance", "cuts guidance", "reaffirms guidance"),
    ResearchEventType.DIVIDEND: ("declares dividend", "dividend increase", "dividend cut"),
    ResearchEventType.MERGER_ACQUISITION: (
        "to acquire",
        "acquisition agreement",
        "merger agreement",
    ),
    ResearchEventType.LEADERSHIP: ("appoints chief", "names chief", "chief executive resigns"),
    ResearchEventType.PRODUCT: ("launches new", "unveils new", "product launch"),
    ResearchEventType.PARTNERSHIP: ("strategic partnership", "partners with", "joint venture"),
    ResearchEventType.FINANCING: ("raises funding", "debt offering", "share offering"),
    ResearchEventType.REGULATORY_LEGAL: (
        "regulatory approval",
        "files lawsuit",
        "antitrust investigation",
    ),
    ResearchEventType.OPERATIONS: ("opens facility", "closes facility", "production halt"),
    ResearchEventType.OTHER: ("announces update",),
}

RULE_PHRASES: dict[ResearchEventType, tuple[str, ...]] = {
    ResearchEventType.EARNINGS: ("earnings", "revenue", "quarterly profit"),
    ResearchEventType.GUIDANCE: ("guidance", "outlook", "forecast"),
    ResearchEventType.DIVIDEND: ("dividend", "share buyback", "stock repurchase"),
    ResearchEventType.MERGER_ACQUISITION: ("acquire", "acquisition", "merger", "takeover"),
    ResearchEventType.LEADERSHIP: ("chief executive", "ceo", "cfo", "chairperson", "resigns"),
    ResearchEventType.PRODUCT: ("launches", "unveils", "new product", "new service"),
    ResearchEventType.PARTNERSHIP: ("partnership", "partners", "collaboration", "joint venture"),
    ResearchEventType.FINANCING: ("funding", "bond offering", "debt", "capital raise"),
    ResearchEventType.REGULATORY_LEGAL: (
        "regulator",
        "lawsuit",
        "court",
        "investigation",
        "approval",
    ),
    ResearchEventType.OPERATIONS: ("facility", "production", "layoffs", "restructuring", "recall"),
    ResearchEventType.OTHER: ("announces material event",),
}


def normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = re.sub(r"[^\w\s]", " ", normalized)
    return " ".join(normalized.split())


def canonical_url(value: str) -> str:
    parsed = urlsplit(value)
    query = urlencode(
        sorted(
            (key, item)
            for key, item in parse_qsl(parsed.query, keep_blank_values=True)
            if not key.casefold().startswith("utm_") and key.casefold() not in TRACKING_PARAMETERS
        )
    )
    path = parsed.path.rstrip("/") or "/"
    return urlunsplit((parsed.scheme.casefold(), parsed.netloc.casefold(), path, query, ""))


class ResearchService:
    def __init__(
        self,
        provider: NewsProvider,
        repository_factory: ResearchRepositoryFactory,
        settings: Settings,
    ) -> None:
        self._provider = provider
        self._repository = repository_factory.create()
        self._settings = settings

    @staticmethod
    def _provider_context(context: ExecutionContext) -> ProviderContext:
        return ProviderContext(
            request_id=context.request_id,
            correlation_id=context.correlation_id,
            causation_id=context.causation_id,
            capability_run_id=context.capability_run_id,
        )

    @staticmethod
    def _source(article: NewsArticle) -> ResearchSource:
        published = article.published_at
        timestamp = published or article.metadata.retrieved_at
        provider = article.metadata.provider
        return ResearchSource(
            source_id=f"{provider}:{article.source_id}",
            provider_source_id=article.source_id,
            provider=provider,
            title=article.title,
            url=article.url,
            published_at=published,
            retrieved_at=article.metadata.retrieved_at,
            timestamp=timestamp,
            timestamp_basis=(TimestampBasis.PUBLISHED if published else TimestampBasis.RETRIEVED),
            summary=article.summary,
            license=article.metadata.license.value,
            freshness=article.metadata.freshness.value,
        )

    async def search(self, context: ExecutionContext, payload: NewsSearchInput) -> NewsSearchOutput:
        articles = await self._provider.search(
            self._provider_context(context),
            NewsSearchRequest(
                query=payload.query,
                start=payload.start,
                end=payload.end,
                limit=payload.limit or self._settings.research_default_search_limit,
            ),
        )
        sources = tuple(
            sorted(
                (self._source(article) for article in articles),
                key=lambda item: (item.timestamp, item.provider, item.source_id),
                reverse=True,
            )
        )
        await self._repository.save(sources, ())
        return NewsSearchOutput(query=payload.query, sources=sources)

    async def deduplicate(self, payload: NewsDeduplicateInput) -> NewsDeduplicateOutput:
        ordered = tuple(
            sorted(
                payload.sources,
                key=lambda item: (item.timestamp, item.provider, item.source_id),
            )
        )
        representatives: list[ResearchSource] = []
        key_owner: dict[str, int] = {}
        duplicates: dict[int, list[str]] = {}
        reasons: dict[int, str] = {}
        for source in ordered:
            day = source.published_at.date().isoformat() if source.published_at else "unknown"
            keys = [
                (
                    f"identity:{source.provider}:{source.provider_source_id}",
                    "provider_source",
                ),
                (f"url:{canonical_url(str(source.url))}", "canonical_url"),
                (f"title:{normalize_text(source.title)}:{day}", "title_day"),
            ]
            if source.document_hash:
                keys.insert(2, (f"hash:{source.document_hash}", "document_hash"))
            owner: int | None = None
            reason = "provider_source"
            for key, candidate_reason in keys:
                if key in key_owner:
                    owner = key_owner[key]
                    reason = candidate_reason
                    break
            if owner is None:
                owner = len(representatives)
                representatives.append(source)
                for key, _ in keys:
                    key_owner[key] = owner
            else:
                duplicates.setdefault(owner, []).append(source.source_id)
                reasons.setdefault(owner, reason)
                for key, _ in keys:
                    key_owner[key] = owner
        groups = tuple(
            DuplicateGroup(
                representative_source_id=representatives[index].source_id,
                duplicate_source_ids=tuple(sorted(source_ids)),
                reason=reasons[index],
            )
            for index, source_ids in sorted(duplicates.items())
        )
        return NewsDeduplicateOutput(
            query=payload.query,
            sources=tuple(representatives),
            duplicate_groups=groups,
            input_count=len(payload.sources),
            unique_count=len(representatives),
        )

    @staticmethod
    def _match(text: str, *, strong: bool) -> ResearchEventType | None:
        normalized = normalize_text(text)
        rules = STRONG_PHRASES if strong else RULE_PHRASES
        for event_type, phrases in rules.items():
            if any(phrase in normalized for phrase in phrases):
                return event_type
        return None

    async def extract(
        self, context: ExecutionContext, payload: EventExtractionInput
    ) -> EventExtractionOutput:
        events: list[ResearchEvent] = []
        unmatched: list[str] = []
        failures: list[str] = []
        updated_sources: list[ResearchSource] = []
        fetches = 0
        for source in payload.sources:
            event_type = self._match(source.title, strong=True)
            basis = ConfidenceBasis.STRONG_TITLE
            confidence = 0.95
            excerpt = source.title
            if event_type is None:
                event_type = self._match(source.title, strong=False)
                basis = ConfidenceBasis.TITLE
                confidence = 0.90
            if event_type is None and source.summary:
                event_type = self._match(source.summary, strong=False)
                basis = ConfidenceBasis.SUMMARY
                confidence = 0.85
                excerpt = source.summary
            current_source = source
            if event_type is None and fetches < self._settings.research_document_fetch_limit:
                fetches += 1
                try:
                    document = await self._provider.get_document(
                        self._provider_context(context),
                        NewsDocumentRequest(
                            source_id=source.provider_source_id,
                            provider=source.provider,
                        ),
                    )
                except ProviderError:
                    failures.append(source.source_id)
                else:
                    digest = hashlib.sha256(document.content.encode()).hexdigest()
                    current_source = source.model_copy(update={"document_hash": digest})
                    event_type = self._match(document.content, strong=False)
                    basis = ConfidenceBasis.DOCUMENT
                    confidence = 0.75
                    excerpt = document.content
            updated_sources.append(current_source)
            if event_type is None:
                unmatched.append(source.source_id)
                continue
            event_seed = (
                f"{normalize_text(payload.query)}:{event_type.value}:"
                f"{normalize_text(source.title)}:{source.timestamp.isoformat()}"
            )
            event_id = uuid5(NAMESPACE_URL, f"research-event:{event_seed}")
            claim_id = uuid5(
                NAMESPACE_URL, f"research-claim:{event_id}:{source.provider}:{source.source_id}"
            )
            bounded_excerpt = " ".join(excerpt.split())[
                : self._settings.research_evidence_excerpt_length
            ]
            claim = ResearchClaim(
                claim_id=claim_id,
                event_id=event_id,
                text=source.title,
                source=current_source,
                provider=current_source.provider,
                timestamp=source.timestamp,
                timestamp_basis=source.timestamp_basis,
                confidence=confidence,
                confidence_basis=basis,
                extraction_version=self._settings.research_extraction_version,
                evidence_excerpt=bounded_excerpt,
            )
            events.append(
                ResearchEvent(
                    event_id=event_id,
                    query=payload.query,
                    event_type=event_type,
                    headline=source.title,
                    observed_at=source.timestamp,
                    timestamp_basis=source.timestamp_basis,
                    confidence=confidence,
                    extraction_version=self._settings.research_extraction_version,
                    claims=(claim,),
                    source_ids=(source.source_id,),
                )
            )
        result = EventExtractionOutput(
            query=payload.query,
            events=tuple(sorted(events, key=lambda item: (item.observed_at, str(item.event_id)))),
            sources=tuple(updated_sources),
            unmatched_source_ids=tuple(sorted(unmatched)),
            document_failures=tuple(sorted(failures)),
        )
        await self._repository.save(result.sources, result.events)
        return result

    async def timeline(self, payload: ResearchTimelineInput) -> ResearchTimelineOutput:
        return ResearchTimelineOutput(
            query=payload.query,
            events=tuple(
                sorted(payload.events, key=lambda item: (item.observed_at, str(item.event_id)))
            ),
        )

    async def report(self, payload: ResearchReportInput) -> ResearchReportOutput:
        warnings: list[str] = []
        if payload.unmatched_source_ids:
            warnings.append("Some sources contained no deterministic event rule match.")
        if payload.document_failures:
            warnings.append(
                "Some full documents could not be retrieved; available evidence was retained."
            )
        status = "empty" if not payload.events else "partial" if warnings else "completed"
        return ResearchReportOutput(
            query=payload.query,
            status=status,
            coverage=ResearchCoverage(
                source_count=len(payload.sources),
                duplicate_count=sum(
                    len(group.duplicate_source_ids) for group in payload.duplicate_groups
                ),
                event_count=len(payload.events),
                claim_count=sum(len(event.claims) for event in payload.events),
                unmatched_count=len(payload.unmatched_source_ids),
                document_failure_count=len(payload.document_failures),
            ),
            events=tuple(payload.events),
            sources=tuple(payload.sources),
            duplicate_groups=tuple(payload.duplicate_groups),
            warnings=tuple(warnings),
        )

    async def evidence(self, payload: ResearchEvidenceInput) -> ResearchEvidenceOutput:
        return await self._repository.evidence(payload.event_id)
