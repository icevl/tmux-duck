"""Search-owned derived state helpers."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from codexbot.utils import atomic_write_json, codexbot_dir

from .contracts import (
    SearchBackfillManifest,
    SearchGenerationMetadata,
    SearchWorkerStatus,
)


SEARCH_SCHEMA_VERSION = 1
GENERATION_METADATA_FILENAME = "generation.json"
ACTIVE_GENERATION_METADATA_FILENAME = GENERATION_METADATA_FILENAME
GENERATIONS_DIRNAME = "generations"
GENERATION_DOCUMENTS_FILENAME = "documents.jsonl"
GENERATION_MANIFEST_FILENAME = "manifest.json"
WORKER_STATUS_FILENAME = "worker_status.json"


def search_dir() -> Path:
    """Return the directory reserved for derived search state."""
    return codexbot_dir() / "search"


def active_generation_metadata_path() -> Path:
    """Return the active search generation metadata path."""
    return search_dir() / GENERATION_METADATA_FILENAME


def generation_metadata_path() -> Path:
    """Return the active search generation metadata path."""
    return active_generation_metadata_path()


def generations_dir() -> Path:
    """Return the parent directory for inactive and active generations."""
    return search_dir() / GENERATIONS_DIRNAME


def _validate_generation_id(generation_id: str) -> str:
    if not generation_id or Path(generation_id).name != generation_id:
        raise ValueError("generation_id must be a non-empty path segment")
    return generation_id


def generation_dir(generation_id: str) -> Path:
    """Return the search-owned directory for one derived generation."""
    return generations_dir() / _validate_generation_id(generation_id)


def generation_documents_path(generation_id: str) -> Path:
    """Return the JSONL document artifact path for one generation."""
    return generation_dir(generation_id) / GENERATION_DOCUMENTS_FILENAME


def generation_manifest_path(generation_id: str) -> Path:
    """Return the manifest artifact path for one generation."""
    return generation_dir(generation_id) / GENERATION_MANIFEST_FILENAME


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


def read_generation_manifest(generation_id: str) -> SearchBackfillManifest | None:
    """Read a completed generation manifest, ignoring incomplete generations."""
    path = generation_manifest_path(generation_id)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(raw, dict):
        return None

    try:
        manifest = SearchBackfillManifest(**raw)
    except ValidationError:
        return None

    if manifest.schema_version != SEARCH_SCHEMA_VERSION:
        return None
    if manifest.generation.schema_version != SEARCH_SCHEMA_VERSION:
        return None
    if manifest.generation.generation_id != generation_id:
        return None
    if not manifest.completed:
        return None
    return manifest


def write_generation_manifest(manifest: SearchBackfillManifest) -> None:
    """Atomically persist a generation manifest under search-owned state."""
    atomic_write_json(
        generation_manifest_path(manifest.generation.generation_id),
        manifest.model_dump(mode="json"),
    )


def activate_generation(
    manifest: SearchBackfillManifest,
) -> SearchGenerationMetadata:
    """Atomically mark a completed inactive generation as the active one."""
    generation_id = manifest.generation.generation_id
    if manifest.schema_version != SEARCH_SCHEMA_VERSION:
        raise ValueError("generation manifest schema is unsupported")
    if manifest.generation.schema_version != SEARCH_SCHEMA_VERSION:
        raise ValueError("generation metadata schema is unsupported")
    if not manifest.completed:
        raise ValueError("generation manifest is incomplete")
    if read_generation_manifest(generation_id) is None:
        raise ValueError("generation manifest is missing or incomplete")
    if not generation_documents_path(generation_id).exists():
        raise ValueError("generation documents are missing")

    active = manifest.generation.model_copy(update={"active": True})
    atomic_write_json(active_generation_metadata_path(), active.model_dump(mode="json"))
    return active


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
    "ACTIVE_GENERATION_METADATA_FILENAME",
    "GENERATION_DOCUMENTS_FILENAME",
    "GENERATION_METADATA_FILENAME",
    "GENERATION_MANIFEST_FILENAME",
    "GENERATIONS_DIRNAME",
    "SEARCH_SCHEMA_VERSION",
    "WORKER_STATUS_FILENAME",
    "active_generation_metadata_path",
    "generation_dir",
    "generation_documents_path",
    "generation_manifest_path",
    "generation_metadata_path",
    "generations_dir",
    "activate_generation",
    "read_generation_manifest",
    "read_generation_metadata",
    "read_worker_status",
    "search_dir",
    "worker_status_path",
    "write_generation_manifest",
    "write_worker_status",
]
