import logging

from fastapi import APIRouter, Depends, Query

from geo_expression_service.api.dependencies import get_expression_service
from geo_expression_service.domain.models import ExpressionRequest, ExpressionResult
from geo_expression_service.domain.validation import validate_expression_query
from geo_expression_service.services.expression_service import ExpressionService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["expression"])


@router.get("/expression", response_model=ExpressionResult)
async def get_expression(
    gse: str = Query(description="GEO series accession, e.g. GSE2034"),
    genes: str = Query(description="Comma-separated gene symbols, 2-5 unique"),
    expression_service: ExpressionService = Depends(get_expression_service),
) -> ExpressionResult:
    normalized_gse, validated_genes = validate_expression_query(gse, genes)
    request = ExpressionRequest(gse_id=normalized_gse, gene_symbols=validated_genes)
    result = await expression_service.get_expression(request)
    logger.info(
        "Expression route finished: gse_id=%s genes=%s cached=%s duration_ms=%s",
        result.gse_id,
        len(result.genes),
        result.cached,
        result.duration_ms,
    )
    return result
