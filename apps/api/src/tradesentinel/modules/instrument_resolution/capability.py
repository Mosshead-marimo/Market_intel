from __future__ import annotations

from datetime import UTC, datetime

from tradesentinel.domain.instruments import (
    InstrumentAutocompleteInput,
    InstrumentAutocompleteOutput,
    InstrumentCatalogInput,
    InstrumentCatalogOutput,
    InstrumentMatch,
    InstrumentResolveBatchInput,
    InstrumentResolveBatchOutput,
    InstrumentResolveInput,
    InstrumentResolveOutput,
    InstrumentSearchInput,
    InstrumentSearchOutput,
)
from tradesentinel.modules.instrument_resolution.service import InstrumentResolutionService
from tradesentinel.platform.capabilities import Capability
from tradesentinel.platform.contracts import (
    CapabilityResult,
    CapabilityWarning,
    ComparisonTable,
    ComponentStatus,
    ExecutionContext,
    RunMetadata,
    RunStatus,
    SummaryCard,
    TableRow,
)


def _table(matches: tuple[InstrumentMatch, ...], *, status: ComponentStatus) -> ComparisonTable:
    return ComparisonTable(
        id="instrument-matches",
        title="Instrument matches",
        status=status,
        columns=("Symbol", "Company", "Exchange", "Asset type", "Confidence"),
        rows=tuple(
            TableRow(
                cells=(
                    match.instrument.symbol,
                    match.instrument.name,
                    match.instrument.exchange,
                    match.instrument.asset_type.value,
                    f"{match.confidence:.2f}",
                )
            )
            for match in matches
        ),
    )


def _result(
    output: InstrumentSearchOutput | InstrumentAutocompleteOutput | InstrumentResolveOutput,
    started: datetime,
) -> CapabilityResult:
    completed = datetime.now(UTC)
    if isinstance(output, InstrumentResolveOutput):
        matches = (output.match,) if output.match else output.candidates
        matches = tuple(match for match in matches if match is not None)
        ambiguous = output.status == "ambiguous"
        empty = output.status == "not_found"
    else:
        matches = output.matches
        ambiguous = False
        empty = not matches
    warnings: tuple[CapabilityWarning, ...] = ()
    if ambiguous:
        warnings = (
            CapabilityWarning(
                code="INSTRUMENT_AMBIGUOUS",
                message="Multiple listings match; provide an exchange to resolve one instrument.",
            ),
        )
    elif empty:
        warnings = (
            CapabilityWarning(
                code="INSTRUMENT_NOT_FOUND",
                message="No catalog instrument matched the query.",
            ),
        )
    component_status = (
        ComponentStatus.PARTIAL
        if ambiguous
        else ComponentStatus.EMPTY
        if empty
        else ComponentStatus.READY
    )
    components = (
        _table(matches, status=component_status),
        SummaryCard(
            id="catalog-origin",
            heading="Built-in instrument catalog",
            body="Results use the representative TradeSentinel seed catalog.",
            status=component_status,
        ),
    )
    return CapabilityResult(
        capability="",
        status=RunStatus.PARTIAL if ambiguous else RunStatus.COMPLETED,
        data=output.model_dump(mode="json"),
        summary=(
            "Instrument resolution requires an exchange choice."
            if ambiguous
            else "No matching instrument was found."
            if empty
            else f"Found {len(matches)} instrument match{'es' if len(matches) != 1 else ''}."
        ),
        warnings=warnings,
        components=components,
        metadata=RunMetadata(
            started_at=started,
            completed_at=completed,
            duration_ms=max(0, int((completed - started).total_seconds() * 1_000)),
            freshness="unknown",
        ),
    )


class ResolveCapability(Capability[InstrumentResolveInput]):
    input_model = InstrumentResolveInput

    def __init__(self, service: InstrumentResolutionService) -> None:
        self._service = service

    async def execute(
        self, context: ExecutionContext, payload: InstrumentResolveInput
    ) -> CapabilityResult:
        del context
        started = datetime.now(UTC)
        return _result(await self._service.resolve(payload), started)


class SearchCapability(Capability[InstrumentSearchInput]):
    input_model = InstrumentSearchInput

    def __init__(self, service: InstrumentResolutionService) -> None:
        self._service = service

    async def execute(
        self, context: ExecutionContext, payload: InstrumentSearchInput
    ) -> CapabilityResult:
        del context
        started = datetime.now(UTC)
        return _result(await self._service.search(payload), started)


class AutocompleteCapability(Capability[InstrumentAutocompleteInput]):
    input_model = InstrumentAutocompleteInput

    def __init__(self, service: InstrumentResolutionService) -> None:
        self._service = service

    async def execute(
        self, context: ExecutionContext, payload: InstrumentAutocompleteInput
    ) -> CapabilityResult:
        del context
        started = datetime.now(UTC)
        return _result(await self._service.autocomplete(payload), started)


class CatalogCapability(Capability[InstrumentCatalogInput]):
    input_model = InstrumentCatalogInput

    def __init__(self, service: InstrumentResolutionService) -> None:
        self._service = service

    async def execute(
        self, context: ExecutionContext, payload: InstrumentCatalogInput
    ) -> CapabilityResult:
        del context, payload
        started = datetime.now(UTC)
        output: InstrumentCatalogOutput = await self._service.catalog()
        completed = datetime.now(UTC)
        return CapabilityResult(
            capability="",
            status=RunStatus.COMPLETED,
            data=output.model_dump(mode="json"),
            summary=f"Loaded {len(output.instruments)} active catalog instruments.",
            metadata=RunMetadata(
                started_at=started,
                completed_at=completed,
                duration_ms=max(0, int((completed - started).total_seconds() * 1_000)),
                freshness="unknown",
            ),
        )


class ResolveBatchCapability(Capability[InstrumentResolveBatchInput]):
    input_model = InstrumentResolveBatchInput

    def __init__(self, service: InstrumentResolutionService) -> None:
        self._service = service

    async def execute(
        self, context: ExecutionContext, payload: InstrumentResolveBatchInput
    ) -> CapabilityResult:
        del context
        started = datetime.now(UTC)
        output: InstrumentResolveBatchOutput = await self._service.resolve_batch(payload)
        completed = datetime.now(UTC)
        warnings = tuple(
            CapabilityWarning(
                code="INSTRUMENT_BATCH_UNRESOLVED",
                message=f"Instrument query '{query}' was not resolved unambiguously.",
            )
            for query in output.unresolved_queries
        )
        return CapabilityResult(
            capability="",
            status=RunStatus.PARTIAL if warnings else RunStatus.COMPLETED,
            data=output.model_dump(mode="json"),
            warnings=warnings,
            metadata=RunMetadata(started_at=started, completed_at=completed),
        )
