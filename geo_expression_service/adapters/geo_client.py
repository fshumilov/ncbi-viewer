import asyncio
import csv
import gzip
import io
import logging
import re
from dataclasses import dataclass

import httpx

from geo_expression_service.config import Settings, get_settings
from geo_expression_service.exceptions import (
    GeoDownloadError,
    GeoNotFoundError,
    GeoTimeoutError,
)
from geo_expression_service.logging import get_request_id

logger = logging.getLogger(__name__)

SERIES_MATRIX_BEGIN = "!series_matrix_table_begin"
SERIES_MATRIX_END = "!series_matrix_table_end"
PLATFORM_SOFT_URL = (
    "https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc={gpl_id}&targ=self&form=text&view=full"
)


@dataclass(frozen=True)
class SeriesMatrix:
    gse_id: str
    gpl_id: str
    sample_ids: list[str]
    probe_values: dict[str, list[float]]


class GeoClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        settings: Settings | None = None,
    ) -> None:
        resolved_settings = settings or get_settings()
        self._http_client = http_client
        self._retry_count = resolved_settings.http_retry_count
        self._retry_backoff_s = resolved_settings.http_retry_backoff_s
        self._semaphore = asyncio.Semaphore(resolved_settings.concurrency_limit)

    async def fetch_series_matrix(self, gse_id: str) -> SeriesMatrix:
        url = build_series_matrix_url(gse_id)
        raw_bytes = await self._download_bytes(url, resource_label=f"series matrix {gse_id}")
        text = decompress_if_needed(raw_bytes, url)
        return parse_series_matrix(text, gse_id)

    async def fetch_platform_annotation(self, gpl_id: str) -> str:
        url = PLATFORM_SOFT_URL.format(gpl_id=gpl_id)
        raw_bytes = await self.download_bytes(url, resource_label=f"platform {gpl_id}")
        return raw_bytes.decode("utf-8", errors="replace")

    async def download_bytes(self, url: str, resource_label: str) -> bytes:
        return await self._download_bytes(url, resource_label=resource_label)

    async def _download_bytes(self, url: str, resource_label: str) -> bytes:
        request_id = get_request_id()
        last_error: GeoDownloadError | None = None

        for attempt in range(self._retry_count + 1):
            if attempt > 0:
                backoff_s = self._retry_backoff_s * (2 ** (attempt - 1))
                logger.warning(
                    "GEO download retry: resource=%s attempt=%s backoff_s=%s request_id=%s",
                    resource_label,
                    attempt,
                    backoff_s,
                    request_id,
                )
                await asyncio.sleep(backoff_s)

            async with self._semaphore:
                try:
                    response = await self._http_client.get(url, follow_redirects=True)
                    response.raise_for_status()
                except httpx.TimeoutException as exc:
                    last_error = GeoTimeoutError(
                        f"Timed out downloading {resource_label}"
                    )
                    if attempt < self._retry_count:
                        logger.warning(
                            "GEO download timeout: resource=%s attempt=%s request_id=%s",
                            resource_label,
                            attempt + 1,
                            request_id,
                        )
                        continue
                    raise last_error from exc
                except httpx.HTTPStatusError as exc:
                    status_code = exc.response.status_code
                    if status_code == 404:
                        raise GeoNotFoundError(
                            f"GEO resource not found for {resource_label}: HTTP 404"
                        ) from exc
                    last_error = GeoDownloadError(
                        f"Failed to download {resource_label}: HTTP {status_code}"
                    )
                    if is_retriable_status(status_code) and attempt < self._retry_count:
                        continue
                    raise last_error from exc
                except httpx.HTTPError as exc:
                    last_error = GeoDownloadError(
                        f"Failed to download {resource_label}: {exc}"
                    )
                    if attempt < self._retry_count:
                        continue
                    raise last_error from exc

                if len(response.content) == 0:
                    raise GeoDownloadError(f"Empty response while downloading {resource_label}")

                logger.info(
                    "GEO download finished: resource=%s bytes=%s attempt=%s request_id=%s",
                    resource_label,
                    len(response.content),
                    attempt + 1,
                    request_id,
                )
                return response.content

        if last_error is not None:
            raise last_error
        raise GeoDownloadError(f"Failed to download {resource_label}")


def is_retriable_status(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


def build_series_matrix_url(gse_id: str) -> str:
    series_number = int(gse_id[3:])
    folder = f"GSE{series_number // 1000}nnn"
    return (
        f"https://ftp.ncbi.nlm.nih.gov/geo/series/{folder}/{gse_id}/matrix/"
        f"{gse_id}_series_matrix.txt.gz"
    )


def decompress_if_needed(raw_bytes: bytes, url: str) -> str:
    if url.endswith(".gz") or raw_bytes[:2] == b"\x1f\x8b":
        try:
            raw_bytes = gzip.decompress(raw_bytes)
        except OSError as exc:
            raise GeoDownloadError("Failed to decompress series matrix payload") from exc
    return raw_bytes.decode("utf-8", errors="replace")


def parse_series_matrix(text: str, gse_id: str) -> SeriesMatrix:
    gpl_id = extract_series_platform_id(text)
    if SERIES_MATRIX_BEGIN not in text or SERIES_MATRIX_END not in text:
        raise GeoDownloadError(f"Series matrix for {gse_id} is missing table markers")

    table_text = text.split(SERIES_MATRIX_BEGIN, maxsplit=1)[1].split(
        SERIES_MATRIX_END, maxsplit=1
    )[0]
    reader = csv.reader(io.StringIO(table_text.strip()), delimiter="\t")
    try:
        header = next(reader)
    except StopIteration as exc:
        raise GeoDownloadError(f"Series matrix for {gse_id} has an empty table") from exc

    sample_ids = [column.strip().strip('"') for column in header[1:] if column.strip()]
    probe_values: dict[str, list[float]] = {}

    for row in reader:
        if not row:
            continue
        probe_id = row[0].strip().strip('"')
        if not probe_id:
            continue
        values: list[float] = []
        for raw_value in row[1:]:
            cleaned = raw_value.strip().strip('"')
            if cleaned in ("", "NA", "null", "Null", "---"):
                values.append(float("nan"))
                continue
            try:
                values.append(float(cleaned))
            except ValueError:
                values.append(float("nan"))
        probe_values[probe_id] = values

    logger.info(
        "Series matrix parsed: gse_id=%s gpl_id=%s probes=%s samples=%s",
        gse_id,
        gpl_id,
        len(probe_values),
        len(sample_ids),
    )
    return SeriesMatrix(
        gse_id=gse_id,
        gpl_id=gpl_id,
        sample_ids=sample_ids,
        probe_values=probe_values,
    )


def extract_series_platform_id(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("!Series_platform_id"):
            parts = line.split("\t")
            if len(parts) >= 2:
                platform_id = parts[1].strip().strip('"').upper()
                if re.fullmatch(r"GPL\d+", platform_id):
                    return platform_id
    raise GeoDownloadError("Series matrix is missing !Series_platform_id metadata")
