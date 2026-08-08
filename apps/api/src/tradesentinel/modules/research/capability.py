from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from pydantic import BaseModel, JsonValue

from tradesentinel.domain.research import (
    EventExtractionInput,
    EventExtractionOutput,
    NewsDeduplicateInput,
    NewsSearchInput,
    ResearchEvidenceInput,
    ResearchReportInput,
    ResearchReportOutput,
    ResearchSource,
    ResearchTimelineInput,
    ResearchTimelineOutput,
)
from tradesentinel.modules.research.service import ResearchService
from tradesentinel.platform.capabilities import Capability
from tradesentinel.platform.contracts import (
    CapabilityResult,
    CapabilityWarning,
    ComponentStatus,
    EventEnvelope,
    EvidenceSource,
    ExecutionContext,
    NewsTimeline,
    ResponseComponent,
    RunMetadata,
    RunStatus,
    SourceList,
    TimelineItem,
)
from tradesentinel.platform.events import EventBus


def _evidence(source: ResearchSource) -> EvidenceSource:
    return EvidenceSource(
        source_id=source.source_id,
        provider=source.provider,
        title=source.title,
        url=source.url,
        published_at=source.published_at,
        retrieved_at=source.retrieved_at,
        source_type="news",
    )


def _result(
    output: BaseModel,
    started: datetime,
    *,
    sources: tuple[ResearchSource, ...] = (),
    events: EventExtractionOutput | ResearchTimelineOutput | ResearchReportOutput | None = None,
    partial: bool = False,
) -> CapabilityResult:
    completed = datetime.now(UTC)
    evidence = tuple(_evidence(source) for source in sources)
    warnings: list[CapabilityWarning] = []
    if isinstance(events, EventExtractionOutput) and events.document_failures:
        warnings.append(
            CapabilityWarning(
                code="RESEARCH_DOCUMENTS_PARTIAL",
                message=(
                    "Some full documents could not be retrieved; available evidence was retained."
                ),
                retryable=True,
                details={"source_ids": list(events.document_failures)},
            )
        )
    if isinstance(events, ResearchReportOutput):
        warnings.extend(
            CapabilityWarning(code="RESEARCH_EVIDENCE_PARTIAL", message=message)
            for message in events.warnings
        )
        partial = events.status == "partial"
    timeline_events = events.events if events is not None else ()
    component_status = ComponentStatus.PARTIAL
    if not partial:
        component_status = ComponentStatus.EMPTY if not timeline_events else ComponentStatus.READY
    components: list[ResponseComponent] = []
    if events is not None:
        components.append(
            NewsTimeline(
                id="research-timeline",
                title="Research event timeline",
                status=component_status,
                source_ids=tuple(source.source_id for source in sources),
                items=tuple(
                    TimelineItem(
                        occurred_at=event.observed_at,
                        headline=event.headline,
                        description=event.event_type.value,
                        source_id=event.source_ids[0],
                    )
                    for event in timeline_events
                ),
            )
        )
    if evidence:
        components.append(
            SourceList(
                id="research-sources",
                title="Research sources",
                status=component_status,
                source_ids=tuple(source.source_id for source in evidence),
                sources=evidence,
            )
        )
    return CapabilityResult(
        capability="",
        status=RunStatus.PARTIAL if partial else RunStatus.COMPLETED,
        data=cast(dict[str, JsonValue], output.model_dump(mode="json")),
        sources=evidence,
        warnings=tuple(warnings),
        components=tuple(components),
        metadata=RunMetadata(started_at=started, completed_at=completed),
    )


class _ResearchCapability:
    def __init__(self, service: ResearchService, events: EventBus) -> None:
        self._service = service
        self._events = events

    async def _emit(self, name: str, context: ExecutionContext, **payload: JsonValue) -> None:
        await self._events.publish(
            EventEnvelope(
                name=name,
                producer="research",
                correlation_id=context.correlation_id,
                causation_id=context.causation_id,
                payload=payload,
            )
        )


class SearchNewsCapability(_ResearchCapability, Capability[NewsSearchInput]):
    input_model = NewsSearchInput

    async def execute(
        self, context: ExecutionContext, payload: NewsSearchInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        output = await self._service.search(context, payload)
        await self._emit(
            "research.news.search.completed", context, source_count=len(output.sources)
        )
        return _result(output, started, sources=output.sources)


class DeduplicateCapability(_ResearchCapability, Capability[NewsDeduplicateInput]):
    input_model = NewsDeduplicateInput

    async def execute(
        self, context: ExecutionContext, payload: NewsDeduplicateInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        output = await self._service.deduplicate(payload)
        await self._emit(
            "research.news.deduplicated",
            context,
            duplicate_count=output.input_count - output.unique_count,
        )
        return _result(output, started, sources=output.sources)


class ExtractEventsCapability(_ResearchCapability, Capability[EventExtractionInput]):
    input_model = EventExtractionInput

    async def execute(
        self, context: ExecutionContext, payload: EventExtractionInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        output = await self._service.extract(context, payload)
        await self._emit("research.events.extracted", context, event_count=len(output.events))
        if output.events:
            await self._emit("research.events.persisted", context, event_count=len(output.events))
        return _result(
            output,
            started,
            sources=output.sources,
            events=output,
            partial=bool(output.document_failures),
        )


class TimelineCapability(_ResearchCapability, Capability[ResearchTimelineInput]):
    input_model = ResearchTimelineInput

    async def execute(
        self, context: ExecutionContext, payload: ResearchTimelineInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        output = await self._service.timeline(payload)
        await self._emit("research.timeline.completed", context, event_count=len(output.events))
        sources = tuple(claim.source for event in output.events for claim in event.claims)
        return _result(output, started, sources=sources, events=output)


class ReportCapability(_ResearchCapability, Capability[ResearchReportInput]):
    input_model = ResearchReportInput

    async def execute(
        self, context: ExecutionContext, payload: ResearchReportInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        output = await self._service.report(payload)
        await self._emit("research.report.completed", context, status=output.status)
        return _result(output, started, sources=output.sources, events=output)


class EvidenceCapability(_ResearchCapability, Capability[ResearchEvidenceInput]):
    input_model = ResearchEvidenceInput

    async def execute(
        self, context: ExecutionContext, payload: ResearchEvidenceInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        output = await self._service.evidence(payload)
        await self._emit("research.evidence.loaded", context, event_id=str(payload.event_id))
        timeline = ResearchTimelineOutput(query=output.event.query, events=(output.event,))
        return _result(output, started, sources=output.sources, events=timeline)
