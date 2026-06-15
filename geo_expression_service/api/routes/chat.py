import logging

from fastapi import APIRouter, Depends

from geo_expression_service.api.dependencies import get_chat_agent
from geo_expression_service.domain.models import ChatRequest, ChatResponse
from geo_expression_service.logging import get_request_id
from geo_expression_service.services.chat_agent import ChatAgent

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.post("/chat", response_model=ChatResponse)
async def post_chat(
    body: ChatRequest,
    chat_agent: ChatAgent = Depends(get_chat_agent),
) -> ChatResponse:
    response = await chat_agent.handle(body.message)
    expression = response.expression
    logger.info(
        (
            "Chat route finished: tool_invoked=%s gse_id=%s genes=%s "
            "cached=%s duration_ms=%s request_id=%s"
        ),
        response.tool_invoked,
        expression.gse_id if expression is not None else None,
        len(expression.genes) if expression is not None else 0,
        expression.cached if expression is not None else None,
        expression.duration_ms if expression is not None else None,
        get_request_id(),
    )
    return response
