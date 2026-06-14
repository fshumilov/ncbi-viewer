import csv
import io
import logging
import math
import re
from dataclasses import dataclass

from geo_expression_service.domain.models import GeneMappingStat, MappingSummary
from geo_expression_service.exceptions import MappingError

logger = logging.getLogger(__name__)

SYMBOL_COLUMN_CANDIDATES = (
    "Gene Symbol",
    "GENE_SYMBOL",
    "SYMBOL",
    "Gene symbol",
    "Gene_Symbol",
)
UNMAPPED_VALUE_TOKENS = frozenset({"", "---", "NA", "N/A", "NULL", "null", "NaN"})
MULTI_GENE_SPLIT_PATTERN = re.compile(r"\s*///\s*|\s*//\s*")


@dataclass(frozen=True)
class GeneExpressionData:
    mapping: MappingSummary
    sample_values_by_gene: dict[str, list[float]]


def parse_platform_table(platform_text: str) -> tuple[str, dict[str, list[str]]]:
    begin_marker = "!platform_table_begin"
    end_marker = "!platform_table_end"
    if begin_marker not in platform_text or end_marker not in platform_text:
        raise MappingError("Platform SOFT file missing platform table markers")

    table_text = platform_text.split(begin_marker, maxsplit=1)[1].split(end_marker, maxsplit=1)[0]
    reader = csv.reader(io.StringIO(table_text.strip()), delimiter="\t")
    try:
        header = next(reader)
    except StopIteration as exc:
        raise MappingError("Platform table is empty") from exc

    symbol_column_index = detect_symbol_column_index(header)
    probe_column_index = detect_probe_column_index(header)
    probe_to_symbols: dict[str, list[str]] = {}

    for row in reader:
        if len(row) <= max(symbol_column_index, probe_column_index):
            continue
        probe_id = row[probe_column_index].strip().strip('"')
        if not probe_id:
            continue
        symbols = parse_symbol_cell(row[symbol_column_index])
        if symbols:
            probe_to_symbols[probe_id] = symbols

    gpl_id = extract_gpl_id(platform_text)
    return gpl_id, probe_to_symbols


def detect_symbol_column_index(header: list[str]) -> int:
    normalized_headers = [column.strip().strip('"') for column in header]
    for candidate in SYMBOL_COLUMN_CANDIDATES:
        if candidate in normalized_headers:
            return normalized_headers.index(candidate)
    raise MappingError(
        f"Could not detect gene symbol column among: {', '.join(SYMBOL_COLUMN_CANDIDATES)}"
    )


def detect_probe_column_index(header: list[str]) -> int:
    normalized_headers = [column.strip().strip('"') for column in header]
    for candidate in ("ID", "ID_REF", "Probe Set ID", "PROBE_ID"):
        if candidate in normalized_headers:
            return normalized_headers.index(candidate)
    return 0


def parse_symbol_cell(raw_value: str) -> list[str]:
    cleaned = raw_value.strip().strip('"')
    if cleaned.upper() in UNMAPPED_VALUE_TOKENS:
        return []
    symbols = [
        symbol.strip().upper()
        for symbol in MULTI_GENE_SPLIT_PATTERN.split(cleaned)
        if symbol.strip() and symbol.strip().upper() not in UNMAPPED_VALUE_TOKENS
    ]
    return symbols


def extract_gpl_id(platform_text: str) -> str:
    for line in platform_text.splitlines():
        if line.startswith("!Platform_geo_accession"):
            match = re.search(r"GPL\d+", line, re.IGNORECASE)
            if match:
                return match.group(0).upper()
        if line.startswith("!Series_platform_id"):
            parts = line.split("\t")
            if len(parts) >= 2:
                value = parts[1].strip().strip('"').upper()
                if value.startswith("GPL"):
                    return value
    raise MappingError("Could not resolve GPL ID from platform annotation")


def map_gene_expression(
    probe_values: dict[str, list[float]],
    probe_to_symbols: dict[str, list[str]],
    gene_symbols: list[str],
    gpl_id: str,
) -> GeneExpressionData:
    requested_genes = [symbol.upper() for symbol in gene_symbols]
    gene_to_probes: dict[str, list[str]] = {gene: [] for gene in requested_genes}

    for probe_id, symbols in probe_to_symbols.items():
        for gene in requested_genes:
            if gene in symbols:
                gene_to_probes[gene].append(probe_id)

    per_gene_stats: list[GeneMappingStat] = []
    sample_values_by_gene: dict[str, list[float]] = {}
    mapped_probe_ids: set[str] = set()

    for gene in requested_genes:
        mapped_probes = gene_to_probes[gene]
        probes_mapped = len(mapped_probes)
        mapped_probe_ids.update(mapped_probes)

        if probes_mapped == 0:
            per_gene_stats.append(
                GeneMappingStat(
                    gene_symbol=gene,
                    probes_mapped=0,
                    skip_reason="no_probes_mapped",
                )
            )
            continue

        aggregated_values = aggregate_gene_samples(probe_values, mapped_probes)
        sample_values_by_gene[gene] = aggregated_values
        per_gene_stats.append(
            GeneMappingStat(
                gene_symbol=gene,
                probes_mapped=probes_mapped,
            )
        )

    unmapped_probe_count = sum(1 for probe_id in probe_values if probe_id not in mapped_probe_ids)
    mapping = MappingSummary(
        per_gene=per_gene_stats,
        unmapped_probe_count=unmapped_probe_count,
        gpl_id=gpl_id,
    )
    logger.info(
        "Gene mapping finished: genes=%s mapped_probes=%s unmapped_probes=%s gpl_id=%s",
        len(requested_genes),
        len(mapped_probe_ids),
        unmapped_probe_count,
        gpl_id,
    )
    return GeneExpressionData(mapping=mapping, sample_values_by_gene=sample_values_by_gene)


def aggregate_gene_samples(
    probe_values: dict[str, list[float]],
    mapped_probes: list[str],
) -> list[float]:
    sample_count = len(next(iter(probe_values.values()), []))
    aggregated: list[float] = []

    for sample_index in range(sample_count):
        log2_values: list[float] = []
        for probe_id in mapped_probes:
            values = probe_values.get(probe_id)
            if values is None or sample_index >= len(values):
                continue
            log2_value = to_log2_expression(values[sample_index])
            if not math.isnan(log2_value):
                log2_values.append(log2_value)
        if log2_values:
            aggregated.append(sum(log2_values) / len(log2_values))
        else:
            aggregated.append(float("nan"))

    return [value for value in aggregated if not math.isnan(value)]


def to_log2_expression(raw_value: float) -> float:
    if raw_value <= 0:
        return float("nan")
    return math.log2(raw_value)
