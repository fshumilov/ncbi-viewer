import pytest
from fastapi.testclient import TestClient
from tests.test_expression_service import FakeGeoClient

from geo_expression_service.api.dependencies import get_chat_agent
from geo_expression_service.config import Settings
from geo_expression_service.domain.chat_parser import ChatParseStatus, parse_chat_intent
from geo_expression_service.main import create_app
from geo_expression_service.services.chat_agent import ChatAgent
from geo_expression_service.services.expression_service import ExpressionService


def test_parse_chat_intent_happy_path() -> None:
    parsed = parse_chat_intent("Show me TP53 and BRCA1 expression in GSE2034")

    assert parsed.status == ChatParseStatus.OK
    assert parsed.gse_id == "GSE2034"
    assert parsed.gene_symbols == ["TP53", "BRCA1"]


def test_parse_chat_intent_missing_gse() -> None:
    parsed = parse_chat_intent("Show me TP53 and BRCA1 expression")

    assert parsed.status == ChatParseStatus.MISSING_GSE


def test_parse_chat_intent_missing_genes() -> None:
    parsed = parse_chat_intent("Show expression in GSE2034")

    assert parsed.status == ChatParseStatus.MISSING_GENES
    assert parsed.gse_id == "GSE2034"


def test_parse_chat_intent_invalid_gene_count() -> None:
    parsed = parse_chat_intent("Show TP53 in GSE2034")

    assert parsed.status == ChatParseStatus.INVALID_GENE_COUNT
    assert parsed.gse_id == "GSE2034"


@pytest.fixture
def stub_chat_client() -> TestClient:
    settings = Settings(stub_llm=True)
    geo_client = FakeGeoClient()
    expression_service = ExpressionService(geo_client=geo_client, cache=None)
    chat_agent = ChatAgent(expression_service=expression_service, settings=settings)
    app = create_app(settings=settings)
    app.dependency_overrides[get_chat_agent] = lambda: chat_agent

    with TestClient(app) as test_client:
        yield test_client


def test_chat_stub_happy_path(stub_chat_client: TestClient) -> None:
    response = stub_chat_client.post(
        "/chat",
        json={"message": "Show me TP53 and BRCA1 expression in GSE2034"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tool_invoked"] is True
    assert payload["expression"]["gse_id"] == "GSE2034"
    assert payload["expression"]["genes"] == ["TP53", "BRCA1"]
    assert payload["expression"]["plot"]["format"] == "png_base64"
    assert "cached" in payload["expression"]
    assert "duration_ms" in payload["expression"]
    assert "GSE2034" in payload["message"]
    assert "TP53" in payload["message"]


def test_chat_stub_clarification_when_unparsed(stub_chat_client: TestClient) -> None:
    response = stub_chat_client.post(
        "/chat",
        json={"message": "Hello, what can you do?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["tool_invoked"] is False
    assert payload["expression"] is None
    assert "GSE" in payload["message"]
