from __future__ import annotations

import hmac
from hashlib import sha256
from typing import cast
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, status

from tradesentinel.api.dependencies import ContainerDependency
from tradesentinel.domain.market_shift import (
    EmptyMarketShiftInput,
    MarketShiftAttempt,
    MarketShiftHistoryPage,
    MarketShiftHistoryRequest,
    MarketShiftObservationBatch,
    MarketShiftObservationReceipt,
    MarketShiftReference,
    MarketShiftRequest,
    MarketShiftScheduleResult,
    MarketShiftSnapshot,
    MarketShiftWatchlist,
    MarketShiftWatchlistEntry,
    MarketShiftWatchlistReference,
)
from tradesentinel.platform.contracts import (
    CapabilityExecutionRequest,
    CapabilityResult,
    ExecutionContext,
    WorkflowExecutionRequest,
    WorkflowResult,
)
from tradesentinel.platform.errors import DomainError

router = APIRouter(tags=["market shift"])


def _context(request: Request, *, admin: bool = False) -> ExecutionContext:
    return ExecutionContext(
        request_id=UUID(request.state.request_id),
        principal_id="market-shift-admin" if admin else request.state.principal_id,
        permissions=("market_shift.admin",) if admin else (),
    )


async def _authorize(
    authorization: str | None, request: Request, container: ContainerDependency
) -> ExecutionContext:
    configured = container.settings.market_shift_admin_token_hash
    if configured is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    valid = hmac.compare_digest(
        sha256(supplied.encode()).hexdigest(), configured.get_secret_value().lower()
    )
    if not valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid administrative credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    allowed, retry_after = await container.rate_limiter.allow(
        f"market-shift-admin:{configured.get_secret_value()[:12]}",
        container.settings.market_shift_admin_rate_limit,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Administrative request rate limit exceeded.",
            headers={"Retry-After": str(retry_after)},
        )
    return _context(request, admin=True)


async def _capability(
    name: str,
    payload: object,
    request: Request,
    container: ContainerDependency,
    *,
    context: ExecutionContext | None = None,
) -> dict[str, object]:
    model_payload = payload.model_dump(mode="json")  # type: ignore[attr-defined]
    outcome = await container.pipeline.execute(
        CapabilityExecutionRequest(capability=name, payload=model_payload),
        context or _context(request),
    )
    result = cast(CapabilityResult, outcome.result)
    return cast(dict[str, object], result.data)


@router.post("/api/v1/market-shift", response_model=MarketShiftSnapshot)
async def calculate(
    body: MarketShiftRequest, request: Request, container: ContainerDependency
) -> MarketShiftSnapshot:
    outcome = await container.pipeline.execute(
        WorkflowExecutionRequest(
            workflow="market_shift.request", payload=body.model_dump(mode="json")
        ),
        _context(request),
    )
    result = cast(WorkflowResult, outcome.result)
    if result.status.value == "failed":
        codes = {warning.code for step in result.steps.values() for warning in step.warnings}
        if "MARKET_SHIFT_INPUT_INCOMPLETE" in codes:
            raise DomainError(
                "MARKET_SHIFT_INPUT_INCOMPLETE",
                "A Market Shift score requires current and prior evidence "
                "for all input categories.",
                status_code=422,
            )
        raise DomainError(
            "MARKET_SHIFT_EXECUTION_FAILED",
            "The Market Shift calculation could not be completed.",
            status_code=503,
        )
    return MarketShiftSnapshot.model_validate(result.steps["calculate"].data)


@router.get(
    "/api/v1/market-shift/instruments/{instrument_id}/history",
    response_model=MarketShiftHistoryPage,
)
async def history(
    instrument_id: UUID,
    request: Request,
    container: ContainerDependency,
    limit: int = Query(default=25, ge=1, le=100),
) -> MarketShiftHistoryPage:
    data = await _capability(
        "market_shift.history",
        MarketShiftHistoryRequest(instrument_id=instrument_id, limit=limit),
        request,
        container,
    )
    return MarketShiftHistoryPage.model_validate(data)


@router.get("/api/v1/market-shift/{calculation_id}", response_model=MarketShiftAttempt)
async def read_calculation(
    calculation_id: UUID, request: Request, container: ContainerDependency
) -> MarketShiftAttempt:
    data = await _capability(
        "market_shift.read",
        MarketShiftReference(calculation_id=calculation_id),
        request,
        container,
    )
    return MarketShiftAttempt.model_validate(data)


@router.post(
    "/api/v1/admin/market-shift/observations",
    response_model=MarketShiftObservationReceipt,
    status_code=201,
)
async def ingest(
    body: MarketShiftObservationBatch,
    request: Request,
    container: ContainerDependency,
    authorization: str | None = Header(default=None),
) -> MarketShiftObservationReceipt:
    context = await _authorize(authorization, request, container)
    data = await _capability(
        "market_shift.observations.ingest", body, request, container, context=context
    )
    return MarketShiftObservationReceipt.model_validate(data)


@router.get("/api/v1/admin/market-shift/watchlist", response_model=MarketShiftWatchlist)
async def list_watchlist(
    request: Request,
    container: ContainerDependency,
    authorization: str | None = Header(default=None),
) -> MarketShiftWatchlist:
    context = await _authorize(authorization, request, container)
    data = await _capability(
        "market_shift.watchlist.list",
        EmptyMarketShiftInput(),
        request,
        container,
        context=context,
    )
    return MarketShiftWatchlist.model_validate(data)


@router.post(
    "/api/v1/admin/market-shift/run",
    response_model=MarketShiftScheduleResult,
)
async def run_schedule(
    request: Request,
    container: ContainerDependency,
    authorization: str | None = Header(default=None),
) -> MarketShiftScheduleResult:
    context = await _authorize(authorization, request, container)
    data = await _capability(
        "market_shift.schedule.run",
        EmptyMarketShiftInput(),
        request,
        container,
        context=context,
    )
    return MarketShiftScheduleResult.model_validate(data)


@router.put(
    "/api/v1/admin/market-shift/watchlist/{watchlist_id}",
    response_model=MarketShiftWatchlistEntry,
)
async def save_watchlist(
    watchlist_id: UUID,
    body: MarketShiftWatchlistEntry,
    request: Request,
    container: ContainerDependency,
    authorization: str | None = Header(default=None),
) -> MarketShiftWatchlistEntry:
    context = await _authorize(authorization, request, container)
    normalized = body.model_copy(update={"watchlist_id": watchlist_id})
    data = await _capability(
        "market_shift.watchlist.save", normalized, request, container, context=context
    )
    return MarketShiftWatchlistEntry.model_validate(data)


@router.delete("/api/v1/admin/market-shift/watchlist/{watchlist_id}")
async def remove_watchlist(
    watchlist_id: UUID,
    request: Request,
    container: ContainerDependency,
    authorization: str | None = Header(default=None),
) -> dict[str, bool]:
    context = await _authorize(authorization, request, container)
    data = await _capability(
        "market_shift.watchlist.remove",
        MarketShiftWatchlistReference(watchlist_id=watchlist_id),
        request,
        container,
        context=context,
    )
    return {"removed": bool(data["removed"])}
