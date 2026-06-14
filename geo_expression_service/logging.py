import contextvars
import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("geo_expression_service.request")

_request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id",
    default=None,
)


def get_request_id() -> str | None:
    return _request_id_ctx.get()


def set_request_id(request_id: str | None) -> contextvars.Token[str | None]:
    return _request_id_ctx.set(request_id)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.request_id = request_id
        request_id_token = set_request_id(request_id)
        started_at = time.perf_counter()

        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            logger.info(
                "Request finished: method=%s path=%s status=%s duration_ms=%s request_id=%s",
                request.method,
                request.url.path,
                response.status_code,
                duration_ms,
                request_id,
            )
            response.headers["X-Request-Id"] = request_id
            return response
        finally:
            _request_id_ctx.reset(request_id_token)
