"""Detect whether the user is actively working before running heavy indexing.

The search backfill is expensive (CPU+GPU) and runs as a subprocess. We
don't want it competing for resources while an agent is generating code,
running tests, building, etc. This module gives the supervisor a single
boolean signal — `is_workload_idle()` — that combines three observations
across all open tmux windows:

1. **Codex/Claude currently generating** — the runtime prints a "(esc to
   interrupt)" status line at the bottom of its pane. We sample the pane
   and look for it via the existing `parse_status_line()`.
2. **Pane runs an obviously-heavy command** — `pane_current_command` is
   matched against a deny-list of build/test tools. We deliberately use
   deny-list rather than allow-list: shells, editors, runtime wrappers
   (claude/codex/python/node) all look alike to tmux and depending on
   them being whitelisted made the supervisor stuck in deferred forever.
3. **Recent message activity** — we track the last NewMessage timestamp
   from `SessionMonitor`. If a message landed within the idle window,
   we consider the workload non-idle even if the pane just settled.

All thresholds and lists live at the top of this module — tweak in
code rather than via env (Mike pushed back on .env clutter).
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from ..terminal_parser import parse_status_line
from ..tmux_manager import tmux_manager

if TYPE_CHECKING:
    from ..session_monitor import NewMessage, SessionMonitor

logger = logging.getLogger(__name__)

# How long the workload must look quiet (no agent activity, no heavy
# process, no recent message) before we consider it OK to start a fresh
# backfill or resume a paused one.
IDLE_TIMEOUT_SECONDS = 30.0
# Was 120s — too aggressive for chat-heavy workflows. With one
# user/agent message per minute (typical conversation pace) the tracker
# never aged out, so the supervisor kept the pause flag set indefinitely
# and the live queue accumulated for hours. 30s is enough for the agent
# to finish a response burst without competing with merge_insert.

# Commands that are obviously a build, test, or other resource-heavy
# workload. When tmux reports any of these as the foreground process in
# a pane, the supervisor treats the whole workload as busy. Everything
# else (shells, editors, claude/codex/node wrappers, REPLs) is allowed
# to coexist with indexing — the "esc to interrupt" status-line check
# and the recent-message check still catch active agents independently.
#
# Match is done on a normalized basename: lowercase, trailing ".exe" /
# ".cmd" stripped so claude.exe, claude, claude.cmd all look alike.
BUSY_PROC_COMMANDS: frozenset[str] = frozenset(
    {
        "pytest",
        "py.test",
        "unittest",
        "ruff",
        "mypy",
        "black",
        "cargo",
        "rustc",
        "go",
        "make",
        "cmake",
        "ninja",
        "gcc",
        "clang",
        "g++",
        "ld",
        "tsc",
        "vite",
        "webpack",
        "rollup",
        "esbuild",
        "next",
        "nuxt",
        "remix",
        "vitest",
        "jest",
        "playwright",
        "cypress",
        "npm",
        "yarn",
        "pnpm",
        "bun",
        "rspec",
        "rake",
        "rails",
        "bundle",
        "gradle",
        "mvn",
        "ant",
        "docker",
        "kubectl",
        "terraform",
        "ansible",
        "ansible-playbook",
        "swift",
        "xcodebuild",
        "lldb",
        "gdb",
    }
)


def _normalize_command(command: str | None) -> str:
    if not command:
        return ""
    name = command.strip().lower()
    for suffix in (".exe", ".cmd", ".bat"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return name


class IdleTracker:
    """Observes session_monitor NewMessage events to remember the last
    moment an agent said anything. The supervisor's idle check reads
    `seconds_since_last_message` and treats fresh messages as activity.

    Lives in the main bot process — only the supervisor uses it; the
    search worker subprocess polls the pause file written by the
    supervisor and never reads this directly."""

    def __init__(self) -> None:
        self._last_message_monotonic: float | None = None

    async def listener(self, _msg: "NewMessage") -> None:
        self._last_message_monotonic = time.monotonic()

    def seconds_since_last_message(self) -> float | None:
        if self._last_message_monotonic is None:
            return None
        return max(0.0, time.monotonic() - self._last_message_monotonic)

    def attach(self, monitor: "SessionMonitor") -> None:
        monitor.add_listener(self.listener)

    def detach(self, monitor: "SessionMonitor") -> None:
        monitor.remove_listener(self.listener)


def _command_is_busy(command: str | None) -> bool:
    return _normalize_command(command) in BUSY_PROC_COMMANDS


async def _pane_text(window_id: str) -> str | None:
    try:
        return await tmux_manager.capture_pane(window_id, with_ansi=False)
    except Exception as exc:  # noqa: BLE001
        logger.debug("idle_detector capture_pane(%s) failed: %s", window_id, exc)
        return None


async def is_workload_idle(tracker: IdleTracker | None = None) -> bool:
    """Return True only when nothing is happening across all tmux windows.

    `tracker` is optional. When passed, recent NewMessage activity also
    counts as busy. Failing to enumerate tmux is treated as "idle" so we
    don't permanently block backfill on transient tmux errors.
    """
    try:
        windows = await tmux_manager.list_windows()
    except Exception as exc:  # noqa: BLE001
        logger.debug("idle_detector list_windows failed: %s", exc)
        return True

    if tracker is not None:
        age = tracker.seconds_since_last_message()
        if age is not None and age < IDLE_TIMEOUT_SECONDS:
            return False

    for window in windows:
        if _command_is_busy(window.pane_current_command):
            return False
        pane_text = await _pane_text(window.window_id)
        if pane_text and parse_status_line(pane_text):
            return False
    return True


__all__ = [
    "BUSY_PROC_COMMANDS",
    "IDLE_TIMEOUT_SECONDS",
    "IdleTracker",
    "is_workload_idle",
]
