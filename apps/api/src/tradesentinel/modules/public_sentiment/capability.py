from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from pydantic import BaseModel, JsonValue

from tradesentinel.domain.sentiment import (
    AggregateSentimentInput,
    AggregateSentimentOutput,
    CollectDiscussionsInput,
    CompanyDetectionInput,
    NarrativeExtractionInput,
    ShiftDetectionInput,
    SourceWeightInput,
    SpamRemovalInput,
    TrendDetectionInput,
)
from tradesentinel.modules.public_sentiment.repository import SentimentPersistenceService
from tradesentinel.modules.public_sentiment.service import PublicSentimentService
from tradesentinel.platform.capabilities import Capability
from tradesentinel.platform.contracts import (
    CapabilityResult,
    CapabilityWarning,
    ChartPoint,
    ChartSeries,
    ComparisonTable,
    ComponentStatus,
    EventEnvelope,
    ExecutionContext,
    MetricGrid,
    MetricItem,
    ResponseComponent,
    RunMetadata,
    RunStatus,
    SentimentChart,
    TableRow,
)
from tradesentinel.platform.events import EventBus


def _result(
    output: BaseModel, started: datetime, components: tuple[ResponseComponent, ...] = ()
) -> CapabilityResult:
    completed = datetime.now(UTC)
    status_value = getattr(output, "status", "completed")
    partial = str(status_value) in {"partial", "insufficient"}
    empty = str(status_value) == "empty"
    warnings = tuple(
        CapabilityWarning(code="SENTIMENT_DATA_PARTIAL", message=message)
        for message in getattr(output, "warnings", ())
    )
    return CapabilityResult(
        capability="",
        status=RunStatus.PARTIAL if partial else RunStatus.COMPLETED,
        data=cast(dict[str, JsonValue], output.model_dump(mode="json")),
        warnings=warnings,
        components=components,
        metadata=RunMetadata(
            started_at=started,
            completed_at=completed,
            duration_ms=max(0, int((completed - started).total_seconds() * 1000)),
        ),
        summary="No qualifying public discussions were available." if empty else None,
    )


class _Base:
    def __init__(
        self,
        service: PublicSentimentService,
        persistence: SentimentPersistenceService,
        events: EventBus,
    ) -> None:
        self._service = service
        self._persistence = persistence
        self._events = events

    async def _emit(self, name: str, context: ExecutionContext, **payload: JsonValue) -> None:
        await self._events.publish(
            EventEnvelope(
                name=name,
                producer="public_sentiment",
                correlation_id=context.correlation_id,
                causation_id=context.causation_id,
                payload=payload,
            )
        )


