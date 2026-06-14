import re

from geo_expression_service.exceptions import InvalidGeneCountError, InvalidGseFormatError

GSE_PATTERN = re.compile(r"^GSE\d+$", re.IGNORECASE)
MIN_GENE_COUNT = 2
MAX_GENE_COUNT = 5


def normalize_gse_id(gse_id: str) -> str:
    normalized = gse_id.strip().upper()
    if not GSE_PATTERN.match(normalized):
        raise InvalidGseFormatError(
            f"Invalid GSE format: expected GSE followed by digits, got {gse_id!r}"
        )
    return normalized


def normalize_gene_symbols(gene_symbols: list[str]) -> list[str]:
    normalized_symbols: list[str] = []
    for symbol in gene_symbols:
        cleaned = symbol.strip().upper()
        if cleaned:
            normalized_symbols.append(cleaned)
    return normalized_symbols


def parse_gene_list(genes: str) -> list[str]:
    raw_symbols = [part.strip() for part in genes.split(",")]
    return normalize_gene_symbols(raw_symbols)


def validate_gene_count(gene_symbols: list[str]) -> list[str]:
    unique_symbols = list(dict.fromkeys(gene_symbols))
    unique_count = len(unique_symbols)
    if unique_count < MIN_GENE_COUNT or unique_count > MAX_GENE_COUNT:
        raise InvalidGeneCountError(
            f"Gene count must be between {MIN_GENE_COUNT} and {MAX_GENE_COUNT} "
            f"unique symbols; got {unique_count}"
        )
    return unique_symbols


def validate_expression_query(gse_id: str, genes: str) -> tuple[str, list[str]]:
    normalized_gse = normalize_gse_id(gse_id)
    parsed_genes = parse_gene_list(genes)
    validated_genes = validate_gene_count(parsed_genes)
    return normalized_gse, validated_genes
