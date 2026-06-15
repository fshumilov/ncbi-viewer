import pytest

from geo_expression_service.adapters.cache_store import CacheStore, build_result_key
from geo_expression_service.config import Settings
from geo_expression_service.domain.models import (
    ExpressionResult,
    GeneMappingStat,
    MappingSummary,
    PlotArtifact,
)
from geo_expression_service.exceptions import CachedNegativeEntryError


def build_result(gse_id: str = "GSE2034", genes: list[str] | None = None) -> ExpressionResult:
    gene_symbols = genes or ["TP53", "BRCA1"]
    return ExpressionResult(
        gse_id=gse_id,
        genes=gene_symbols,
        plot=PlotArtifact(content="cGxvdA=="),
        mapping=MappingSummary(
            per_gene=[GeneMappingStat(gene_symbol=gene, probes_mapped=1) for gene in gene_symbols],
            unmapped_probe_count=0,
            gpl_id="GPL123",
        ),
        cached=False,
        duration_ms=12.5,
    )


@pytest.fixture
def cache_store(tmp_path) -> CacheStore:
    settings = Settings(
        cache_dir=tmp_path / "cache",
        cache_max_entries=8,
        cache_max_bytes=1024 * 1024,
    )
    return CacheStore(settings)


def test_result_cache_cold_then_warm(cache_store: CacheStore) -> None:
    result = build_result()

    assert cache_store.get_result("GSE2034", ["TP53", "BRCA1"]) is None
    cache_store.store_result("GSE2034", ["TP53", "BRCA1"], result)

    cached = cache_store.get_result("GSE2034", ["TP53", "BRCA1"])
    assert cached is not None
    assert cached.gse_id == "GSE2034"
    assert cached.genes == ["TP53", "BRCA1"]


def test_result_cache_survives_restart(tmp_path) -> None:
    cache_dir = tmp_path / "cache"
    settings = Settings(cache_dir=cache_dir, cache_max_entries=8, cache_max_bytes=1024 * 1024)
    first_store = CacheStore(settings)
    first_store.store_result("GSE2034", ["TP53", "BRCA1"], build_result())

    restarted_store = CacheStore(settings)
    cached = restarted_store.get_result("GSE2034", ["TP53", "BRCA1"])

    assert cached is not None
    assert cached.plot.content == "cGxvdA=="


def test_raw_cache_round_trip(cache_store: CacheStore) -> None:
    url = "https://example.com/matrix.txt.gz"
    payload = b"\x1f\x8b\x08payload"

    cache_store.store_raw(url, payload)
    cached = cache_store.get_raw(url)

    assert cached == payload


def test_map_negative_cache_fails_fast(cache_store: CacheStore) -> None:
    cache_store.store_map_negative("GPL999", "Platform SOFT file missing platform table markers")

    with pytest.raises(CachedNegativeEntryError) as exc_info:
        cache_store.get_map("GPL999")

    assert exc_info.value.layer == "map"
    assert "missing platform table markers" in str(exc_info.value)


def test_schema_version_mismatch_deletes_entry(cache_store: CacheStore) -> None:
    storage_key = build_result_key("GSE2034", ["TP53", "BRCA1"])
    metadata_path = cache_store._metadata_path(storage_key)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(
        '{"schema_version": 0, "layer": "result", "expression_result": {}}',
        encoding="utf-8",
    )

    assert cache_store.get_result("GSE2034", ["TP53", "BRCA1"]) is None
    assert not metadata_path.exists()


def test_eviction_removes_oldest_entry(tmp_path) -> None:
    settings = Settings(
        cache_dir=tmp_path / "cache",
        cache_max_entries=1,
        cache_max_bytes=1024 * 1024,
    )
    cache_store = CacheStore(settings)
    first_result = build_result(gse_id="GSE1000", genes=["TP53", "BRCA1"])
    second_result = build_result(gse_id="GSE2000", genes=["TP53", "BRCA1"])

    cache_store.store_result("GSE1000", ["TP53", "BRCA1"], first_result)
    cache_store.store_result("GSE2000", ["TP53", "BRCA1"], second_result)

    assert cache_store.get_result("GSE1000", ["TP53", "BRCA1"]) is None
    assert cache_store.get_result("GSE2000", ["TP53", "BRCA1"]) is not None
