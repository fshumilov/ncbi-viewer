import logging

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

logger = logging.getLogger("geo_expression_service.api.routes.health")

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str = Field(description="Liveness indicator")
    service: str = Field(description="Service name")


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request) -> HealthResponse:
    request_id = getattr(request.state, "request_id", None)
    logger.info(
        "Health finished: status=ok request_id=%s",
        request_id,
    )
    return HealthResponse(status="ok", service="geo-expression-service")
