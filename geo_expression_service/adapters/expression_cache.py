from geo_expression_service.domain.models import ExpressionResult


class NullExpressionCache:
    """No-op cache seam until BL-03 CacheStore integration."""

    async def get_expression_result(
        self,
        gse_id: str,
        gene_symbols: list[str],
    ) -> ExpressionResult | None:
        return None

    async def store_expression_result(
        self,
        gse_id: str,
        gene_symbols: list[str],
        result: ExpressionResult,
    ) -> None:
        return None
