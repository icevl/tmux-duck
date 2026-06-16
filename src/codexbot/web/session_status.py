"""Server-side, bus-fed source of truth for per-window agent status.

The web UI has always derived "is this session busy / waiting on me / done"
on the client, by folding the WebSocket event stream into ad-hoc state in
``App.tsx``. That works for a single attached browser but the status dies on
reload, can't be read without a browser, and can't be shared with the Telegram
or headless paths.

``SessionStatusTracker`` lifts that state machine onto the server. It
subscribes to the same :class:`EventBus` the clients consume (as an *internal*
subscriber, so it doesn't keep the pane-stream / prompt-poll loops awake when
no browser is attached), folds the stream into one small status per tmux
window, and re-publishes a ``session_status`` event whenever a window's visible
status changes. Two consumers ride on top:

  * the Mission Control grid renders the snapshot and the live events;
  * the Attention Router (later) decides when to notify from the same state.

The transitions mirror the client logic in ``App.tsx`` so the sidebar and the
dashboard agree:

  * agent activity (assistant text / tool use / pane stream) -> ``running``;
  * an interactive prompt (permission / AskUserQuestion / plan) -> ``blocked``;
  * a ``completion`` after running -> ``done`` (finished, not yet acknowledged);
  * a watchdog re-armed by activity, expiring -> ``done`` (safety net for a
    ``completion`` we never saw, e.g. dropped across a reconnect gap).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .events import EventBus

logger = logging.getLogger(__name__)

# Mirror of the client-side BUSY_WATCHDOG_MS (App.tsx): a pure safety net for
# turns whose `completion` event we never see. Each activity re-arms it; on
# expiry we treat the turn as ended. 90s comfortably covers a long tool call.
BUSY_WATCHDOG_SECONDS = 90.0
# How often the watchdog sweeps for expired `running` windows.
WATCHDOG_TICK_SECONDS = 10.0
# Interactive-prompt content can be long; keep the summary short for the grid.
PROMPT_SUMMARY_MAX_CHARS = 160

# Event types we fold into status. Everything else (including our own
# `session_status` echoes) is ignored.
_HANDLED_TYPES = frozenset(
    {
        "message",
        "stream",
        "completion",
        "interactive_prompt",
        "interactive_prompt_cleared",
    }
)


class Status(str, Enum):
    """Visible status of a session, in attention-priority order."""

    blocked = "blocked"  # waiting on the user (permission / AskUserQuestion / plan)
    running = "running"  # agent is working
    done = "done"  # turn finished, not yet acknowledged by a viewer
    idle = "idle"  # quiet, nothing pending


@dataclass
class WindowStatus:
    """Tracked status for one tmux window."""

    status: Status = Status.idle
    since: float = 0.0  # epoch seconds when we entered `status`
    prompt_summary: str | None = None  # pending interactive-prompt text, if blocked
    last_activity: float = 0.0  # epoch seconds of the last activity event

    @property
    def attention(self) -> bool:
        """Whether this window is waiting on the user right now."""
        return self.status is Status.blocked

    def to_payload(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "status_since": self.since,
            "attention": self.attention,
            "prompt_summary": self.prompt_summary,
        }


def _event_ts(event: dict[str, Any]) -> float:
    ts = event.get("ts")
    return float(ts) if isinstance(ts, (int, float)) else time.time()


def _is_activity(event: dict[str, Any]) -> bool:
    """True for events that mean the agent is actively producing output.

    Mirrors the `isActivity` predicate in App.tsx: pane stream chunks, plus
    assistant text and any tool use/result message. Plain user echoes don't
    count as the agent working.
    """
    etype = event.get("type")
    if etype == "stream":
        return True
    if etype == "message":
        return (
            event.get("role") == "assistant"
            or bool(event.get("tool_name"))
            or bool(event.get("tool_use_id"))
        )
    return False


def _prompt_summary(event: dict[str, Any]) -> str | None:
    """Short, human-readable label for a pending interactive prompt."""
    name = (event.get("ui_name") or "").strip()
    content = (event.get("content") or "").strip()
    first_line = content.splitlines()[0].strip() if content else ""
    text = name or first_line
    if not text:
        return None
    if len(text) > PROMPT_SUMMARY_MAX_CHARS:
        text = text[: PROMPT_SUMMARY_MAX_CHARS - 1].rstrip() + "…"
    return text


class SessionStatusTracker:
    """Folds the event bus into a per-window status and republishes changes."""

    def __init__(
        self,
        bus: "EventBus",
        *,
        watchdog_seconds: float = BUSY_WATCHDOG_SECONDS,
    ) -> None:
        self._bus = bus
        self._watchdog_seconds = watchdog_seconds
        self._status: dict[str, WindowStatus] = {}
        self._queue: asyncio.Queue[dict[str, Any]] | None = None
        self._consume_task: asyncio.Task[None] | None = None
        self._watchdog_task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        if self._consume_task is not None and not self._consume_task.done():
            return
        self._stop.clear()
        self._queue = self._bus.subscribe(internal=True)
        self._consume_task = asyncio.create_task(
            self._consume_loop(), name="session-status-consumer"
        )
        self._watchdog_task = asyncio.create_task(
            self._watchdog_loop(), name="session-status-watchdog"
        )

    async def stop(self) -> None:
        self._stop.set()
        if self._queue is not None:
            self._bus.unsubscribe(self._queue)
            self._queue = None
        for task in (self._consume_task, self._watchdog_task):
            if task is None:
                continue
            task.cancel()
            try:
                await asyncio.wait_for(task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            except Exception:  # noqa: BLE001
                logger.exception("session status task did not stop cleanly")
        self._consume_task = None
        self._watchdog_task = None

    # -- reads -------------------------------------------------------------

    def snapshot(self) -> dict[str, WindowStatus]:
        """Copy of the current per-window status (window_id -> WindowStatus)."""
        return dict(self._status)

    def get(self, window_id: str) -> WindowStatus | None:
        return self._status.get(window_id)

    async def acknowledge(self, window_id: str) -> None:
        """Mark a ``done`` window as seen (-> idle).

        Called when a viewer opens the window, so the dashboard's "finished
        while you were away" affordance clears. A no-op for any other status.
        """
        st = self._status.get(window_id)
        if st is not None and st.status is Status.done:
            await self._set(window_id, Status.idle, time.time())

    def forget(self, window_id: str) -> None:
        """Drop tracked state for a window that no longer exists."""
        self._status.pop(window_id, None)

    # -- consume loop ------------------------------------------------------

    async def _consume_loop(self) -> None:
        while not self._stop.is_set():
            queue = self._queue
            if queue is None:
                return
            try:
                event = await queue.get()
            except asyncio.CancelledError:
                raise
            etype = event.get("type")
            if etype == self._bus.SHUTDOWN_EVENT_TYPE:
                if self._stop.is_set() or self._bus.is_closed:
                    return
                # The bus dropped us as a slow subscriber (not a shutdown).
                # Re-subscribe so a transient backpressure spike doesn't kill
                # status tracking for the rest of the process's life.
                logger.warning("session status: re-subscribing after bus sentinel")
                self._queue = self._bus.subscribe(internal=True)
                continue
            try:
                await self._handle(event)
            except Exception:  # noqa: BLE001
                logger.exception("session status: failed to handle %r", etype)

    async def _handle(self, event: dict[str, Any]) -> None:
        etype = event.get("type")
        if etype not in _HANDLED_TYPES:
            return
        wid = event.get("window_id")
        if not isinstance(wid, str) or not wid:
            return
        now = _event_ts(event)
        st = self._status.get(wid)
        if st is None:
            st = WindowStatus()
            self._status[wid] = st
        st.last_activity = max(st.last_activity, now)

        if etype == "interactive_prompt":
            st.prompt_summary = _prompt_summary(event)
            await self._set(wid, Status.blocked, now)
        elif etype == "interactive_prompt_cleared":
            st.prompt_summary = None
            if st.status is Status.blocked:
                # The user answered or the agent moved on. Treat it as resumed;
                # a following completion / watchdog resolves to done / idle.
                await self._set(wid, Status.running, now)
        elif etype == "completion":
            st.prompt_summary = None
            # Mirror the client `wasBusy` gate: only a turn we actually saw
            # running becomes "done". A stray completion on an idle window is
            # ignored; a completion while blocked just ends the wait.
            if st.status is Status.running:
                await self._set(wid, Status.done, now)
            elif st.status is Status.blocked:
                await self._set(wid, Status.idle, now)
        elif _is_activity(event) and st.status is not Status.blocked:
            # Activity re-arms the watchdog (via last_activity above). Only
            # publish when it actually flips us into running.
            if st.status is not Status.running:
                await self._set(wid, Status.running, now)

    # -- watchdog ----------------------------------------------------------

    async def _watchdog_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=WATCHDOG_TICK_SECONDS)
                return  # stop was set
            except asyncio.TimeoutError:
                pass
            await self._sweep_expired(time.time())

    async def _sweep_expired(self, now: float) -> None:
        """End any ``running`` window whose last activity is older than the
        watchdog window — a safety net for a ``completion`` we never saw."""
        for wid, st in list(self._status.items()):
            if (
                st.status is Status.running
                and now - st.last_activity > self._watchdog_seconds
            ):
                await self._set(wid, Status.done, now)

    # -- mutation ----------------------------------------------------------

    async def _set(self, window_id: str, status: Status, now: float) -> None:
        st = self._status.get(window_id)
        if st is None:
            st = WindowStatus()
            self._status[window_id] = st
        if st.status is status:
            return
        st.status = status
        st.since = now
        if status is not Status.blocked:
            st.prompt_summary = None
        await self._publish(window_id, st)

    async def _publish(self, window_id: str, st: WindowStatus) -> None:
        payload: dict[str, Any] = {"type": "session_status", "window_id": window_id}
        payload.update(st.to_payload())
        await self._bus.publish(payload)


__all__ = [
    "BUSY_WATCHDOG_SECONDS",
    "SessionStatusTracker",
    "Status",
    "WindowStatus",
]
