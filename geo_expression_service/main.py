from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from geo_expression_service.adapters.cache_store import CacheStore
from geo_expression_service.adapters.geo_client import GeoClient
from geo_expression_service.api.routes import chat, expression, health
from geo_expression_service.config import Settings, get_settings
from geo_expression_service.exceptions import (
    GeoDownloadError,
    GeoExpressionError,
    GeoNotFoundError,
    GeoTimeoutError,
    InvalidGeneCountError,
    InvalidGseFormatError,
    MappingError,
)
from geo_expression_service.logging import RequestIdMiddleware, configure_logging
from geo_expression_service.services.chat_agent import ChatAgent
from geo_expression_service.services.expression_service import ExpressionService


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    app.state.settings = settings
    app.state.http_client = httpx.AsyncClient(timeout=settings.http_timeout_s)
    geo_client = GeoClient(app.state.http_client, settings=settings)
    cache_store = CacheStore(settings)
    app.state.expression_service = ExpressionService(
        geo_client=geo_client,
        cache=cache_store,
    )
    app.state.chat_agent = ChatAgent(
        expression_service=app.state.expression_service,
        settings=settings,
    )
    yield
    await app.state.http_client.aclose()


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    app_settings = settings or get_settings()
    app = FastAPI(
        title="GEO Expression Service",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = app_settings
    app.add_middleware(RequestIdMiddleware)
    app.include_router(health.router)
    app.include_router(expression.router)
    app.include_router(chat.router)
    register_exception_handlers(app)
    return app


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(InvalidGeneCountError)
    async def handle_invalid_gene_count(
        request: Request,
        exc: InvalidGeneCountError,
    ) -> JSONResponse:
        return _validation_error_response(request, "invalid_gene_count", str(exc))

    @app.exception_handler(InvalidGseFormatError)
    async def handle_invalid_gse_format(
        request: Request,
        exc: InvalidGseFormatError,
    ) -> JSONResponse:
        return _validation_error_response(request, "invalid_gse_format", str(exc))

    @app.exception_handler(GeoNotFoundError)
    async def handle_geo_not_found_error(
        request: Request,
        exc: GeoNotFoundError,
    ) -> JSONResponse:
        return _service_error_response(request, 404, "geo_not_found", str(exc))

    @app.exception_handler(GeoTimeoutError)
    async def handle_geo_timeout_error(
        request: Request,
        exc: GeoTimeoutError,
    ) -> JSONResponse:
        return _service_error_response(request, 504, "geo_timeout", str(exc))

    @app.exception_handler(GeoDownloadError)
    async def handle_geo_download_error(
        request: Request,
        exc: GeoDownloadError,
    ) -> JSONResponse:
        return _service_error_response(request, 502, "geo_download_error", str(exc))

    @app.exception_handler(MappingError)
    async def handle_mapping_error(
        request: Request,
        exc: MappingError,
    ) -> JSONResponse:
        return _service_error_response(request, 502, "mapping_error", str(exc))

    @app.exception_handler(GeoExpressionError)
    async def handle_geo_expression_error(
        request: Request,
        exc: GeoExpressionError,
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=500,
            content={
                "error": "geo_expression_error",
                "message": str(exc),
                "request_id": request_id,
            },
        )


def _validation_error_response(
    request: Request,
    error_code: str,
    message: str,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=422,
        content={
            "error": error_code,
            "message": message,
            "request_id": request_id,
        },
    )


def _service_error_response(
    request: Request,
    status_code: int,
    error_code: str,
    message: str,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error_code,
            "message": message,
            "request_id": request_id,
        },
    )


app = create_app()
