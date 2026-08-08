from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request

from tradesentinel.api.dependencies import ContainerDependency
from tradesentinel.domain.instruments import (
    AssetType,
    InstrumentAutocompleteInput,
    InstrumentAutocompleteOutput,
    InstrumentResolveInput,
    InstrumentResolveOutput,
    InstrumentSearchInput,
    InstrumentSearchOutput,
)
from tradesentinel.platform.contracts import CapabilityExecutionRequest, ExecutionContext

router = APIRouter(prefix="/api/v1/instruments", tags=["instruments"])


async def _execute[
    OutputT: (InstrumentSearchOutput, InstrumentAutocompleteOutput, InstrumentResolveOutput)
](
    capability: str,
    payload: dict[str, object],
    output_type: type[OutputT],
    request: Request,
    container: ContainerDependency,
) -> OutputT:
    outcome = await container.pipeline.execute(
        CapabilityExecutionRequest(capability=capability, payload=payload),
        ExecutionContext(
            request_id=UUID(request.state.request_id),
            principal_id=request.state.principal_id,
        ),
    )
    return output_type.model_validate(outcome.result.model_dump()["data"])


@router.get("/search", response_model=InstrumentSearchOutput)
async def search_instruments(
    request: Request,
    container: ContainerDependency,
    q: str,
    exchange: str | None = None,
    asset_type: AssetType | None = None,
    limit: int = 20,
) -> InstrumentSearchOutput:
    payload = InstrumentSearchInput(
        query=q, exchange=exchange, asset_type=asset_type, limit=limit
    ).model_dump(mode="json")
    return await _execute("instrument.search", payload, InstrumentSearchOutput, request, container)


@router.get("/autocomplete", response_model=InstrumentAutocompleteOutput)
async def autocomplete_instruments(
    request: Request,
    container: ContainerDependency,
    q: str,
    exchange: str | None = None,
    asset_type: AssetType | None = None,
    limit: int = 10,
) -> InstrumentAutocompleteOutput:
    payload = InstrumentAutocompleteInput(
        query=q, exchange=exchange, asset_type=asset_type, limit=limit
    ).model_dump(mode="json")
    return await _execute(
        "instrument.autocomplete", payload, InstrumentAutocompleteOutput, request, container
    )


@router.get("/resolve", response_model=InstrumentResolveOutput)
async def resolve_instrument(
    request: Request,
    container: ContainerDependency,
    q: str,
    exchange: str | None = None,
    asset_type: AssetType | None = None,
) -> InstrumentResolveOutput:
    payload = InstrumentResolveInput(query=q, exchange=exchange, asset_type=asset_type).model_dump(
        mode="json"
    )
    return await _execute(
        "instrument.resolve", payload, InstrumentResolveOutput, request, container
    )
