import hashlib
import json
import logging
import threading
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from geo_expression_service.config import Settings
from geo_expression_service.domain.models import ExpressionResult
from geo_expression_service.exceptions import CachedNegativeEntryError
from geo_expression_service.logging import get_request_id

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
CacheLayer = Literal["raw", "map", "result"]


@dataclass(frozen=True)
class _MemoryEntry:
    storage_key: str
    layer: CacheLayer
    size_bytes: int


class CacheStore:
    def __init__(self, settings: Settings) -> None:
        self._cache_dir = settings.cache_dir
        self._max_entries = settings.cache_max_entries
        self._max_bytes = settings.cache_max_bytes
        self._memory_index: OrderedDict[str, _MemoryEntry] = OrderedDict()
        self._tracked_bytes = 0
        self._lock = threading.RLock()
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def get_raw(self, url: str) -> bytes | None:
        storage_key = build_raw_key(url)
        metadata = self._read_entry_metadata(storage_key, "raw")
        if metadata is None:
            self._log_cache_event("raw", storage_key, "miss")
            return None
        if metadata.get("negative"):
            raise CachedNegativeEntryError(
                layer="raw",
                key=storage_key,
                message=str(metadata.get("error", "Cached raw download failure")),
            )
        raw_bytes = self._read_raw_bytes(storage_key)
        if raw_bytes is None:
            self._delete_entry_files(storage_key)
            self._log_cache_event("raw", storage_key, "miss")
            return None
        self._touch_memory_entry(storage_key, "raw", metadata.get("size_bytes", len(raw_bytes)))
        self._log_cache_event("raw", storage_key, "hit")
        return raw_bytes

    def store_raw(self, url: str, data: bytes) -> None:
        storage_key = build_raw_key(url)
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "key": storage_key,
            "layer": "raw",
            "url": url,
            "negative": False,
            "size_bytes": len(data),
            "fetched_at": datetime.now(UTC).isoformat(),
        }
        self._write_raw_entry(storage_key, metadata, data)
        self._register_entry(storage_key, "raw", len(data))
        self._log_cache_event("raw", storage_key, "store")

    def store_raw_negative(self, url: str, error: str) -> None:
        storage_key = build_raw_key(url)
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "key": storage_key,
            "layer": "raw",
            "url": url,
            "negative": True,
            "error": error,
            "size_bytes": len(error.encode("utf-8")),
            "fetched_at": datetime.now(UTC).isoformat(),
        }
        self._write_metadata_only(storage_key, metadata)
        self._register_entry(storage_key, "raw", metadata["size_bytes"])
        self._log_cache_event("raw", storage_key, "negative_store")

    def get_map(self, gpl_id: str) -> dict[str, list[str]] | None:
        storage_key = build_map_key(gpl_id)
        metadata = self._read_entry_metadata(storage_key, "map")
        if metadata is None:
            self._log_cache_event("map", storage_key, "miss")
            return None
        if metadata.get("negative"):
            raise CachedNegativeEntryError(
                layer="map",
                key=storage_key,
                message=str(metadata.get("error", "Cached map parse failure")),
            )
        probe_to_symbols = metadata.get("probe_to_symbols")
        if not isinstance(probe_to_symbols, dict):
            self._delete_entry_files(storage_key)
            self._log_cache_event("map", storage_key, "miss")
            return None
        normalized_map = {
            str(probe_id): [str(symbol) for symbol in symbols]
            for probe_id, symbols in probe_to_symbols.items()
        }
        self._touch_memory_entry(
            storage_key,
            "map",
            metadata.get("size_bytes", self._estimate_json_size(metadata)),
        )
        self._log_cache_event("map", storage_key, "hit")
        return normalized_map

    def store_map(self, gpl_id: str, probe_to_symbols: dict[str, list[str]]) -> None:
        storage_key = build_map_key(gpl_id)
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "key": storage_key,
            "layer": "map",
            "gpl_id": gpl_id.upper(),
            "negative": False,
            "probe_to_symbols": probe_to_symbols,
            "size_bytes": 0,
        }
        metadata["size_bytes"] = self._estimate_json_size(metadata)
        self._write_metadata_only(storage_key, metadata)
        self._register_entry(storage_key, "map", metadata["size_bytes"])
        self._log_cache_event("map", storage_key, "store")

    def store_map_negative(self, gpl_id: str, error: str) -> None:
        storage_key = build_map_key(gpl_id)
        metadata = {
            "schema_version": SCHEMA_VERSION,
            "key": storage_key,
            "layer": "map",
            "gpl_id": gpl_id.upper(),
            "negative": True,
            "error": error,
            "size_bytes": len(error.encode("utf-8")),
        }
        self._write_metadata_only(storage_key, metadata)
        self._register_entry(storage_key, "map", metadata["size_bytes"])
        self._log_cache_event("map", storage_key, "negative_store")

    def get_result(self, gse_id: str, gene_symbols: list[str]) -> ExpressionResult | None:
        storage_key = build_result_key(gse_id, gene_symbols)
        metadata = self._read_entry_metadata(storage_key, "result")
        if metadata is None:
            self._log_cache_event("result", storage_key, "miss")
            return None
        if metadata.get("negative"):
            raise CachedNegativeEntryError(
                layer="result",
                key=storage_key,
                message=str(metadata.get("error", "Cached result failure")),
            )
        payload = metadata.get("expression_result")
        if not isinstance(payload, dict):
            self._delete_entry_files(storage_key)
            self._log_cache_event("result", storage_key, "miss")
            return None
        try:
            result = ExpressionResult.model_validate(payload)
        except Exception:
            self._delete_entry_files(storage_key)
            self._log_cache_event("result", storage_key, "miss")
            return None
        self._touch_memory_entry(
            storage_key,
            "result",
            metadata.get("size_bytes", self._estimate_json_size(metadata)),
        )
        self._log_cache_event("result", storage_key, "hit")
        return result

    def store_result(
        self,
        gse_id: str,
        gene_symbols: list[str],
        result: ExpressionResult,
    ) -> None:
        storage_key = build_result_key(gse_id, gene_symbols)
        payload = result.model_copy(update={"cached": False}).model_dump(mode="json")
        metadata: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "key": storage_key,
            "layer": "result",
            "gse_id": gse_id.upper(),
            "genes": sorted(symbol.upper() for symbol in gene_symbols),
            "negative": False,
            "expression_result": payload,
            "size_bytes": 0,
        }
        metadata["size_bytes"] = self._estimate_json_size(metadata)
        self._write_metadata_only(storage_key, metadata)
        self._register_entry(storage_key, "result", metadata["size_bytes"])
        self._log_cache_event("result", storage_key, "store")

    def _read_entry_metadata(
        self,
        storage_key: str,
        expected_layer: CacheLayer,
    ) -> dict[str, Any] | None:
        with self._lock:
            metadata_path = self._metadata_path(storage_key)
            if not metadata_path.exists():
                return None
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._delete_entry_files(storage_key)
                return None
            if metadata.get("schema_version") != SCHEMA_VERSION:
                self._delete_entry_files(storage_key)
                return None
            if metadata.get("layer") != expected_layer:
                self._delete_entry_files(storage_key)
                return None
            return metadata

    def _read_raw_bytes(self, storage_key: str) -> bytes | None:
        with self._lock:
            raw_path = self._raw_bytes_path(storage_key)
            if not raw_path.exists():
                return None
            try:
                return raw_path.read_bytes()
            except OSError:
                return None

    def _write_raw_entry(
        self,
        storage_key: str,
        metadata: dict[str, Any],
        data: bytes,
    ) -> None:
        with self._lock:
            self._metadata_path(storage_key).write_text(
                json.dumps(metadata, ensure_ascii=True),
                encoding="utf-8",
            )
            self._raw_bytes_path(storage_key).write_bytes(data)

    def _write_metadata_only(self, storage_key: str, metadata: dict[str, Any]) -> None:
        with self._lock:
            self._metadata_path(storage_key).write_text(
                json.dumps(metadata, ensure_ascii=True),
                encoding="utf-8",
            )

    def _register_entry(self, storage_key: str, layer: CacheLayer, size_bytes: int) -> None:
        with self._lock:
            if storage_key in self._memory_index:
                previous_entry = self._memory_index.pop(storage_key)
                self._tracked_bytes -= previous_entry.size_bytes
            self._memory_index[storage_key] = _MemoryEntry(
                storage_key=storage_key,
                layer=layer,
                size_bytes=size_bytes,
            )
            self._tracked_bytes += size_bytes
            self._memory_index.move_to_end(storage_key)
            self._evict_if_needed()

    def _touch_memory_entry(
        self,
        storage_key: str,
        layer: CacheLayer,
        size_bytes: int,
    ) -> None:
        with self._lock:
            if storage_key not in self._memory_index:
                self._memory_index[storage_key] = _MemoryEntry(
                    storage_key=storage_key,
                    layer=layer,
                    size_bytes=size_bytes,
                )
                self._tracked_bytes += size_bytes
            self._memory_index.move_to_end(storage_key)
            metadata_path = self._metadata_path(storage_key)
            if metadata_path.exists():
                try:
                    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                    metadata["last_access_at"] = datetime.now(UTC).isoformat()
                    metadata_path.write_text(
                        json.dumps(metadata, ensure_ascii=True),
                        encoding="utf-8",
                    )
                except (OSError, json.JSONDecodeError):
                    pass

    def _evict_if_needed(self) -> None:
        while len(self._memory_index) > self._max_entries or self._tracked_bytes > self._max_bytes:
            if not self._memory_index:
                break
            _, entry = self._memory_index.popitem(last=False)
            self._tracked_bytes -= entry.size_bytes
            self._delete_entry_files(entry.storage_key)
            logger.info(
                "Cache eviction finished: key=%s layer=%s entries=%s bytes=%s request_id=%s",
                entry.storage_key,
                entry.layer,
                len(self._memory_index),
                self._tracked_bytes,
                get_request_id(),
            )

    def _delete_entry_files(self, storage_key: str) -> None:
        metadata_path = self._metadata_path(storage_key)
        raw_path = self._raw_bytes_path(storage_key)
        for path in (metadata_path, raw_path):
            if path.exists():
                path.unlink(missing_ok=True)

    def _metadata_path(self, storage_key: str) -> Path:
        return self._cache_dir / f"{sanitize_storage_key(storage_key)}.json"

    def _raw_bytes_path(self, storage_key: str) -> Path:
        return self._cache_dir / f"{sanitize_storage_key(storage_key)}.bin"

    def _log_cache_event(self, layer: CacheLayer, storage_key: str, event: str) -> None:
        logger.info(
            "Cache %s finished: layer=%s storage_key=%s event=%s request_id=%s",
            event,
            layer,
            storage_key,
            event,
            get_request_id(),
        )

    @staticmethod
    def _estimate_json_size(payload: dict[str, Any]) -> int:
        return len(json.dumps(payload, ensure_ascii=True).encode("utf-8"))


