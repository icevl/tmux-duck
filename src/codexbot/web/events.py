"""In-process pub/sub for the web transport.

Subscribers attach an asyncio queue and receive structured events. A single
publisher hooks into `SessionMonitor` and translates `NewMessage` records into
JSON-serializable payloads.

Event shapes (all dicts with `"type"` discriminator):

    {"type": "message", "window_id": "@12", "session_id": "...", "role": "...",
     "text": "...", "content_type": "text", "is_complete": true,
     "tool_name": "...", "tool_input": {...}, "tool_use_id": "...",
     "timestamp": "2026-05-20T10:00:00Z", "transcript_offset": 123,
     "transcript_index": 0, "ts": 1731600000.123, "seq": 1}

    {"type": "completion", "window_id": "@12", "session_id": "...",
     "turn_id": 3, "ts": ..., "seq": 2}

    {"type": "skill_hints_changed", "runtime": "codex", "window_id": "@12",
     "session_id": "...", "source": "transcript", "ts": ..., "seq": 3}

    {"type": "sessions_changed", "ts": ..., "seq": 4}
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from ..session_monitor import NewMessage

logger = logging.getLogger(__name__)


class EventBus:
    """Fan-out hub for web subscribers."""

    SHUTDOWN_EVENT_TYPE = "__shutdown__"

    def __init__(self, *, queue_size: int = 256) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        # Internal subscribers (e.g. the SessionStatusTracker) consume the same
        # fan-out as web clients but must NOT count as "a client is watching":
        # `subscriber_count` gates the pane-streaming and interactive-prompt
        # poll loops, which should still idle when no browser is attached.
        self._internal: set[asyncio.Queue[dict[str, Any]]] = set()
        self._queue_size = queue_size
        self._closed = False
        self._next_seq = 1

    def subscribe(self, *, internal: bool = False) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=self._queue_size)
        if self._closed:
            self._put_shutdown(q)
            return q
        self._subscribers.add(q)
        if internal:
            self._internal.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._subscribers.discard(q)
        self._internal.discard(q)

    @property
    def subscriber_count(self) -> int:
        """Number of client (non-internal) subscribers currently attached."""
        return len(self._subscribers) - len(self._internal)

    @property
    def is_closed(self) -> bool:
        return self._closed

    def _put_shutdown(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        event = {"type": self.SHUTDOWN_EVENT_TYPE}
        while True:
            try:
                q.put_nowait(event)
                return
            except asyncio.QueueFull:
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    return

    async def close(self) -> None:
        """Wake all subscribers so websocket handlers can exit during shutdown."""
        if self._closed:
            return
        self._closed = True
        for q in list(self._subscribers):
            self._put_shutdown(q)

    async def publish(self, event: dict[str, Any]) -> None:
        if self._closed:
            return
        event.setdefault("ts", time.time())
        event.setdefault("seq", self._next_seq)
        self._next_seq += 1
        dead: list[asyncio.Queue[dict[str, Any]]] = []
        for q in self._subscribers:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Dropping slow subscriber (queue full)")
                dead.append(q)
        for q in dead:
            self._subscribers.discard(q)
            self._internal.discard(q)
            # Don't just orphan the queue: the /api/ws handler is parked on
            # `queue.get()` and would block forever, so the browser would keep
            # a live-but-dead socket and silently receive nothing. Push the
            # shutdown sentinel so the handler wakes, exits, and the client
            # auto-reconnects (and then catches up missed history).
            self._put_shutdown(q)

    async def publish_sessions_changed(self) -> None:
        await self.publish({"type": "sessions_changed"})

    async def publish_message(self, msg: NewMessage, window_id: str | None) -> None:
        payload: dict[str, Any] = {
            "type": "completion" if msg.message_type == "completion" else "message",
            "window_id": window_id or "",
            "session_id": msg.session_id,
            "role": msg.role,
            "text": msg.text,
            "content_type": msg.content_type,
            "is_complete": msg.is_complete,
            "tool_name": msg.tool_name,
            "tool_input": msg.tool_input,
            "tool_use_id": msg.tool_use_id,
            "turn_id": msg.turn_id,
            "timestamp": msg.timestamp,
            "transcript_offset": msg.transcript_offset,
            "transcript_index": msg.transcript_index,
        }
        await self.publish(payload)


async def session_monitor_listener(bus: EventBus, msg: NewMessage) -> None:
    """Adapter passed to `SessionMonitor.add_listener`."""
    # Lazy import to avoid circular import with bot.py.
    from ..session import session_manager

    window_id: str | None = None
    for wid, ws in session_manager.window_states.items():
        if ws.session_id == msg.session_id:
            window_id = wid
            break
    if window_id is None:
        # No live window currently maps to this session_id (session resolving,
        # just resumed under a new id, or a transient race). The event still
        # publishes with session_id, so ChatView's session_id fallback can
        # render it for the active session — but window_id-keyed consumers
        # (e.g. the busy indicator) can't route it. Log for observability.
        logger.warning(
            "No window mapped to session %s; event published without window_id",
            msg.session_id,
        )
    await bus.publish_message(msg, window_id=window_id)
