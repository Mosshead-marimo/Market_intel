from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from pydantic import BaseModel, JsonValue

from tradesentinel.domain.fundamentals import (
    FundamentalBatchDataInput,
    FundamentalDataInput,
    FundamentalDatasetInput,
    FundamentalGrowthOutput,
    FundamentalPeerComparisonInput,
    FundamentalPeerComparisonOutput,
    FundamentalPeerSelectionInput,
    FundamentalSectionOutput,
    FundamentalSnapshot,
    FundamentalSnapshotInput,
    FundamentalValuationInput,
    FundamentalValuationOutput,
)
from tradesentinel.modules.fundamentals.service import FundamentalAnalysisService
from tradesentinel.platform.capabilities import Capability
from tradesentinel.platform.contracts import (
    CapabilityResult,
    CapabilityWarning,
    ComparisonTable,
    ComponentStatus,
    EventEnvelope,
    ExecutionContext,
    MetricGrid,
    MetricItem,
    ResponseComponent,
    RunMetadata,
    RunStatus,
    TableRow,
)
from tradesentinel.platform.events import EventBus


def _components(output: BaseModel) -> tuple[ResponseComponent, ...]:
    if isinstance(output, FundamentalSnapshot):
        metrics = []
        for section in (output.revenue, output.profit, output.margins, output.roe, output.roce):
            for item in section.metrics:
                if item.latest is not None:
                    metrics.append(
                        MetricItem(label=item.label, value=str(item.latest), detail=item.unit)
                    )
        return (
            MetricGrid(
                id="fundamental-snapshot",
                title="Fundamental snapshot",
                status=_component_status(output.status),
                metrics=tuple(metrics[:12]),
            ),
        )
    if isinstance(output, FundamentalSectionOutput):
        return (
            MetricGrid(
                id=f"fundamental-{output.section}",
                title=output.section.replace("_", " ").title(),
                status=_component_status(output.status),
                metrics=tuple(
                    MetricItem(label=item.label, value=str(item.latest), detail=item.unit)
                    for item in output.metrics
                    if item.latest is not None
                ),
            ),
        )
    if isinstance(output, FundamentalPeerComparisonOutput):
        instruments = (output.target, *output.peers)
        return (
            ComparisonTable(
                id="fundamental-peer-comparison",
                title="Fundamental peer comparison",
                status=_component_status(output.status),
                columns=("Metric", *(item.symbol for item in instruments), "Peer median"),
                rows=tuple(
                    TableRow(
                        cells=(
                            comparison.concept,
                            *(
                                "—" if item.value is None else str(item.value)
                                for item in comparison.values
                            ),
                            "—" if comparison.median is None else str(comparison.median),
                        )
                    )
                    for comparison in output.comparisons
                ),
            ),
        )
    return ()


def _component_status(status: object) -> ComponentStatus:
    return (
        ComponentStatus.EMPTY
        if str(status) == "empty"
        else ComponentStatus.PARTIAL
        if str(status) == "partial"
        else ComponentStatus.READY
    )


def _result(output: BaseModel, started: datetime) -> CapabilityResult:
    completed = datetime.now(UTC)
    raw_status = getattr(output, "status", "completed")
    warnings = tuple(
        CapabilityWarning(code="FUNDAMENTAL_DATA_PARTIAL", message=message)
        for message in getattr(output, "warnings", ())
    )
    return CapabilityResult(
        capability="",
        status=RunStatus.PARTIAL if str(raw_status) == "partial" else RunStatus.COMPLETED,
        data=cast(dict[str, JsonValue], output.model_dump(mode="json")),
        warnings=warnings,
        components=_components(output),
        metadata=RunMetadata(
            started_at=started,
            completed_at=completed,
            data_cutoff=getattr(output, "data_cutoff", None),
        ),
    )


class _FundamentalCapability:
    def __init__(self, service: FundamentalAnalysisService, events: EventBus) -> None:
        self._service = service
        self._events = events

    async def _complete(
        self, name: str, context: ExecutionContext, output: BaseModel, started: datetime
    ) -> CapabilityResult:
        await self._events.publish(
            EventEnvelope(
                name=f"fundamental.{name}.completed",
                producer="fundamentals",
                correlation_id=context.correlation_id,
                causation_id=context.causation_id,
                payload={
                    "status": str(getattr(output, "status", "completed")),
                    "data_cutoff": (
                        value.isoformat()
                        if (value := getattr(output, "data_cutoff", None)) is not None
                        else None
                    ),
                    "capability_run_id": (
                        str(context.capability_run_id)
                        if context.capability_run_id is not None
                        else None
                    ),
                },
            )
        )
        return _result(output, started)


