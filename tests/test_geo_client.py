import asyncio

import httpx
import pytest

from geo_expression_service.adapters.geo_client import GeoClient, is_retriable_status
from geo_expression_service.config import Settings
from geo_expression_service.exceptions import GeoDownloadError, GeoNotFoundError, GeoTimeoutError
from geo_expression_service.logging import set_request_id


class CountingTransport(httpx.AsyncBaseTransport):
    def __init__(self, handler) -> None:
        self._handler = handler
        self.in_flight = 0
        self.max_in_flight = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            return await self._handler(request)
        finally:
            self.in_flight -= 1


@pytest.mark.asyncio
async def test_geo_client_retries_transient_5xx_then_succeeds() -> None:
    attempts = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, content=b"ok")

    transport = CountingTransport(handler)
    settings = Settings(http_retry_count=3, http_retry_backoff_s=0.01, concurrency_limit=4)
    async with httpx.AsyncClient(transport=transport, timeout=1.0) as http_client:
        client = GeoClient(http_client, settings=settings)
        content = await client.download_bytes("https://example.test/file", "test resource")

    assert content == b"ok"
    assert attempts["count"] == 3


@pytest.mark.asyncio
async def test_geo_client_maps_404_without_retry() -> None:
    attempts = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(404)

    transport = CountingTransport(handler)
    settings = Settings(http_retry_count=3, http_retry_backoff_s=0.01)
    async with httpx.AsyncClient(transport=transport, timeout=1.0) as http_client:
        client = GeoClient(http_client, settings=settings)
        with pytest.raises(GeoNotFoundError):
            await client.download_bytes("https://example.test/missing", "missing resource")

    assert attempts["count"] == 1


@pytest.mark.asyncio
async def test_geo_client_maps_timeout_to_geo_timeout_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("read timed out", request=request)

    transport = CountingTransport(handler)
    settings = Settings(http_retry_count=0, http_retry_backoff_s=0.01)
    async with httpx.AsyncClient(transport=transport, timeout=1.0) as http_client:
        client = GeoClient(http_client, settings=settings)
        with pytest.raises(GeoTimeoutError):
            await client.download_bytes("https://example.test/slow", "slow resource")


@pytest.mark.asyncio
async def test_geo_client_semaphore_limits_parallel_downloads() -> None:
    release_gate = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        await release_gate.wait()
        return httpx.Response(200, content=b"ok")

    transport = CountingTransport(handler)
    settings = Settings(http_retry_count=0, concurrency_limit=2)
    async with httpx.AsyncClient(transport=transport, timeout=5.0) as http_client:
        client = GeoClient(http_client, settings=settings)
        tasks = [
            asyncio.create_task(
                client.download_bytes(f"https://example.test/file-{index}", f"resource-{index}")
            )
            for index in range(4)
        ]
        await asyncio.sleep(0.05)
        assert transport.max_in_flight <= 2
        release_gate.set()
        results = await asyncio.gather(*tasks)

    assert results == [b"ok", b"ok", b"ok", b"ok"]


@pytest.mark.asyncio
async def test_geo_client_logs_retry_with_request_id(caplog: pytest.LogCaptureFixture) -> None:
    attempts = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            return httpx.Response(500)
        return httpx.Response(200, content=b"ok")

    transport = CountingTransport(handler)
    settings = Settings(http_retry_count=2, http_retry_backoff_s=0.01)
    request_id_token = set_request_id("req-geo-retry")
    try:
        async with httpx.AsyncClient(transport=transport, timeout=1.0) as http_client:
            client = GeoClient(http_client, settings=settings)
            with caplog.at_level("WARNING"):
                content = await client.download_bytes("https://example.test/file", "retry resource")
    finally:
        from geo_expression_service.logging import _request_id_ctx

        _request_id_ctx.reset(request_id_token)

    assert content == b"ok"
    retry_logs = [record for record in caplog.records if "GEO download retry" in record.message]
    assert retry_logs
    assert "req-geo-retry" in retry_logs[0].message


def test_is_retriable_status() -> None:
    assert is_retriable_status(429) is True
    assert is_retriable_status(500) is True
    assert is_retriable_status(404) is False
    assert is_retriable_status(502) is True


@pytest.mark.asyncio
async def test_geo_client_exhausted_retries_raise_geo_download_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    transport = CountingTransport(handler)
    settings = Settings(http_retry_count=1, http_retry_backoff_s=0.01)
    async with httpx.AsyncClient(transport=transport, timeout=1.0) as http_client:
        client = GeoClient(http_client, settings=settings)
        with pytest.raises(GeoDownloadError):
            await client.download_bytes("https://example.test/fail", "failing resource")