def build_raw_key(url: str) -> str:
    url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
    return f"raw:{url_hash}"


def build_map_key(gpl_id: str) -> str:
    return f"map:{gpl_id.upper()}"


def build_result_key(gse_id: str, gene_symbols: list[str]) -> str:
    genes_hash = hashlib.sha256(
        ",".join(sorted(symbol.upper() for symbol in gene_symbols)).encode("utf-8")
    ).hexdigest()[:16]
    return f"result:{gse_id.upper()}:{genes_hash}"


def sanitize_storage_key(storage_key: str) -> str:
    return storage_key.replace(":", "_")


class NullCacheStore:
    """No-op cache for tests that bypass persistence."""

    def get_raw(self, url: str) -> bytes | None:
        return None

    def store_raw(self, url: str, data: bytes) -> None:
        return None

    def store_raw_negative(self, url: str, error: str) -> None:
        return None

    def get_map(self, gpl_id: str) -> dict[str, list[str]] | None:
        return None

    def store_map(self, gpl_id: str, probe_to_symbols: dict[str, list[str]]) -> None:
        return None

    def store_map_negative(self, gpl_id: str, error: str) -> None:
        return None

    def get_result(self, gse_id: str, gene_symbols: list[str]) -> ExpressionResult | None:
        return None

    def store_result(
        self,
        gse_id: str,
        gene_symbols: list[str],
        result: ExpressionResult,
    ) -> None:
        return None
