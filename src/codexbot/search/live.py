"""Live transcript producer and replay helpers for the search queue."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codexbot.session import ParsedTranscriptSession, SessionManager, session_manager
from codexbot.session_monitor import NewMessage
from codexbot.tmux_manager import TmuxManager, TmuxWindow, tmux_manager
from codexbot.transcript_parser import ParsedEntry

from .backfill import (
    DEFAULT_CHUNK_MAX_CHARS,
    DEFAULT_CHUNK_OVERLAP_CHARS,
    documents_for_entry,
    routing_for_source,
)
from .queue import (
    enqueue_documents,
    list_stale_sources,
    parse_document,
    read_watermark,
    record_queue_error,
    replace_stale_sources,
    upsert_watermark,
)
from .contracts import SearchBackfillDocument
from .state import (
    generation_documents_path,
    read_generation_manifest,
    read_generation_metadata,
    write_generation_manifest,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _ResolvedSource:
    source: ParsedTranscriptSession
    window: TmuxWindow


def _is_useful_live_message(msg: NewMessage) -> bool:
    if msg.message_type != "content":
        return False
    if msg.content_type == "completion":
        return False
    return bool(msg.text and msg.text.strip())


def _entry_after_watermark(entry: ParsedEntry, watermark: object | None) -> bool:
    if watermark is None:
        return True
    watermark_offset = getattr(watermark, "transcript_offset", None)
    watermark_index = getattr(watermark, "transcript_index", None)
    if entry.transcript_offset is not None and watermark_offset is not None:
        if entry.transcript_offset != watermark_offset:
            return entry.transcript_offset > watermark_offset
        return (entry.transcript_index or -1) > (watermark_index or -1)
    if entry.transcript_index is not None and watermark_index is not None:
        return entry.transcript_index > watermark_index
    return True


def _identity_key(document: SearchBackfillDocument) -> str:
    identity = document.identity
    return json.dumps(
        identity.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _atomic_write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
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


async def _window_for_id(
    window_id: str,
    state_cwd: str,
    state_name: str,
    state_runtime: str,
    *,
    tmux: TmuxManager,
) -> TmuxWindow:
    try:
        for window in await tmux.list_windows():
            if window.window_id == window_id:
                return window
    except Exception:
        logger.debug("search_live_tmux_window_lookup_failed", exc_info=True)
    return TmuxWindow(
        window_id=window_id,
        window_name=state_name or window_id,
        cwd=state_cwd,
        pane_current_command=state_runtime,
    )


async def resolve_source_for_session(
    session_id: str,
    *,
    session_manager: SessionManager = session_manager,
    tmux_manager: TmuxManager = tmux_manager,
) -> _ResolvedSource | None:
    """Resolve a live monitor session id to parser source plus current window."""
    for window_id, state in list(session_manager.window_states.items()):
        if state.session_id != session_id:
            continue
        source = await session_manager.read_parsed_transcript_for_window(window_id)
        if source is None:
            return None
        window = await _window_for_id(
            window_id,
            state.cwd,
            state.window_name,
            state.runtime,
            tmux=tmux_manager,
        )
        return _ResolvedSource(source=source, window=window)
    return None


def _entry_from_message(msg: NewMessage) -> ParsedEntry:
    return ParsedEntry(
        role=msg.role,
        text=msg.text,
        content_type=msg.content_type,
        tool_use_id=msg.tool_use_id,
        timestamp=msg.timestamp,
        tool_name=msg.tool_name,
        tool_input=msg.tool_input,
        image_data=msg.image_data,
        transcript_offset=msg.transcript_offset,
        transcript_index=msg.transcript_index,
    )


class LiveQueueProducer:
    """Nonblocking SessionMonitor listener that persists useful search queue rows."""

    def __init__(
        self,
        *,
        session_manager: SessionManager = session_manager,
        tmux_manager: TmuxManager = tmux_manager,
    ) -> None:
        self.session_manager = session_manager
        self.tmux_manager = tmux_manager
        self._tasks: set[asyncio.Task[None]] = set()

    async def listener(self, msg: NewMessage) -> None:
        """Schedule queue persistence and return before monitor delivery blocks."""
        task = asyncio.create_task(
            self.enqueue_message(msg),
            name="codexbot-search-live-producer",
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def enqueue_message(self, msg: NewMessage) -> None:
        """Translate one monitor message into durable queue documents."""
        if not _is_useful_live_message(msg):
            return
        try:
            resolved = await resolve_source_for_session(
                msg.session_id,
                session_manager=self.session_manager,
                tmux_manager=self.tmux_manager,
            )
            if resolved is None:
                return
            routing = routing_for_source(resolved.source, resolved.window)
            if routing is None:
                return
            entry = _entry_from_message(msg)
            documents = documents_for_entry(
                source=resolved.source,
                routing=routing,
                entry=entry,
                fallback_order=0,
                chunk_max_chars=DEFAULT_CHUNK_MAX_CHARS,
                chunk_overlap_chars=DEFAULT_CHUNK_OVERLAP_CHARS,
            )
            if not documents:
                return
            await asyncio.to_thread(enqueue_documents, documents)
            await asyncio.to_thread(
                upsert_watermark,
                runtime=routing.runtime,
                session_id=resolved.source.session.session_id,
                transcript_source=resolved.source.transcript_source,
                transcript_offset=msg.transcript_offset,
                transcript_index=msg.transcript_index,
            )
        except Exception as exc:
            logger.warning("search_live_enqueue_failed: %s", type(exc).__name__)
            try:
                await asyncio.to_thread(record_queue_error, exc)
            except Exception:
                logger.debug("search_live_record_error_failed", exc_info=True)

    async def drain_pending(self) -> None:
        """Wait for currently scheduled producer tasks."""
        tasks = list(self._tasks)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def stop(self) -> None:
        """Cancel and await owned producer tasks."""
        tasks = list(self._tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()


async def replay_open_session_queue(
    *,
    session_manager: SessionManager = session_manager,
    tmux_manager: TmuxManager = tmux_manager,
) -> int:
    """Replay current open transcripts from search-owned watermarks."""
    windows = await tmux_manager.list_windows()
    queued_documents = 0
    for window in windows:
        source = await session_manager.read_parsed_transcript_for_window(
            window.window_id
        )
        if source is None:
            continue
        routing = routing_for_source(source, window)
        if routing is None:
            continue
        watermark = await asyncio.to_thread(
            read_watermark,
            routing.runtime,
            source.transcript_source,
        )
        for fallback_order, entry in enumerate(source.entries):
            if not _entry_after_watermark(entry, watermark):
                continue
            documents = documents_for_entry(
                source=source,
                routing=routing,
                entry=entry,
                fallback_order=fallback_order,
                chunk_max_chars=DEFAULT_CHUNK_MAX_CHARS,
                chunk_overlap_chars=DEFAULT_CHUNK_OVERLAP_CHARS,
            )
            if documents:
                await asyncio.to_thread(enqueue_documents, documents)
                queued_documents += len(documents)
            await asyncio.to_thread(
                upsert_watermark,
                runtime=routing.runtime,
                session_id=source.session.session_id,
                transcript_source=source.transcript_source,
                transcript_offset=entry.transcript_offset,
                transcript_index=entry.transcript_index,
            )
            watermark = await asyncio.to_thread(
                read_watermark,
                routing.runtime,
                source.transcript_source,
            )
    return queued_documents


def read_generation_documents(generation_id: str) -> list[SearchBackfillDocument]:
    """Read valid generation documents, ignoring corrupt historical lines."""
    path = generation_documents_path(generation_id)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    documents = []
    for line in lines:
        document = parse_document(line)
        if document is not None:
            documents.append(document)
    return documents


def upsert_generation_documents(
    generation_id: str,
    documents: list[SearchBackfillDocument],
) -> int:
    """Atomically upsert live documents by stable row identity."""
    existing = {
        _identity_key(document): document
        for document in read_generation_documents(generation_id)
    }
    for document in documents:
        existing[_identity_key(document)] = document
    ordered = sorted(
        existing.values(),
        key=lambda doc: (
            getattr(doc.provenance, "transcript_source", ""),
            getattr(doc, "source_order", 0),
            getattr(doc, "chunk_index", 0),
        ),
    )
    _atomic_write_jsonl(
        generation_documents_path(generation_id),
        [document.model_dump(mode="json") for document in ordered],
    )

    manifest = read_generation_manifest(generation_id)
    if manifest is not None:
        session_ids = {
            document.provenance.session_id
            for document in ordered
            if document.provenance.session_id
        }
        counters = manifest.counters.model_copy(
            update={
                "indexed_sessions": max(
                    manifest.counters.indexed_sessions,
                    len(session_ids),
                ),
                "indexed_chunks": len(ordered),
            }
        )
        write_generation_manifest(
            manifest.model_copy(
                update={
                    "counters": counters,
                    "document_count": len(ordered),
                }
            )
        )
    return len(ordered)


async def refresh_stale_sources(
    *,
    session_manager: SessionManager = session_manager,
    tmux_manager: TmuxManager = tmux_manager,
    generation_id: str | None = None,
) -> set[str]:
    """Mark generation document sources whose tmux window is no longer open."""
    generation = read_generation_metadata()
    target_generation_id = generation_id or (
        generation.generation_id if generation is not None else None
    )
    if target_generation_id is None:
        replace_stale_sources([])
        return set()

    active_sources: set[str] = set()
    windows = await tmux_manager.list_windows()
    for window in windows:
        source = await session_manager.read_parsed_transcript_for_window(
            window.window_id
        )
        if source is not None:
            active_sources.add(source.transcript_source)

    stale: list[tuple[str, str, str | None]] = []
    for document in read_generation_documents(target_generation_id):
        source = document.provenance.transcript_source
        if source not in active_sources:
            stale.append(
                (
                    source,
                    document.provenance.runtime,
                    document.provenance.session_id,
                )
            )
    unique_stale = sorted(set(stale))
    replace_stale_sources(unique_stale)
    return {source for source, _runtime, _session_id in unique_stale}


def filter_stale_documents(
    documents: list[SearchBackfillDocument],
) -> list[SearchBackfillDocument]:
    """Hide stale-source documents from normal v1 routing."""
    stale_sources = list_stale_sources()
    return [
        document
        for document in documents
        if document.provenance.transcript_source not in stale_sources
    ]


__all__ = [
    "LiveQueueProducer",
    "filter_stale_documents",
    "read_generation_documents",
    "replay_open_session_queue",
    "resolve_source_for_session",
    "refresh_stale_sources",
    "upsert_generation_documents",
]
