import math

import pytest

from geo_expression_service.domain.annotation_mapper import (
    aggregate_gene_samples,
    detect_symbol_column_index,
    map_gene_expression,
    parse_platform_table,
    parse_symbol_cell,
    to_log2_expression,
)
from geo_expression_service.exceptions import MappingError


def test_parse_symbol_cell_splits_multi_gene_values() -> None:
    assert parse_symbol_cell("TP53 /// WRAP53") == ["TP53", "WRAP53"]
    assert parse_symbol_cell("BRCA1 // BRCA2") == ["BRCA1", "BRCA2"]


@pytest.mark.parametrize("raw_value", ["---", "NA", "N/A", "", "null"])
def test_parse_symbol_cell_treats_sentinels_as_unmapped(raw_value: str) -> None:
    assert parse_symbol_cell(raw_value) == []


def test_detect_symbol_column_index_finds_gene_symbol_column() -> None:
    header = ["ID", "GENE_SYMBOL", "Other"]
    assert detect_symbol_column_index(header) == 1


def test_parse_platform_table_builds_probe_to_symbols(platform_soft_text: str) -> None:
    gpl_id, probe_to_symbols = parse_platform_table(platform_soft_text)

    assert gpl_id == "GPL123"
    assert probe_to_symbols["probe1"] == ["TP53", "WRAP53"]
    assert "probe2" not in probe_to_symbols
    assert probe_to_symbols["probe3"] == ["BRCA1"]


def test_parse_platform_table_raises_when_markers_missing() -> None:
    with pytest.raises(MappingError, match="platform table markers"):
        parse_platform_table("no table here")


def test_map_gene_expression_maps_requested_genes_and_skip_reason() -> None:
    probe_values = {
        "probe1": [100.0, 200.0],
        "probe3": [50.0, 60.0],
        "orphan": [1.0, 2.0],
    }
    probe_to_symbols = {
        "probe1": ["TP53", "WRAP53"],
        "probe3": ["BRCA1"],
    }

    result = map_gene_expression(
        probe_values=probe_values,
        probe_to_symbols=probe_to_symbols,
        gene_symbols=["TP53", "BRCA1", "EGFR"],
        gpl_id="GPL123",
    )

    tp53_stat = next(item for item in result.mapping.per_gene if item.gene_symbol == "TP53")
    egfr_stat = next(item for item in result.mapping.per_gene if item.gene_symbol == "EGFR")

    assert tp53_stat.probes_mapped == 1
    assert tp53_stat.skip_reason is None
    assert egfr_stat.probes_mapped == 0
    assert egfr_stat.skip_reason == "no_probes_mapped"
    assert result.mapping.unmapped_probe_count == 1
    assert "TP53" in result.sample_values_by_gene
    assert "EGFR" not in result.sample_values_by_gene


def test_aggregate_gene_samples_averages_log2_values_across_probes() -> None:
    probe_values = {
        "p1": [100.0],
        "p2": [200.0],
    }
    aggregated = aggregate_gene_samples(probe_values, ["p1", "p2"])

    expected = (to_log2_expression(100.0) + to_log2_expression(200.0)) / 2
    assert len(aggregated) == 1
    assert math.isclose(aggregated[0], expected)


def test_to_log2_expression_returns_nan_for_non_positive_values() -> None:
    assert math.isnan(to_log2_expression(0.0))
    assert math.isnan(to_log2_expression(-1.0))
