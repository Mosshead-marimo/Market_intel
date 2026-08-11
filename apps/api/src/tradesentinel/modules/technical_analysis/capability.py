from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

from pydantic import BaseModel, JsonValue

from tradesentinel.domain.technical import (
    TechnicalCalculationInput,
    TechnicalSnapshot,
    TechnicalWindowInput,
)
from tradesentinel.modules.technical_analysis.service import TechnicalAnalysisService
from tradesentinel.platform.capabilities import Capability
from tradesentinel.platform.contracts import (
    CapabilityResult,
    CapabilityWarning,
    ChartPoint,
    ChartSeries,
    ComponentStatus,
    EventEnvelope,
    ExecutionContext,
    MetricGrid,
    MetricItem,
    PriceChart,
    ResponseComponent,
    RunMetadata,
    RunStatus,
)
from tradesentinel.platform.events import EventBus


def _components(output: BaseModel) -> tuple[ResponseComponent, ...]:
    if isinstance(output, TechnicalSnapshot):
        metrics: list[MetricItem] = []
        if output.rsi is not None:
            metrics.append(MetricItem(label="RSI", value=str(output.rsi.series.latest)))
        if output.macd is not None:
            metrics.append(
                MetricItem(label="MACD histogram", value=str(output.macd.latest.histogram))
            )
        if output.trend is not None:
            metrics.append(
                MetricItem(
                    label="Trend",
                    value=output.trend.direction,
                    detail=output.trend.strength,
                )
            )
        if output.volatility is not None:
            metrics.append(
                MetricItem(
                    label="Volatility",
                    value=output.volatility.regime,
                    detail=str(output.volatility.annualized_volatility),
                )
            )
        status = (
            ComponentStatus.EMPTY
            if output.status == "empty"
            else ComponentStatus.PARTIAL
            if output.status == "partial"
            else ComponentStatus.READY
        )
        components: list[ResponseComponent] = [
            MetricGrid(
                id="technical-snapshot",
                title="Technical snapshot",
                status=status,
                metrics=tuple(metrics),
            )
        ]
        series: list[ChartSeries] = []
        if output.ema is not None:
            series.append(
                ChartSeries(
                    name=f"EMA {output.ema.series.period}",
                    points=tuple(
                        ChartPoint(timestamp=item.timestamp, value=float(item.value))
                        for item in output.ema.series.points
                    ),
                )
            )
        if output.sma is not None:
            series.append(
                ChartSeries(
                    name=f"SMA {output.sma.series.period}",
                    points=tuple(
                        ChartPoint(timestamp=item.timestamp, value=float(item.value))
                        for item in output.sma.series.points
                    ),
                )
            )
        if series:
            components.append(
                PriceChart(
                    id="technical-moving-averages",
                    title="Adjusted moving averages",
                    status=status,
                    series=tuple(series),
                )
            )
        return tuple(components)
    return ()


def _result(output: BaseModel, started: datetime) -> CapabilityResult:
    completed = datetime.now(UTC)
    partial = isinstance(output, TechnicalSnapshot) and output.status != "completed"
    warnings = (
        tuple(
            CapabilityWarning(code="TECHNICAL_INDICATOR_UNAVAILABLE", message=message)
            for message in output.warnings
        )
        if isinstance(output, TechnicalSnapshot)
        else ()
    )
    return CapabilityResult(
        capability="",
        status=RunStatus.PARTIAL if partial else RunStatus.COMPLETED,
        data=cast(dict[str, JsonValue], output.model_dump(mode="json")),
        warnings=warnings,
        components=_components(output),
        metadata=RunMetadata(
            started_at=started,
            completed_at=completed,
            data_cutoff=output.data_cutoff if isinstance(output, TechnicalSnapshot) else None,
        ),
    )


class _TechnicalCapability:
    def __init__(self, service: TechnicalAnalysisService, events: EventBus) -> None:
        self._service = service
        self._events = events

    async def _complete(
        self, name: str, context: ExecutionContext, output: BaseModel, started: datetime
    ) -> CapabilityResult:
        serialized = output.model_dump(mode="json")
        count = 0
        if isinstance(output, TechnicalSnapshot):
            count = output.observation_count
        elif hasattr(output, "points"):
            count = len(output.points)
        elif hasattr(output, "series"):
            count = len(output.series.points)
        periods = {
            key: value
            for key, value in serialized.items()
            if key == "period" or key.endswith("_period")
        }
        event_payload: dict[str, JsonValue] = {
            "observation_count": count,
            "status": serialized.get("status", "completed"),
            "periods": periods,
            "data_cutoff": serialized.get("data_cutoff"),
            "capability_run_id": (
                str(context.capability_run_id) if context.capability_run_id is not None else None
            ),
        }
        await self._events.publish(
            EventEnvelope(
                name=f"technical.{name}.completed",
                producer="technical_analysis",
                correlation_id=context.correlation_id,
                causation_id=context.causation_id,
                payload=event_payload,
            )
        )
        return _result(output, started)


