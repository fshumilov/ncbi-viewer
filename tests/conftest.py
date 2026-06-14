import pytest
from fastapi.testclient import TestClient

from geo_expression_service.main import create_app

PLATFORM_SOFT_FIXTURE = """\
!Platform_geo_accession = "GPL123"
!platform_table_begin
"ID"\t"Gene Symbol"
"probe1"\t"TP53 /// WRAP53"
"probe2"\t"---"
"probe3"\t"BRCA1"
!platform_table_end
"""


@pytest.fixture
def platform_soft_text() -> str:
    return PLATFORM_SOFT_FIXTURE


@pytest.fixture
def client() -> TestClient:
    with TestClient(create_app()) as test_client:
        yield test_client
