"""Parser-backed open-session search backfill.

The v1 corpus is deliberately scoped to currently open tmux windows. Historical
transcript discovery remains in session resolution; this module only consumes
the resolved parser-level entries for windows that are live now.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from codexbot.session import ParsedTranscriptSession, SessionManager, session_manager
from codexbot.tmux_manager import TmuxManager, TmuxWindow, tmux_manager
from codexbot.transcript_parser import ParsedEntry

from .contracts import (
    SearchBackfillDocument,
    SearchBackfillManifest,
    SearchCounters,
    SearchGenerationMetadata,
    SearchRoutingMetadata,
    SearchRowIdentity,
    TranscriptProvenance,
)
from .state import (
    SEARCH_SCHEMA_VERSION,
    generation_documents_path,
    write_generation_manifest,
)

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_MAX_CHARS = 4000
DEFAULT_CHUNK_OVERLAP_CHARS = 200


@dataclass
class OpenSessionBackfillResult:
    """Documents and counters produced by one open-session backfill pass."""

    documents: list[SearchBackfillDocument]
    counters: SearchCounters
    errors: list[str]


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def new_generation_id() -> str:
    """Return a filesystem-safe generation id."""
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")


def _chunk_text(
    text: str,
    *,
    chunk_max_chars: int,
    chunk_overlap_chars: int,
) -> list[str]:
    text = text.strip()
    if not text:
        return []

    max_chars = max(1, chunk_max_chars)
    overlap = max(0, min(chunk_overlap_chars, max_chars - 1))
    step = max(1, max_chars - overlap)

    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + max_chars)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start += step
    return chunks


def _source_order(entry: ParsedEntry, fallback: int) -> int:
    if entry.transcript_offset is not None:
        return entry.transcript_offset
    if entry.transcript_index is not None:
        return entry.transcript_index
    return fallback


def routing_for_source(
    source: ParsedTranscriptSession,
    window: TmuxWindow,
) -> SearchRoutingMetadata | None:
    state = source.state
    cwd = state.cwd or window.cwd
    if not cwd:
        return None
    return SearchRoutingMetadata(
        window_id=window.window_id,
        name=state.window_name or window.window_name or window.window_id,
        cwd=cwd,
        runtime=state.runtime or "codex",
        session_id=source.session.session_id,
        pinned=state.pinned,
        sort_order=state.sort_order,
    )


def documents_for_entry(
    *,
    source: ParsedTranscriptSession,
    routing: SearchRoutingMetadata,
    entry: ParsedEntry,
    fallback_order: int,
    chunk_max_chars: int,
    chunk_overlap_chars: int,
) -> list[SearchBackfillDocument]:
    chunks = _chunk_text(
        entry.text,
        chunk_max_chars=chunk_max_chars,
        chunk_overlap_chars=chunk_overlap_chars,
    )
    if not chunks:
        return []

    provenance = TranscriptProvenance(
        runtime=routing.runtime,
        session_id=source.session.session_id,
        transcript_source=source.transcript_source,
        transcript_offset=entry.transcript_offset,
        transcript_index=entry.transcript_index,
        role=entry.role,
        content_type=entry.content_type,
        tool_name=entry.tool_name,
        tool_use_id=entry.tool_use_id,
        source_event_kind="parsed_entry",
        timestamp=entry.timestamp,
    )
    source_order = _source_order(entry, fallback_order)
    chunk_count = len(chunks)
    return [
        SearchBackfillDocument(
            identity=SearchRowIdentity.from_provenance(
                provenance,
                chunk_index=chunk_index,
            ),
            provenance=provenance,
            routing=routing,
            text=chunk,
            timestamp=entry.timestamp,
            source_order=source_order,
            chunk_index=chunk_index,
            chunk_count=chunk_count,
        )
        for chunk_index, chunk in enumerate(chunks)
    ]


def documents_for_source(
    source: ParsedTranscriptSession,
    window: TmuxWindow,
    *,
    chunk_max_chars: int,
    chunk_overlap_chars: int,
) -> list[SearchBackfillDocument]:
    routing = routing_for_source(source, window)
    if routing is None:
        return []

    documents: list[SearchBackfillDocument] = []
    for fallback_order, entry in enumerate(source.entries):
        documents.extend(
            documents_for_entry(
                source=source,
                routing=routing,
                entry=entry,
                fallback_order=fallback_order,
                chunk_max_chars=chunk_max_chars,
                chunk_overlap_chars=chunk_overlap_chars,
            )
        )
    return documents


def _safe_error_summary(window_id: str, exc: BaseException) -> str:
    return f"{window_id}: {type(exc).__name__}"


def _identity_key(document: SearchBackfillDocument) -> str:
    return json.dumps(
        document.identity.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def dedupe_documents_by_identity(
    documents: Iterable[SearchBackfillDocument],
) -> list[SearchBackfillDocument]:
    """Collapse duplicate transcript chunk identities before writing a generation."""
    unique: dict[str, SearchBackfillDocument] = {}
    for document in documents:
        unique[_identity_key(document)] = document
    return sorted(
        unique.values(),
        key=lambda doc: (
            getattr(doc.provenance, "transcript_source", ""),
            getattr(doc, "source_order", 0),
            getattr(doc, "chunk_index", 0),
        ),
    )


async def collect_open_session_documents(
    *,
    session_manager: SessionManager = session_manager,
    tmux_manager: TmuxManager = tmux_manager,
    chunk_max_chars: int = DEFAULT_CHUNK_MAX_CHARS,
    chunk_overlap_chars: int = DEFAULT_CHUNK_OVERLAP_CHARS,
) -> OpenSessionBackfillResult:
    """Build chunk documents for currently open tmux-backed sessions."""
    windows = await tmux_manager.list_windows()
    documents: list[SearchBackfillDocument] = []
    indexed_sessions = 0
    failed_items = 0
    errors: list[str] = []

    for window in windows:
        try:
            source = await session_manager.read_parsed_transcript_for_window(
                window.window_id
            )
        except Exception as exc:
            failed_items += 1
            errors.append(_safe_error_summary(window.window_id, exc))
            logger.exception(
                "search_backfill_window_failed window_id=%s", window.window_id
            )
            continue

        if source is None:
            failed_items += 1
            continue

        session_documents = documents_for_source(
            source,
            window,
            chunk_max_chars=chunk_max_chars,
            chunk_overlap_chars=chunk_overlap_chars,
        )
        if session_documents:
            indexed_sessions += 1
            documents.extend(session_documents)

    documents = dedupe_documents_by_identity(documents)
    counters = SearchCounters(
        open_sessions=len(windows),
        indexed_sessions=indexed_sessions,
        indexed_chunks=len(documents),
        failed_items=failed_items,
    )
    return OpenSessionBackfillResult(
        documents=documents,
        counters=counters,
        errors=errors,
    )


def _atomic_write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        suffix=".tmp",
        prefix=f".{path.name}.",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for row in rows:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


async def materialize_backfill_generation(
    generation_id: str,
    *,
    session_manager: SessionManager = session_manager,
    tmux_manager: TmuxManager = tmux_manager,
    chunk_max_chars: int = DEFAULT_CHUNK_MAX_CHARS,
    chunk_overlap_chars: int = DEFAULT_CHUNK_OVERLAP_CHARS,
) -> SearchBackfillManifest:
    """Write inactive parser-backed documents and manifest for one generation."""
    result = await collect_open_session_documents(
        session_manager=session_manager,
        tmux_manager=tmux_manager,
        chunk_max_chars=chunk_max_chars,
        chunk_overlap_chars=chunk_overlap_chars,
    )
    generation = SearchGenerationMetadata(
        schema_version=SEARCH_SCHEMA_VERSION,
        generation_id=generation_id,
        created_at=_now_iso(),
        active=False,
    )
    manifest = SearchBackfillManifest(
        schema_version=SEARCH_SCHEMA_VERSION,
        generation=generation,
        counters=result.counters,
        document_count=len(result.documents),
        errors=result.errors,
    )

    _atomic_write_jsonl(
        generation_documents_path(generation_id),
        (doc.model_dump(mode="json") for doc in result.documents),
    )
    write_generation_manifest(manifest)
    return manifest


async def materialize_initial_backfill(
    *,
    session_manager: SessionManager = session_manager,
    tmux_manager: TmuxManager = tmux_manager,
) -> SearchBackfillManifest:
    """Materialize a new inactive generation for the initial worker run."""
    return await materialize_backfill_generation(
        new_generation_id(),
        session_manager=session_manager,
        tmux_manager=tmux_manager,
    )


__all__ = [
    "DEFAULT_CHUNK_MAX_CHARS",
    "DEFAULT_CHUNK_OVERLAP_CHARS",
    "OpenSessionBackfillResult",
    "collect_open_session_documents",
    "documents_for_entry",
    "documents_for_source",
    "materialize_backfill_generation",
    "materialize_initial_backfill",
    "new_generation_id",
    "routing_for_source",
]
