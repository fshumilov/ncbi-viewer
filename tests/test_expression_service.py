import gzip

import pytest
from tests.conftest import PLATFORM_SOFT_FIXTURE, SERIES_MATRIX_FIXTURE

from geo_expression_service.adapters.cache_store import CacheStore, NullCacheStore
from geo_expression_service.adapters.geo_client import SeriesMatrix
from geo_expression_service.config import Settings
from geo_expression_service.domain.models import ExpressionRequest
from geo_expression_service.exceptions import MappingError
from geo_expression_service.services.expression_service import ExpressionService


class FakeGeoClient:
    def __init__(self) -> None:
        self.matrix_fetch_count = 0
        self.platform_fetch_count = 0

    async def fetch_series_matrix(self, gse_id: str) -> SeriesMatrix:
        self.matrix_fetch_count += 1
        return SeriesMatrix(
            gse_id=gse_id,
            gpl_id="GPL123",
            sample_ids=["sample1", "sample2"],
            probe_values={
                "probe1": [100.0, 200.0],
                "probe3": [50.0, 60.0],
            },
        )

    async def fetch_platform_annotation(self, gpl_id: str) -> str:
        self.platform_fetch_count += 1
        assert gpl_id == "GPL123"
        return PLATFORM_SOFT_FIXTURE

    async def download_bytes(self, url: str, resource_label: str) -> bytes:
        self.matrix_fetch_count += 1
        return gzip.compress(SERIES_MATRIX_FIXTURE.encode("utf-8"))


@pytest.mark.asyncio
async def test_expression_service_builds_result_from_geo_client() -> None:
    geo_client = FakeGeoClient()
    service = ExpressionService(geo_client=geo_client, cache=NullCacheStore())

    result = await service.get_expression(
        ExpressionRequest(gse_id="GSE2034", gene_symbols=["TP53", "BRCA1"])
    )

    assert result.gse_id == "GSE2034"
    assert result.genes == ["TP53", "BRCA1"]
    assert result.cached is False
    assert result.duration_ms >= 0
    assert result.plot.format == "png_base64"
    assert result.plot.content
    assert result.mapping.gpl_id == "GPL123"
    assert geo_client.matrix_fetch_count == 1
    assert geo_client.platform_fetch_count == 1

    tp53_stat = next(item for item in result.mapping.per_gene if item.gene_symbol == "TP53")
    brca1_stat = next(item for item in result.mapping.per_gene if item.gene_symbol == "BRCA1")
    assert tp53_stat.probes_mapped == 1
    assert brca1_stat.probes_mapped == 1


@pytest.mark.asyncio
async def test_expression_service_map_negative_cache_skips_platform_refetch(tmp_path) -> None:
    geo_client = FakeGeoClient()
    cache_store = CacheStore(
        Settings(
            cache_dir=tmp_path / "cache",
            cache_max_entries=16,
            cache_max_bytes=1024 * 1024,
        )
    )
    service = ExpressionService(geo_client=geo_client, cache=cache_store)
    cache_store.store_map_negative("GPL123", "Platform SOFT file missing platform table markers")
    request = ExpressionRequest(gse_id="GSE2034", gene_symbols=["TP53", "BRCA1"])

    with pytest.raises(MappingError):
        await service.get_expression(request)
    with pytest.raises(MappingError):
        await service.get_expression(request)

    assert geo_client.platform_fetch_count == 0


@pytest.mark.asyncio
async def test_expression_service_warm_result_cache(tmp_path) -> None:
    geo_client = FakeGeoClient()
    cache_store = CacheStore(
        Settings(
            cache_dir=tmp_path / "cache",
            cache_max_entries=16,
            cache_max_bytes=1024 * 1024,
        )
    )
    service = ExpressionService(geo_client=geo_client, cache=cache_store)
    request = ExpressionRequest(gse_id="GSE2034", gene_symbols=["TP53", "BRCA1"])

    cold_result = await service.get_expression(request)
    warm_result = await service.get_expression(request)

    assert cold_result.cached is False
    assert warm_result.cached is True
    assert warm_result.duration_ms <= cold_result.duration_ms
    assert geo_client.matrix_fetch_count == 1
    assert geo_client.platform_fetch_count == 1
