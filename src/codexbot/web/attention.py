"""Attention Router — turn status transitions into "the agent needs you" pings.

The whole point of TmuxDuck is that you walk away while the agent works. The
missing half of that loop is being pulled back *exactly* when you're needed,
instead of polling the UI yourself. The Attention Router is that half.

It rides on the server-side status core: the :class:`SessionStatusTracker`
already folds the event stream into a per-window status and publishes
``session_status`` events. The router subscribes to those (as an *internal* bus
subscriber, so it doesn't keep client-gated poll loops awake on its own),
applies a small notification policy, and dispatches to the configured channels.

Policy (all tuning is module constants below, not env vars):

  * ``blocked`` (agent waiting on a permission / question / plan) -> notify
    immediately; this is the highest-value interrupt.
  * ``done`` after a turn that ran at least ``TURN_DONE_MIN_DURATION_SECONDS``
    -> notify "finished"; short turns are noise.
  * A per-(window, reason) cooldown collapses floods.
  * During ``QUIET_HOURS`` we stay silent.

Delivery is a pluggable :class:`Notifier`. Today the one implementation is
:class:`TelegramNotifier` — the channel this project is actually driven from on
a phone. Web push is a future notifier (needs an installed PWA + HTTPS, which a
loopback self-hosted box doesn't have), and slots in beside Telegram without
touching the policy engine.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from telegram import Bot

    from .events import EventBus

logger = logging.getLogger(__name__)

# A turn must run at least this long before its completion is worth a ping;
# below it, the agent answered in seconds and you don't need interrupting.
TURN_DONE_MIN_DURATION_SECONDS = 60.0
# At most one ping per (window, reason) within this window — collapses a window
# that re-blocks repeatedly into a single nudge.
PER_WINDOW_COOLDOWN_SECONDS = 30.0
# Local-time hours [start, end) during which we stay silent. (23, 8) == 23:00
# through 07:59. Set to None to never suppress.
QUIET_HOURS: tuple[int, int] | None = (23, 8)


def in_quiet_hours(hour: int, window: tuple[int, int] | None = QUIET_HOURS) -> bool:
    """Whether ``hour`` (0–23) falls inside the quiet window.

    Handles windows that wrap past midnight, e.g. (23, 8) covers 23 and 0–7.
    """
    if window is None:
        return False
    start, end = window
    if start == end:
        return False
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


@dataclass
class AttentionItem:
    """One thing that wants the user's attention, ready to deliver."""

    window_id: str
    reason: str  # "blocked" | "turn_done"
    title: str
    body: str


class Notifier(Protocol):
    """A delivery channel for attention items."""

    async def deliver(self, item: AttentionItem) -> None: ...


class TelegramNotifier:
    """Send attention pings into the session's Telegram forum topic.

    Reuses the bot already wired into the web server and the existing
    window->topic bindings, so a ping lands in the same thread the user already
    drives that session from. No new dependency, no extra config.
    """

    def __init__(self, bot: "Bot") -> None:
        self._bot = bot

    async def deliver(self, item: AttentionItem) -> None:
        from ..session import session_manager

        text = f"🔔 {item.title}\n{item.body}" if item.body else f"🔔 {item.title}"
        sent = False
        for user_id, thread_id, window_id in session_manager.iter_thread_bindings():
            if window_id != item.window_id:
                continue
            chat_id = session_manager.resolve_chat_id(user_id, thread_id)
            try:
                await self._bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    message_thread_id=thread_id or None,
                )
                sent = True
            except Exception:  # noqa: BLE001
                logger.exception(
                    "attention: telegram delivery failed window=%s chat=%s",
                    item.window_id,
                    chat_id,
                )
        if not sent:
            logger.debug(
                "attention: no telegram topic bound for window %s", item.window_id
            )


class BrowserNotifier:
    """Deliver attention items to the web UI by re-publishing them on the bus.

    The server can't raise a browser notification itself — only page JS can — so
    this notifier publishes a normalized ``attention`` event and the open web
    client shows it (gated on the user's notification toggle). Foreground only by
    nature: nothing is delivered when no tab is connected. Scoped to web-visible
    sessions; connector-owned windows aren't in the UI, so they're skipped.
    """

    def __init__(self, bus: "EventBus") -> None:
        self._bus = bus

    async def deliver(self, item: AttentionItem) -> None:
        from ..session import session_manager

        ws = session_manager.window_states.get(item.window_id)
        if ws is not None and ws.connector_id:
            return
        await self._bus.publish(
            {
                "type": "attention",
                "window_id": item.window_id,
                "reason": item.reason,
                "title": item.title,
                "body": item.body,
            }
        )


