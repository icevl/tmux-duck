"""Background poll that surfaces tmux-rendered interactive prompts to the web UI.

Telegram has a dedicated flow (`handle_interactive_ui`) that catches
AskUserQuestion / ExitPlanMode / permission prompts that exist only in
the agent's TUI (not in the structured transcript). The web UI had no
counterpart, so users on Claude Code saw a blank turn whenever the agent
waited on a choice. This monitor polls each active window's pane, runs
the same `terminal_parser` detection, parses the option list, and
publishes `interactive_prompt` / `interactive_prompt_cleared` events on
the EventBus. The /choose REST endpoint translates a click back into
arrow-key navigation + Enter via tmux_manager.send_keys.

Polling is gated on `bus.subscriber_count > 0` — when no web client is
attached we skip the work entirely.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from ..terminal_parser import (
    ParsedOption,
    ParsedPrompt,
    extract_interactive_content,
    parse_options,
)
from ..tmux_manager import tmux_manager

if TYPE_CHECKING:
    from .events import EventBus

logger = logging.getLogger(__name__)


class InteractivePromptMonitor:
    """Periodically scans each window's tmux pane for interactive prompts."""

    # Consecutive empty/no-prompt captures required before we publish
    # `interactive_prompt_cleared`. A single empty frame (transient capture
    # failure, or a redraw mid-frame) must not retract a still-open prompt.
    _CLEAR_MISS_THRESHOLD = 2

    def __init__(self, bus: "EventBus", *, poll_interval: float = 1.0) -> None:
        self._bus = bus
        self._poll_interval = poll_interval
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()
        # window_id → fingerprint of last published prompt, so we don't
        # re-emit the same event every tick.
        self._last: dict[str, str] = {}
        # window_id → consecutive empty/no-prompt capture count, for debounced
        # clearing. Reset to 0 whenever a prompt is successfully detected.
        self._miss: dict[str, int] = {}

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="interactive-prompt-monitor")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
            self._task = None

    async def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self._tick()
            except Exception:
                logger.exception("InteractivePromptMonitor tick failed")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self._poll_interval
                )
            except asyncio.TimeoutError:
                continue

    async def _tick(self) -> None:
        if self._bus.subscriber_count == 0:
            # Skip polling when nobody is listening — also forget last
            # state so a re-attaching client gets a fresh event.
            self._last.clear()
            self._miss.clear()
            return

        from ..session import session_manager

        # Dormant keys are post-reboot placeholders, not live tmux windows —
        # capturing them always fails, so skip them rather than poll dead ids.
        window_ids = [
            wid
            for wid in session_manager.window_states.keys()
            if not session_manager.is_dormant_key(wid)
        ]
        for window_id in window_ids:
            try:
                await self._check_window(window_id)
            except Exception:
                logger.exception("Interactive check failed for %s", window_id)

    async def _check_window(self, window_id: str) -> None:
        from ..session import session_manager

        state = session_manager.window_states.get(window_id)
        if state is None:
            return
        pane_text = await tmux_manager.capture_pane(window_id)
        content = (
            extract_interactive_content(pane_text, runtime=state.runtime)
            if pane_text
            else None
        )

        parsed = parse_options(content.content) if content is not None else None
        if content is None or parsed is None or not parsed.options:
            # No usable prompt this tick (empty capture, no prompt, or
            # unparseable options). Debounce before retracting an open prompt
            # so a single transient miss can't strand or prematurely clear it.
            await self._note_miss(window_id)
            return

        # Live prompt detected — reset the miss debounce.
        self._miss.pop(window_id, None)

        fingerprint = self._fingerprint(content.name, parsed)
        if self._last.get(window_id) == fingerprint:
            return
        self._last[window_id] = fingerprint

        await self._bus.publish(
            {
                "type": "interactive_prompt",
                "window_id": window_id,
                "runtime": state.runtime,
                "ui_name": content.name,
                "options": [{"label": o.label} for o in parsed.options],
                "current_index": parsed.current_index,
                "content": content.content,
            }
        )

    async def _note_miss(self, window_id: str) -> None:
        """Record a no-prompt tick; publish `interactive_prompt_cleared` only
        after `_CLEAR_MISS_THRESHOLD` consecutive misses."""
        if window_id not in self._last:
            self._miss.pop(window_id, None)
            return
        count = self._miss.get(window_id, 0) + 1
        if count < self._CLEAR_MISS_THRESHOLD:
            self._miss[window_id] = count
            return
        del self._last[window_id]
        self._miss.pop(window_id, None)
        await self._bus.publish(
            {
                "type": "interactive_prompt_cleared",
                "window_id": window_id,
            }
        )

    @staticmethod
    def _fingerprint(name: str, parsed: ParsedPrompt) -> str:
        labels = "|".join(o.label for o in parsed.options)
        return f"{name}::{parsed.current_index}::{labels}"


async def navigate_and_choose(window_id: str, option_index: int, total: int) -> bool:
    """Move the TUI cursor to `option_index` (0-based) and press Enter.

    Uses arrow keys, which works for both numbered (`1. ...`) and radio
    (`◯ ...`) Claude prompts regardless of where the cursor currently
    sits. Overshooting Up at the top is harmless — the TUI clamps.
    """
    if option_index < 0 or total <= 0 or option_index >= total:
        return False
    # Push cursor to top first.
    for _ in range(total):
        if not await tmux_manager.send_keys(
            window_id, "Up", enter=False, literal=False
        ):
            return False
        await asyncio.sleep(0.02)
    for _ in range(option_index):
        if not await tmux_manager.send_keys(
            window_id, "Down", enter=False, literal=False
        ):
            return False
        await asyncio.sleep(0.02)
    # Small settle gap before Enter — the TUI sometimes coalesces a
    # tight Down+Enter and treats Enter as a no-op.
    await asyncio.sleep(0.1)
    return await tmux_manager.send_keys(window_id, "Enter", enter=False, literal=False)


__all__ = ["InteractivePromptMonitor", "navigate_and_choose", "ParsedOption"]
