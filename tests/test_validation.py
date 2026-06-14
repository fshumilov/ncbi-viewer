import pytest

from geo_expression_service.domain.validation import (
    normalize_gene_symbols,
    normalize_gse_id,
    parse_gene_list,
    validate_expression_query,
    validate_gene_count,
)
from geo_expression_service.exceptions import InvalidGeneCountError, InvalidGseFormatError


def test_normalize_gse_id_uppercases_and_accepts_valid_format() -> None:
    assert normalize_gse_id("gse2034") == "GSE2034"
    assert normalize_gse_id("  GSE2034  ") == "GSE2034"


@pytest.mark.parametrize("invalid_gse", ["GSE", "GSEABC", "2034", ""])
def test_normalize_gse_id_rejects_invalid_format(invalid_gse: str) -> None:
    with pytest.raises(InvalidGseFormatError):
        normalize_gse_id(invalid_gse)


def test_parse_gene_list_splits_and_normalizes() -> None:
    assert parse_gene_list("tp53, brca1") == ["TP53", "BRCA1"]


def test_validate_gene_count_deduplicates_symbols() -> None:
    assert validate_gene_count(["TP53", "TP53", "BRCA1"]) == ["TP53", "BRCA1"]


@pytest.mark.parametrize("gene_count", [0, 1, 6])
def test_validate_gene_count_rejects_out_of_bounds(gene_count: int) -> None:
    genes = [f"GENE{i}" for i in range(gene_count)]
    with pytest.raises(InvalidGeneCountError):
        validate_gene_count(genes)


def test_validate_expression_query_returns_normalized_values() -> None:
    gse_id, genes = validate_expression_query("gse2034", "TP53, BRCA1")
    assert gse_id == "GSE2034"
    assert genes == ["TP53", "BRCA1"]


def test_normalize_gene_symbols_skips_empty_tokens() -> None:
    assert normalize_gene_symbols([" TP53 ", "", "  "]) == ["TP53"]
