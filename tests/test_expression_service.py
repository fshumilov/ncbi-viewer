import pytest
from tests.conftest import PLATFORM_SOFT_FIXTURE

from geo_expression_service.adapters.geo_client import SeriesMatrix
from geo_expression_service.domain.models import ExpressionRequest
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


@pytest.mark.asyncio
async def test_expression_service_builds_result_from_geo_client() -> None:
    geo_client = FakeGeoClient()
    service = ExpressionService(geo_client=geo_client)

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
