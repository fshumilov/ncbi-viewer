from fastapi import FastAPI
from fastapi.testclient import TestClient

from geo_expression_service.exceptions import GeoNotFoundError, GeoTimeoutError
from geo_expression_service.main import register_exception_handlers


def _build_test_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/not-found")
    async def raise_not_found() -> None:
        raise GeoNotFoundError("GEO resource not found for series matrix GSE9999: HTTP 404")

    @app.get("/timeout")
    async def raise_timeout() -> None:
        raise GeoTimeoutError("Timed out downloading series matrix GSE2034")

    return app


def test_geo_not_found_maps_to_http_404() -> None:
    client = TestClient(_build_test_app())
    response = client.get("/not-found")

    assert response.status_code == 404
    body = response.json()
    assert body["error"] == "geo_not_found"
    assert "GSE9999" in body["message"]


def test_geo_timeout_maps_to_http_504() -> None:
    client = TestClient(_build_test_app())
    response = client.get("/timeout")

    assert response.status_code == 504
    body = response.json()
    assert body["error"] == "geo_timeout"
    assert "Timed out" in body["message"]