class CollectDiscussionsCapability(_Base, Capability[CollectDiscussionsInput]):
    input_model = CollectDiscussionsInput

    async def execute(
        self, context: ExecutionContext, payload: CollectDiscussionsInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        output = await self._service.collect(context, payload)
        await self._persistence.discussions(output.discussions)
        await self._emit("sentiment.discussions.collected", context, count=len(output.discussions))
        return _result(output, started)


class RemoveSpamCapability(_Base, Capability[SpamRemovalInput]):
    input_model = SpamRemovalInput

    async def execute(
        self, context: ExecutionContext, payload: SpamRemovalInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        output = self._service.remove_spam(payload)
        await self._persistence.spam(output)
        await self._emit(
            "sentiment.spam.filtered",
            context,
            retained=len(output.retained),
            removed=len(output.decisions) - len(output.retained),
        )
        return _result(output, started)


class DetectCompaniesCapability(_Base, Capability[CompanyDetectionInput]):
    input_model = CompanyDetectionInput

    async def execute(
        self, context: ExecutionContext, payload: CompanyDetectionInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        output = self._service.detect_companies(payload)
        await self._persistence.detection(output)
        await self._emit(
            "sentiment.companies.detected",
            context,
            relevant=len(output.relevant),
            co_mentions=len(output.co_mentions),
        )
        return _result(output, started)


class WeightSourcesCapability(_Base, Capability[SourceWeightInput]):
    input_model = SourceWeightInput

    async def execute(
        self, context: ExecutionContext, payload: SourceWeightInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        output = self._service.weight_sources(payload)
        await self._persistence.weights(output)
        await self._emit("sentiment.sources.weighted", context, count=len(output.observations))
        return _result(output, started)


class AggregateSentimentCapability(_Base, Capability[AggregateSentimentInput]):
    input_model = AggregateSentimentInput

    async def execute(
        self, context: ExecutionContext, payload: AggregateSentimentInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        snapshot = self._service.aggregate(payload)
        await self._persistence.snapshot(snapshot)
        component = MetricGrid(
            id="sentiment-snapshot",
            title="Public sentiment snapshot",
            status=ComponentStatus.EMPTY
            if snapshot.status == "empty"
            else ComponentStatus.PARTIAL
            if snapshot.status == "partial"
            else ComponentStatus.READY,
            metrics=(
                MetricItem(
                    label="Score",
                    value="unavailable"
                    if snapshot.current.mean_score is None
                    else str(snapshot.current.mean_score),
                ),
                MetricItem(label="Mentions", value=str(snapshot.current.mention_count)),
                MetricItem(
                    label="Confidence",
                    value="unavailable"
                    if snapshot.confidence is None
                    else str(snapshot.confidence),
                ),
            ),
        )
        await self._emit(
            "sentiment.snapshot.completed",
            context,
            status=snapshot.status.value,
            mentions=snapshot.current.mention_count,
        )
        return _result(AggregateSentimentOutput(snapshot=snapshot), started, (component,))


class ExtractNarrativesCapability(_Base, Capability[NarrativeExtractionInput]):
    input_model = NarrativeExtractionInput

    async def execute(
        self, context: ExecutionContext, payload: NarrativeExtractionInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        output = self._service.narratives(payload)
        await self._persistence.narratives(output)
        await self._emit("sentiment.narratives.extracted", context, count=len(output.narratives))
        table = ComparisonTable(
            id="sentiment-narratives",
            title="Public narratives",
            status=ComponentStatus.EMPTY if not output.narratives else ComponentStatus.READY,
            columns=("Narrative", "Sentiment", "Weighted share", "Confidence"),
            rows=tuple(
                TableRow(
                    cells=(
                        item.topic,
                        item.sentiment.value,
                        str(item.weighted_share),
                        str(item.confidence),
                    )
                )
                for item in output.narratives
            ),
        )
        return _result(output, started, (table,))


class DetectTrendCapability(_Base, Capability[TrendDetectionInput]):
    input_model = TrendDetectionInput

    async def execute(
        self, context: ExecutionContext, payload: TrendDetectionInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        output = self._service.trend(payload)
        await self._persistence.trend(output)
        chart = SentimentChart(
            id="sentiment-trend",
            title="Observed sentiment trend",
            status=ComponentStatus.PARTIAL
            if output.status == "insufficient"
            else ComponentStatus.READY,
            series=(
                ChartSeries(
                    name="Sentiment",
                    points=tuple(
                        ChartPoint(timestamp=item.day, value=float(item.mean_score))
                        for item in output.buckets
                        if item.mean_score is not None
                    ),
                ),
            ),
        )
        await self._emit("sentiment.trend.detected", context, direction=output.direction)
        return _result(output, started, (chart,))


class DetectShiftCapability(_Base, Capability[ShiftDetectionInput]):
    input_model = ShiftDetectionInput

    async def execute(
        self, context: ExecutionContext, payload: ShiftDetectionInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        output = self._service.shift(payload)
        await self._persistence.shift(output)
        await self._emit("sentiment.shift.detected", context, status=output.status.value)
        component = MetricGrid(
            id="sentiment-shift",
            title="Observed sentiment shift",
            status=ComponentStatus.PARTIAL if output.shift_score is None else ComponentStatus.READY,
            metrics=(
                MetricItem(
                    label="Shift score",
                    value="unavailable" if output.shift_score is None else str(output.shift_score),
                    detail="descriptive, not predictive",
                ),
            ),
        )
        return _result(output, started, (component,))
