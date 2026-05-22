"""Live transcript producer and replay helpers for the search queue."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

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
    read_watermark,
    record_queue_error,
    upsert_watermark,
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


__all__ = [
    "LiveQueueProducer",
    "replay_open_session_queue",
    "resolve_source_for_session",
]
