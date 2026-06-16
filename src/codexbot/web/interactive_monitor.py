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
from collections.abc import Callable
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

    def __init__(
        self,
        bus: "EventBus",
        *,
        poll_interval: float = 1.0,
        extra_demand: Callable[[], bool] | None = None,
    ) -> None:
        self._bus = bus
        self._poll_interval = poll_interval
        # Optional predicate that keeps polling alive even when no web client is
        # attached — set by the Attention Router so the agent being blocked on
        # the user is still detected (and pushed) while you're away from the UI.
        self._extra_demand = extra_demand
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
        demand = self._bus.subscriber_count > 0 or (
            self._extra_demand is not None and self._extra_demand()
        )
        if not demand:
            # Skip polling when nobody is listening (no web client and no
            # attention channel) — also forget last state so a re-attaching
            # client gets a fresh event.
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


# How many navigate-then-recheck rounds before we give up landing on the
# target option. Each round corrects for a cursor that moved under us.
_MAX_NAV_ATTEMPTS = 4


def _forward_steps(current_index: int, target_index: int, total: int) -> int:
    """Down-key presses to move the cursor from ``current`` to ``target``.

    The Claude/Codex pickers wrap (Down past the last option returns to the
    first) and advance exactly one option per press, so a forward-only count
    reaches any target regardless of where the cursor sits — unlike pressing
    Up, which we observed wrapping unpredictably.
    """
    return (target_index - current_index) % total


async def _read_current_prompt(window_id: str) -> ParsedPrompt | None:
    """Capture the pane and parse the live option list + cursor position."""
    from ..session import session_manager

    state = session_manager.window_states.get(window_id)
    if state is None:
        return None
    pane_text = await tmux_manager.capture_pane(window_id)
    if not pane_text:
        return None
    content = extract_interactive_content(pane_text, runtime=state.runtime)
    if content is None:
        return None
    return parse_options(content.content)


async def navigate_and_choose(window_id: str, option_index: int, total: int) -> bool:
    """Move the TUI cursor onto ``option_index`` (0-based) and press Enter.

    Reads the cursor's *actual* position from the live pane and steps Down to
    the target, then re-reads to confirm before committing. This is resilient
    to the picker wrapping and to the cursor having moved since the prompt was
    surfaced. Critically, if we can't confirm the cursor is on the target we
    return False WITHOUT pressing Enter — better to fail the choice than to
    submit the wrong option (the old "press Up to reach the top" approach broke
    exactly here, because Up wraps instead of clamping).
    """
    if option_index < 0 or total <= 0 or option_index >= total:
        return False

    for _ in range(_MAX_NAV_ATTEMPTS):
        parsed = await _read_current_prompt(window_id)
        if parsed is None or not parsed.options:
            return False
        count = len(parsed.options)
        if option_index >= count:
            return False  # the menu changed under us
        if parsed.current_index == option_index:
            break
        steps = _forward_steps(parsed.current_index, option_index, count)
        for _ in range(steps):
            if not await tmux_manager.send_keys(
                window_id, "Down", enter=False, literal=False
            ):
                return False
            await asyncio.sleep(0.02)
        await asyncio.sleep(0.08)  # let the TUI settle before re-reading
    else:
        return False  # never confirmed on the target — do not commit

    # Final confirmation: only commit when the cursor is provably on the target.
    parsed = await _read_current_prompt(window_id)
    if parsed is None or parsed.current_index != option_index:
        return False
    # Small settle gap — the TUI sometimes coalesces a tight move+Enter.
    await asyncio.sleep(0.1)
    return await tmux_manager.send_keys(window_id, "Enter", enter=False, literal=False)


__all__ = [
    "InteractivePromptMonitor",
    "navigate_and_choose",
    "ParsedOption",
    "_forward_steps",
]
