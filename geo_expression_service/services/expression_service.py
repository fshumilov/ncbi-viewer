import logging
import time

from geo_expression_service.adapters.expression_cache import NullExpressionCache
from geo_expression_service.adapters.geo_client import GeoClient
from geo_expression_service.domain.annotation_mapper import (
    map_gene_expression,
    parse_platform_table,
)
from geo_expression_service.domain.models import ExpressionRequest, ExpressionResult
from geo_expression_service.domain.plot_builder import build_combined_boxplot
from geo_expression_service.domain.validation import normalize_gse_id, validate_gene_count

logger = logging.getLogger(__name__)


class ExpressionService:
    def __init__(
        self,
        geo_client: GeoClient,
        cache: NullExpressionCache | None = None,
    ) -> None:
        self._geo_client = geo_client
        self._cache = cache or NullExpressionCache()

    async def get_expression(self, request: ExpressionRequest) -> ExpressionResult:
        started_at = time.perf_counter()
        normalized_gse = normalize_gse_id(request.gse_id)
        validated_genes = validate_gene_count(request.gene_symbols)

        cached_result = await self._cache.get_expression_result(normalized_gse, validated_genes)
        if cached_result is not None:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            logger.info(
                "Expression finished: cached=true duration_ms=%s gse_id=%s genes=%s",
                duration_ms,
                normalized_gse,
                len(validated_genes),
            )
            return cached_result.model_copy(update={"cached": True, "duration_ms": duration_ms})

        series_matrix = await self._geo_client.fetch_series_matrix(normalized_gse)
        platform_text = await self._geo_client.fetch_platform_annotation(series_matrix.gpl_id)
        _, probe_to_symbols = parse_platform_table(platform_text)
        expression_data = map_gene_expression(
            probe_values=series_matrix.probe_values,
            probe_to_symbols=probe_to_symbols,
            gene_symbols=validated_genes,
            gpl_id=series_matrix.gpl_id,
        )
        plot = build_combined_boxplot(
            sample_values_by_gene=expression_data.sample_values_by_gene,
            gene_order=validated_genes,
        )
        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        result = ExpressionResult(
            gse_id=normalized_gse,
            genes=validated_genes,
            plot=plot,
            mapping=expression_data.mapping,
            sample_values_by_gene=expression_data.sample_values_by_gene or None,
            cached=False,
            duration_ms=duration_ms,
        )
        await self._cache.store_expression_result(normalized_gse, validated_genes, result)
        logger.info(
            "Expression finished: cached=false duration_ms=%s gse_id=%s genes=%s",
            duration_ms,
            normalized_gse,
            len(validated_genes),
        )
        return result
