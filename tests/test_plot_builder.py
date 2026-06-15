import base64

from geo_expression_service.domain.plot_builder import build_combined_boxplot


def test_build_combined_boxplot_returns_png_base64() -> None:
    sample_values_by_gene = {
        "TP53": [1.0, 2.0, 3.0],
        "BRCA1": [2.0, 2.5, 3.5],
    }

    artifact = build_combined_boxplot(sample_values_by_gene, ["TP53", "BRCA1"])

    assert artifact.format == "png_base64"
    decoded = base64.b64decode(artifact.content)
    assert decoded.startswith(b"\x89PNG")


def test_build_combined_boxplot_handles_no_mapped_values() -> None:
    artifact = build_combined_boxplot({}, ["TP53"])

    assert artifact.format == "png_base64"
    assert base64.b64decode(artifact.content).startswith(b"\x89PNG")