class AttentionRouter:
    """Folds ``session_status`` events into notifications via the notifiers."""

    def __init__(
        self,
        bus: "EventBus",
        notifiers: list[Notifier],
        *,
        turn_done_min_seconds: float = TURN_DONE_MIN_DURATION_SECONDS,
        cooldown_seconds: float = PER_WINDOW_COOLDOWN_SECONDS,
        quiet_hours: tuple[int, int] | None = QUIET_HOURS,
    ) -> None:
        self._bus = bus
        self._notifiers = notifiers
        self._turn_done_min_seconds = turn_done_min_seconds
        self._cooldown_seconds = cooldown_seconds
        self._quiet_hours = quiet_hours
        # window_id -> epoch seconds the current run started (last "running").
        self._running_since: dict[str, float] = {}
        # (window_id, reason) -> last delivery time, for the cooldown.
        self._last_notified: dict[tuple[str, str], float] = {}
        self._queue: "asyncio.Queue[dict[str, Any]] | None" = None
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()

    def is_active(self) -> bool:
        """Whether the router has any channel to deliver through.

        Used to gate the always-on interactive-prompt poll: without a channel
        there's nobody to notify, so don't pay for background pane captures.
        """
        return bool(self._notifiers)

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._stop.clear()
        self._queue = self._bus.subscribe(internal=True)
        self._task = asyncio.create_task(self._run(), name="attention-router")

    async def stop(self) -> None:
        self._stop.set()
        if self._queue is not None:
            self._bus.unsubscribe(self._queue)
            self._queue = None
        if self._task is not None:
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
            except Exception:  # noqa: BLE001
                logger.exception("attention router did not stop cleanly")
            self._task = None

    # -- consume loop ------------------------------------------------------

    async def _run(self) -> None:
        while not self._stop.is_set():
            queue = self._queue
            if queue is None:
                return
            try:
                event = await queue.get()
            except asyncio.CancelledError:
                raise
            if event.get("type") == self._bus.SHUTDOWN_EVENT_TYPE:
                if self._stop.is_set() or self._bus.is_closed:
                    return
                logger.warning("attention: re-subscribing after bus sentinel")
                self._queue = self._bus.subscribe(internal=True)
                continue
            if event.get("type") != "session_status":
                continue
            try:
                await self._handle_status(event)
            except Exception:  # noqa: BLE001
                logger.exception("attention: failed to handle status event")

    async def _handle_status(self, event: dict[str, Any]) -> None:
        wid = event.get("window_id")
        status = event.get("status")
        if not isinstance(wid, str) or not wid:
            return
        now = float(event.get("status_since") or time.time())

        if status == "running":
            self._running_since[wid] = now
            return
        if status == "blocked":
            await self._maybe_notify(
                wid, "blocked", now, prompt=event.get("prompt_summary")
            )
            return
        if status == "done":
            started = self._running_since.pop(wid, now)
            if now - started >= self._turn_done_min_seconds:
                await self._maybe_notify(wid, "turn_done", now, duration=now - started)
            return
        if status == "idle":
            self._running_since.pop(wid, None)

    async def _maybe_notify(
        self,
        window_id: str,
        reason: str,
        now: float,
        *,
        prompt: str | None = None,
        duration: float | None = None,
    ) -> None:
        if in_quiet_hours(time.localtime(now).tm_hour, self._quiet_hours):
            logger.debug("attention: suppressed %s/%s (quiet hours)", window_id, reason)
            return
        key = (window_id, reason)
        last = self._last_notified.get(key)
        if last is not None and now - last < self._cooldown_seconds:
            return
        self._last_notified[key] = now

        item = self._build_item(window_id, reason, prompt=prompt, duration=duration)
        for notifier in self._notifiers:
            try:
                await notifier.deliver(item)
            except Exception:  # noqa: BLE001
                logger.exception("attention: notifier failed for %s", window_id)

    def _build_item(
        self,
        window_id: str,
        reason: str,
        *,
        prompt: str | None,
        duration: float | None,
    ) -> AttentionItem:
        from ..session import session_manager

        name = session_manager.get_display_name(window_id) or window_id
        ws = session_manager.window_states.get(window_id)
        runtime = ws.runtime if ws is not None else ""
        title = f"{name} · {runtime}".rstrip(" ·") if runtime else name
        if reason == "blocked":
            body = prompt or "Waiting for your input"
        else:
            mins = max(1, round((duration or 0) / 60))
            body = f"Finished after {mins}m"
        return AttentionItem(window_id=window_id, reason=reason, title=title, body=body)


__all__ = [
    "AttentionItem",
    "AttentionRouter",
    "BrowserNotifier",
    "Notifier",
    "TelegramNotifier",
    "in_quiet_hours",
]
