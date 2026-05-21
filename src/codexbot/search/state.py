"""Search-owned derived state helpers."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from codexbot.utils import atomic_write_json, codexbot_dir

from .contracts import SearchGenerationMetadata, SearchWorkerStatus


SEARCH_SCHEMA_VERSION = 1
GENERATION_METADATA_FILENAME = "generation.json"
WORKER_STATUS_FILENAME = "worker_status.json"


def search_dir() -> Path:
    """Return the directory reserved for derived search state."""
    return codexbot_dir() / "search"


def generation_metadata_path() -> Path:
    """Return the active search generation metadata path."""
    return search_dir() / GENERATION_METADATA_FILENAME


def worker_status_path() -> Path:
    """Return the search worker status path."""
    return search_dir() / WORKER_STATUS_FILENAME


def read_generation_metadata() -> SearchGenerationMetadata | None:
    """Read active generation metadata, treating missing or stale data as absent."""
    path = generation_metadata_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(raw, dict):
        return None

    try:
        metadata = SearchGenerationMetadata(**raw)
    except ValidationError:
        return None

    if metadata.schema_version != SEARCH_SCHEMA_VERSION:
        return None
    if not metadata.active:
        return None
    return metadata


def read_worker_status() -> SearchWorkerStatus | None:
    """Read worker status, treating missing or invalid data as absent."""
    path = worker_status_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(raw, dict):
        return None

    try:
        return SearchWorkerStatus(**raw)
    except ValidationError:
        return None


def write_worker_status(status: SearchWorkerStatus) -> None:
    """Atomically persist search worker status under search-owned state."""
    atomic_write_json(worker_status_path(), status.model_dump(mode="json"))


__all__ = [
    "GENERATION_METADATA_FILENAME",
    "SEARCH_SCHEMA_VERSION",
    "WORKER_STATUS_FILENAME",
    "generation_metadata_path",
    "read_generation_metadata",
    "read_worker_status",
    "search_dir",
    "worker_status_path",
    "write_worker_status",
]
