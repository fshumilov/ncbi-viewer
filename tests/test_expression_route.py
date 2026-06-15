import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize(
    ("genes", "error_code"),
    [
        ("TP53", "invalid_gene_count"),
        ("TP53,BRCA1,EGFR,MAPK1,AKT1,MTOR", "invalid_gene_count"),
    ],
)
def test_expression_rejects_invalid_gene_count_before_service(
    client: TestClient,
    genes: str,
    error_code: str,
) -> None:
    response = client.get(
        "/expression",
        params={"gse": "GSE2034", "genes": genes},
    )

    assert response.status_code == 422
    assert response.json()["error"] == error_code


@pytest.mark.parametrize("gse", ["GSE", "INVALID", "1234"])
def test_expression_rejects_invalid_gse_format(client: TestClient, gse: str) -> None:
    response = client.get(
        "/expression",
        params={"gse": gse, "genes": "TP53,BRCA1"},
    )

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_gse_format"
