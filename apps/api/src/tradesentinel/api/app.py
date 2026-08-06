from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.responses import Response

from tradesentinel import __version__
from tradesentinel.api.routes import router
from tradesentinel.platform.config import Settings, get_settings
from tradesentinel.platform.container import build_container
from tradesentinel.platform.contracts import ApiErrorDetail, ApiErrorResponse
from tradesentinel.platform.errors import DomainError
from tradesentinel.platform.logging import configure_logging, request_id_var


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings or get_settings()
    configure_logging(resolved.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = build_container(resolved)
        app.state.container = container
        yield
        await container.close()

    app = FastAPI(
        title="TradeSentinel API",
        version=__version__,
        description="Domain-agnostic capability platform foundation.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get("X-Request-ID")
        try:
            request_id = str(UUID(incoming)) if incoming else str(uuid4())
        except ValueError:
            request_id = str(uuid4())
        request.state.request_id = request_id
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            request_id_var.reset(token)

    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        response = ApiErrorResponse(
            error=ApiErrorDetail(
                code=exc.code,
                message=exc.message,
                retryable=exc.retryable,
                details=exc.details,
            ),
            request_id=UUID(request.state.request_id),
        )
        structlog.get_logger().warning("domain_error", code=exc.code, status=exc.status_code)
        return JSONResponse(status_code=exc.status_code, content=response.model_dump(mode="json"))

    app.include_router(router)
    return app


app = create_app()
