import base64
import io
import logging

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from geo_expression_service.domain.models import PlotArtifact

logger = logging.getLogger(__name__)


def build_combined_boxplot(
    sample_values_by_gene: dict[str, list[float]],
    gene_order: list[str],
) -> PlotArtifact:
    labels: list[str] = []
    values: list[list[float]] = []

    for gene in gene_order:
        gene_values = sample_values_by_gene.get(gene, [])
        if gene_values:
            labels.append(gene)
            values.append(gene_values)

    figure, axis = plt.subplots(figsize=(max(4, len(labels) * 1.5), 5))
    if values:
        axis.boxplot(values, tick_labels=labels)
        axis.set_ylabel("log2 expression (mean across probes)")
        axis.set_title("Gene expression across samples")
    else:
        axis.text(0.5, 0.5, "No mapped gene expression", ha="center", va="center")
        axis.set_axis_off()

    figure.tight_layout()
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", bbox_inches="tight")
    plt.close(figure)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    logger.info("Plot finished: genes=%s", len(labels))
    return PlotArtifact(content=encoded)