class CollectDataCapability(_FundamentalCapability, Capability[FundamentalDataInput]):
    input_model = FundamentalDataInput

    async def execute(
        self, context: ExecutionContext, payload: FundamentalDataInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        return await self._complete(
            "data.collected", context, await self._service.collect(context, payload), started
        )


class CollectBatchCapability(_FundamentalCapability, Capability[FundamentalBatchDataInput]):
    input_model = FundamentalBatchDataInput

    async def execute(
        self, context: ExecutionContext, payload: FundamentalBatchDataInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        return await self._complete(
            "data.batch_collected",
            context,
            await self._service.collect_batch(context, payload),
            started,
        )


class SelectPeersCapability(_FundamentalCapability, Capability[FundamentalPeerSelectionInput]):
    input_model = FundamentalPeerSelectionInput

    async def execute(
        self, context: ExecutionContext, payload: FundamentalPeerSelectionInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        return await self._complete(
            "peers.selected",
            context,
            await self._service.select_peers(context, payload),
            started,
        )


class _DatasetCapability(_FundamentalCapability):
    input_model = FundamentalDatasetInput

    async def calculate(
        self, name: str, context: ExecutionContext, output: BaseModel, started: datetime
    ) -> CapabilityResult:
        return await self._complete(name, context, output, started)


class RevenueCapability(_DatasetCapability, Capability[FundamentalDatasetInput]):
    async def execute(
        self, context: ExecutionContext, payload: FundamentalDatasetInput
    ) -> CapabilityResult:
        return await self.calculate(
            "revenue", context, self._service.revenue(payload.dataset), datetime.now(UTC)
        )


class ProfitCapability(_DatasetCapability, Capability[FundamentalDatasetInput]):
    async def execute(
        self, context: ExecutionContext, payload: FundamentalDatasetInput
    ) -> CapabilityResult:
        return await self.calculate(
            "profit", context, self._service.profit(payload.dataset), datetime.now(UTC)
        )


class CashFlowCapability(_DatasetCapability, Capability[FundamentalDatasetInput]):
    async def execute(
        self, context: ExecutionContext, payload: FundamentalDatasetInput
    ) -> CapabilityResult:
        return await self.calculate(
            "cash_flow", context, self._service.cash_flow(payload.dataset), datetime.now(UTC)
        )


class DebtCapability(_DatasetCapability, Capability[FundamentalDatasetInput]):
    async def execute(
        self, context: ExecutionContext, payload: FundamentalDatasetInput
    ) -> CapabilityResult:
        return await self.calculate(
            "debt", context, self._service.debt(payload.dataset), datetime.now(UTC)
        )


class MarginsCapability(_DatasetCapability, Capability[FundamentalDatasetInput]):
    async def execute(
        self, context: ExecutionContext, payload: FundamentalDatasetInput
    ) -> CapabilityResult:
        return await self.calculate(
            "margins", context, self._service.margins(payload.dataset), datetime.now(UTC)
        )


class RoeCapability(_DatasetCapability, Capability[FundamentalDatasetInput]):
    async def execute(
        self, context: ExecutionContext, payload: FundamentalDatasetInput
    ) -> CapabilityResult:
        return await self.calculate(
            "roe", context, self._service.roe(payload.dataset), datetime.now(UTC)
        )


class RoceCapability(_DatasetCapability, Capability[FundamentalDatasetInput]):
    async def execute(
        self, context: ExecutionContext, payload: FundamentalDatasetInput
    ) -> CapabilityResult:
        return await self.calculate(
            "roce", context, self._service.roce(payload.dataset), datetime.now(UTC)
        )


class GrowthCapability(_DatasetCapability, Capability[FundamentalDatasetInput]):
    async def execute(
        self, context: ExecutionContext, payload: FundamentalDatasetInput
    ) -> CapabilityResult:
        output: FundamentalGrowthOutput = self._service.growth(payload.dataset)
        return await self.calculate("growth", context, output, datetime.now(UTC))


class ValuationCapability(_FundamentalCapability, Capability[FundamentalValuationInput]):
    input_model = FundamentalValuationInput

    async def execute(
        self, context: ExecutionContext, payload: FundamentalValuationInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        output: FundamentalValuationOutput = self._service.valuation(payload)
        return await self._complete("valuation", context, output, started)


class SnapshotCapability(_FundamentalCapability, Capability[FundamentalSnapshotInput]):
    input_model = FundamentalSnapshotInput

    async def execute(
        self, context: ExecutionContext, payload: FundamentalSnapshotInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        return await self._complete("snapshot", context, self._service.snapshot(payload), started)


class PeerComparisonCapability(_FundamentalCapability, Capability[FundamentalPeerComparisonInput]):
    input_model = FundamentalPeerComparisonInput

    async def execute(
        self, context: ExecutionContext, payload: FundamentalPeerComparisonInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        return await self._complete(
            "peer_comparison", context, self._service.peer_comparison(payload), started
        )
