"""Search-owned derived state helpers."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from codexbot.utils import codexbot_dir

from .contracts import SearchGenerationMetadata


SEARCH_SCHEMA_VERSION = 1
GENERATION_METADATA_FILENAME = "generation.json"


def search_dir() -> Path:
    """Return the directory reserved for derived search state."""
    return codexbot_dir() / "search"


def generation_metadata_path() -> Path:
    """Return the active search generation metadata path."""
    return search_dir() / GENERATION_METADATA_FILENAME


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


__all__ = [
    "GENERATION_METADATA_FILENAME",
    "SEARCH_SCHEMA_VERSION",
    "generation_metadata_path",
    "read_generation_metadata",
    "search_dir",
]
