from typing import Literal

from pydantic import BaseModel, Field


class ExpressionRequest(BaseModel):
    gse_id: str
    gene_symbols: list[str] = Field(min_length=2, max_length=5)


class GeneMappingStat(BaseModel):
    gene_symbol: str
    probes_mapped: int
    aggregation: Literal["mean_log2"] = "mean_log2"
    skip_reason: str | None = None


class MappingSummary(BaseModel):
    per_gene: list[GeneMappingStat]
    unmapped_probe_count: int
    gpl_id: str


class PlotArtifact(BaseModel):
    format: Literal["png_base64"] = "png_base64"
    content: str


class ExpressionResult(BaseModel):
    gse_id: str
    genes: list[str]
    plot: PlotArtifact
    mapping: MappingSummary
    sample_values_by_gene: dict[str, list[float]] | None = None
    cached: bool = False
    duration_ms: float
