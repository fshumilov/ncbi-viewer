import logging
import time

from geo_expression_service.adapters.cache_store import CacheStore, NullCacheStore
from geo_expression_service.adapters.geo_client import (
    PLATFORM_SOFT_URL,
    GeoClient,
    build_series_matrix_url,
    decompress_if_needed,
    parse_series_matrix,
)
from geo_expression_service.domain.annotation_mapper import (
    map_gene_expression,
    parse_platform_table,
)
from geo_expression_service.domain.models import ExpressionRequest, ExpressionResult
from geo_expression_service.domain.plot_builder import build_combined_boxplot
from geo_expression_service.domain.validation import normalize_gse_id, validate_gene_count
from geo_expression_service.exceptions import (
    CachedNegativeEntryError,
    GeoDownloadError,
    MappingError,
)
from geo_expression_service.logging import get_request_id

logger = logging.getLogger(__name__)


class ExpressionService:
    def __init__(
        self,
        geo_client: GeoClient,
        cache: CacheStore | NullCacheStore | None = None,
    ) -> None:
        self._geo_client = geo_client
        self._cache = cache or NullCacheStore()

    async def get_expression(self, request: ExpressionRequest) -> ExpressionResult:
        started_at = time.perf_counter()
        normalized_gse = normalize_gse_id(request.gse_id)
        validated_genes = validate_gene_count(request.gene_symbols)
        request_id = get_request_id()

        cached_result = self._cache.get_result(normalized_gse, validated_genes)
        if cached_result is not None:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            logger.info(
                "Expression finished: cached=true duration_ms=%s gse_id=%s genes=%s request_id=%s",
                duration_ms,
                normalized_gse,
                len(validated_genes),
                request_id,
            )
            return cached_result.model_copy(update={"cached": True, "duration_ms": duration_ms})

        series_matrix = await self._fetch_series_matrix(normalized_gse)
        probe_to_symbols = await self._resolve_probe_map(series_matrix.gpl_id)
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
        self._cache.store_result(normalized_gse, validated_genes, result)
        logger.info(
            "Expression finished: cached=false duration_ms=%s gse_id=%s genes=%s request_id=%s",
            duration_ms,
            normalized_gse,
            len(validated_genes),
            request_id,
        )
        return result

    async def _fetch_series_matrix(self, gse_id: str):
        matrix_url = build_series_matrix_url(gse_id)
        try:
            raw_bytes = self._cache.get_raw(matrix_url)
        except CachedNegativeEntryError as exc:
            raise GeoDownloadError(str(exc)) from exc

        if raw_bytes is None:
            try:
                raw_bytes = await self._geo_client.download_bytes(
                    matrix_url,
                    resource_label=f"series matrix {gse_id}",
                )
            except GeoDownloadError as exc:
                self._cache.store_raw_negative(matrix_url, str(exc))
                raise
            self._cache.store_raw(matrix_url, raw_bytes)

        text = decompress_if_needed(raw_bytes, matrix_url)
        return parse_series_matrix(text, gse_id)

    async def _resolve_probe_map(self, gpl_id: str) -> dict[str, list[str]]:
        try:
            cached_map = self._cache.get_map(gpl_id)
        except CachedNegativeEntryError as exc:
            raise MappingError(str(exc)) from exc

        if cached_map is not None:
            return cached_map

        platform_url = PLATFORM_SOFT_URL.format(gpl_id=gpl_id)
        try:
            raw_bytes = self._cache.get_raw(platform_url)
        except CachedNegativeEntryError as exc:
            raise GeoDownloadError(str(exc)) from exc

        if raw_bytes is None:
            try:
                platform_text = await self._geo_client.fetch_platform_annotation(gpl_id)
            except GeoDownloadError as exc:
                self._cache.store_raw_negative(platform_url, str(exc))
                raise
            self._cache.store_raw(platform_url, platform_text.encode("utf-8", errors="replace"))
        else:
            platform_text = raw_bytes.decode("utf-8", errors="replace")

        try:
            _, probe_to_symbols = parse_platform_table(platform_text)
        except MappingError as exc:
            self._cache.store_map_negative(gpl_id, str(exc))
            raise

        self._cache.store_map(gpl_id, probe_to_symbols)
        return probe_to_symbols