class WindowCapability(_TechnicalCapability, Capability[TechnicalWindowInput]):
    input_model = TechnicalWindowInput

    async def execute(
        self, context: ExecutionContext, payload: TechnicalWindowInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        output = self._service.window(payload)
        return await self._complete("window", context, output, started)


class RsiCapability(_TechnicalCapability, Capability[TechnicalCalculationInput]):
    input_model = TechnicalCalculationInput

    async def execute(
        self, context: ExecutionContext, payload: TechnicalCalculationInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        return await self._complete("rsi", context, self._service.rsi(payload), started)


class MacdCapability(_TechnicalCapability, Capability[TechnicalCalculationInput]):
    input_model = TechnicalCalculationInput

    async def execute(
        self, context: ExecutionContext, payload: TechnicalCalculationInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        return await self._complete("macd", context, self._service.macd(payload), started)


class EmaCapability(_TechnicalCapability, Capability[TechnicalCalculationInput]):
    input_model = TechnicalCalculationInput

    async def execute(
        self, context: ExecutionContext, payload: TechnicalCalculationInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        return await self._complete("ema", context, self._service.ema(payload), started)


class SmaCapability(_TechnicalCapability, Capability[TechnicalCalculationInput]):
    input_model = TechnicalCalculationInput

    async def execute(
        self, context: ExecutionContext, payload: TechnicalCalculationInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        return await self._complete("sma", context, self._service.sma(payload), started)


class AtrCapability(_TechnicalCapability, Capability[TechnicalCalculationInput]):
    input_model = TechnicalCalculationInput

    async def execute(
        self, context: ExecutionContext, payload: TechnicalCalculationInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        return await self._complete("atr", context, self._service.atr(payload), started)


class AdxCapability(_TechnicalCapability, Capability[TechnicalCalculationInput]):
    input_model = TechnicalCalculationInput

    async def execute(
        self, context: ExecutionContext, payload: TechnicalCalculationInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        return await self._complete("adx", context, self._service.adx(payload), started)


class SupportCapability(_TechnicalCapability, Capability[TechnicalCalculationInput]):
    input_model = TechnicalCalculationInput

    async def execute(
        self, context: ExecutionContext, payload: TechnicalCalculationInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        return await self._complete("support", context, self._service.support(payload), started)


class ResistanceCapability(_TechnicalCapability, Capability[TechnicalCalculationInput]):
    input_model = TechnicalCalculationInput

    async def execute(
        self, context: ExecutionContext, payload: TechnicalCalculationInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        return await self._complete(
            "resistance", context, self._service.resistance(payload), started
        )


class TrendCapability(_TechnicalCapability, Capability[TechnicalCalculationInput]):
    input_model = TechnicalCalculationInput

    async def execute(
        self, context: ExecutionContext, payload: TechnicalCalculationInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        return await self._complete("trend", context, self._service.trend(payload), started)


class MomentumCapability(_TechnicalCapability, Capability[TechnicalCalculationInput]):
    input_model = TechnicalCalculationInput

    async def execute(
        self, context: ExecutionContext, payload: TechnicalCalculationInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        return await self._complete("momentum", context, self._service.momentum(payload), started)


class VolatilityCapability(_TechnicalCapability, Capability[TechnicalCalculationInput]):
    input_model = TechnicalCalculationInput

    async def execute(
        self, context: ExecutionContext, payload: TechnicalCalculationInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        return await self._complete(
            "volatility", context, self._service.volatility(payload), started
        )


class SnapshotCapability(_TechnicalCapability, Capability[TechnicalCalculationInput]):
    input_model = TechnicalCalculationInput

    async def execute(
        self, context: ExecutionContext, payload: TechnicalCalculationInput
    ) -> CapabilityResult:
        started = datetime.now(UTC)
        return await self._complete("snapshot", context, self._service.snapshot(payload), started)
