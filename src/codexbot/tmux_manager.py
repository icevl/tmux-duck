"""Tmux session/window management.

Provides async-friendly operations on a single tmux session:
  - list_windows / find_window_by_id / find_window_by_name: discover windows.
  - capture_pane: read terminal content (plain or with ANSI colors).
  - send_keys: forward user input or control keys to a window.
  - create_window / kill_window: lifecycle management.

Read-mostly queries (window list, pane capture) call the `tmux` binary
directly with a minimal `-F` format; mutations go through libtmux. Every
blocking call runs on a small dedicated thread pool (`TmuxManager._run`) so
tmux forks never queue behind — or starve — the default executor.

Key class: TmuxManager (singleton instantiated as `tmux_manager`).
"""

from __future__ import annotations

import asyncio
import functools
import logging
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, TypeVar

import libtmux

from .config import SENSITIVE_ENV_VARS, config

if TYPE_CHECKING:
    from .runtimes.base import AgentRuntime

logger = logging.getLogger(__name__)

T = TypeVar("T")

# `tmux list-panes -s` returns every pane of the session in ONE fork, with
# exactly the fields we need. libtmux's object model instead re-runs
# `list-windows` plus a per-window `list-panes` with ~200 format variables on
# every attribute access, which turned a single `find_window_by_id` into 16+
# tmux forks for a 15-window session.
_LIST_PANES_FIELD_SEP = "\x1f"
_LIST_PANES_FORMAT = _LIST_PANES_FIELD_SEP.join(
    (
        "#{window_id}",
        "#{window_name}",
        "#{pane_current_path}",
        "#{pane_current_command}",
        "#{pane_pid}",
        "#{pane_active}",
    )
)


@dataclass
class TmuxWindow:
    """Information about a tmux window."""

    window_id: str
    window_name: str
    cwd: str  # Current working directory
    pane_current_command: str = ""  # Process running in active pane
    pane_pid: int | None = None  # OS pid of the active pane's process


class TmuxManager:
    """Manages tmux windows for Codex sessions."""

    def __init__(self, session_name: str | None = None):
        """Initialize tmux manager.

        Args:
            session_name: Name of the tmux session to use (default from config)
        """
        self.session_name = session_name or config.tmux_session_name
        self._server: libtmux.Server | None = None
        # Dedicated, deliberately small pool for tmux forks. Sharing the
        # default executor let pane polling starve unrelated blocking work
        # (transcript reads via aiofiles) whenever tmux got slow.
        self._executor = ThreadPoolExecutor(
            max_workers=config.tmux_max_concurrency, thread_name_prefix="tmux"
        )
        self._windows_cache: list[TmuxWindow] | None = None
        self._windows_cache_at: float = 0.0
        self._windows_lock: asyncio.Lock | None = None
        self._windows_lock_loop: asyncio.AbstractEventLoop | None = None

    async def _run(self, fn: Callable[..., T], *args: Any) -> T:
        """Run a blocking tmux/libtmux call on the dedicated tmux executor."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, functools.partial(fn, *args))

    def _tmux(self, *args: str) -> subprocess.CompletedProcess[str] | None:
        """Run a tmux command synchronously.

        Returns the completed process, or None when tmux could not run at all
        (missing binary, or it exceeded `tmux_command_timeout_seconds`).
        """
        try:
            return subprocess.run(
                ["tmux", *args],
                capture_output=True,
                text=True,
                check=False,
                timeout=config.tmux_command_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                "tmux %s timed out after %.0fs",
                args[0] if args else "",
                config.tmux_command_timeout_seconds,
            )
            return None
        except OSError as e:
            logger.warning("tmux %s failed to start: %s", args[0] if args else "", e)
            return None

    @property
    def server(self) -> libtmux.Server:
        """Get or create tmux server connection."""
        if self._server is None:
            self._server = libtmux.Server()
        return self._server

    def get_session(self) -> libtmux.Session | None:
        """Get the tmux session if it exists."""
        try:
            return self.server.sessions.get(session_name=self.session_name)
        except Exception:
            return None

    def get_or_create_session(self) -> libtmux.Session:
        """Get existing session or create a new one."""
        session = self.get_session()
        if session:
            self._scrub_session_env(session)
            self._set_session_env(session)
            return session

        # Create new session with main window named specifically
        session = self.server.new_session(
            session_name=self.session_name,
            start_directory=str(Path.home()),
        )
        # Rename the default window to the main window name
        if session.windows:
            session.windows[0].rename_window(config.tmux_main_window_name)
        self._scrub_session_env(session)
        self._set_session_env(session)
        return session

    @staticmethod
    def _scrub_session_env(session: libtmux.Session) -> None:
        """Remove sensitive env vars from the tmux session environment.

        Prevents new windows (and their child processes like Codex)
        from inheriting secrets such as TELEGRAM_BOT_TOKEN.
        """
        for var in SENSITIVE_ENV_VARS:
            # Scrub both global server env and session env.
            # Tmux server-level variables can leak into newly created windows
            # even if session-level values were unset.
            try:
                session.server.unset_environment(var)
            except Exception:
                pass
            try:
                session.unset_environment(var)
            except Exception:
                pass  # var not set in session env — nothing to remove
            try:
                subprocess.run(
                    ["tmux", "set-environment", "-gru", var],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

    @staticmethod
    def _set_session_env(session: libtmux.Session) -> None:
        """Disable shell update prompts in spawned windows.

        oh-my-zsh's "[Y/n] update?" prompt eats the first keystroke of the
        agent start command (so `claude` arrives as `laude`). Exporting these
        into the session env makes new windows skip the prompt entirely.
        """
        env = {"DISABLE_AUTO_UPDATE": "true", "DISABLE_UPDATE_PROMPT": "true"}
        for name, value in env.items():
            try:
                session.set_environment(name, value)
            except Exception:
                pass
            try:
                subprocess.run(
                    ["tmux", "set-environment", "-g", name, value],
                    check=False,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except Exception:
                pass

    @staticmethod
    def _parse_list_panes(stdout: str) -> list[TmuxWindow]:
        """Turn `list-panes -F _LIST_PANES_FORMAT` output into TmuxWindow rows."""
        windows: list[TmuxWindow] = []
        for line in stdout.splitlines():
            parts = line.split(_LIST_PANES_FIELD_SEP)
            if len(parts) < 6:
                continue
            window_id, name, cwd, pane_cmd, pane_pid, pane_active = parts[:6]
            # The active pane stands for the window (matches libtmux's
            # `window.active_pane` that callers relied on).
            if pane_active != "1":
                continue
            # Skip the main window (placeholder window)
            if name == config.tmux_main_window_name:
                continue
            windows.append(
                TmuxWindow(
                    window_id=window_id,
                    window_name=name,
                    cwd=cwd,
                    pane_current_command=pane_cmd,
                    pane_pid=int(pane_pid) if pane_pid.isdigit() else None,
                )
            )
        return windows

    def _sync_list_windows(self) -> list[TmuxWindow] | None:
        """One `tmux list-panes -s` fork for the whole session.

        Returns None when tmux itself could not be run (callers then keep
        serving the previous snapshot); an empty list when the session or
        server does not exist.
        """
        proc = self._tmux(
            "list-panes",
            "-s",
            "-t",
            f"={self.session_name}",  # '=' → exact session-name match
            "-F",
            _LIST_PANES_FORMAT,
        )
        if proc is None:
            return None
        if proc.returncode != 0:
            logger.debug(
                "tmux list-panes rc=%s: %s", proc.returncode, proc.stderr.strip()
            )
            return []
        return self._parse_list_panes(proc.stdout)

    def _windows_cache_lock(self) -> asyncio.Lock:
        # Bind the lock to the running loop lazily; the singleton outlives
        # test event loops.
        loop = asyncio.get_running_loop()
        if self._windows_lock is None or self._windows_lock_loop is not loop:
            self._windows_lock = asyncio.Lock()
            self._windows_lock_loop = loop
        return self._windows_lock

    def _cached_windows(self, max_age: float) -> list[TmuxWindow] | None:
        if self._windows_cache is None:
            return None
        if time.monotonic() - self._windows_cache_at >= max_age:
            return None
        return list(self._windows_cache)

    def invalidate_windows_cache(self) -> None:
        """Forget the cached window list (after create/kill/rename)."""
        self._windows_cache = None
        self._windows_cache_at = 0.0

    async def list_windows(self, *, max_age: float | None = None) -> list[TmuxWindow]:
        """List all agent windows in the session (active pane per window).

        The result is cached for `config.tmux_cache_ttl_seconds` and concurrent
        callers share a single refresh, so the many pollers (session monitor,
        pane streaming, status polling, interactive monitor) together cost one
        tmux fork per TTL. Pass `max_age=0` to force a fresh read.

        Returns:
            List of TmuxWindow with window info and cwd
        """
        ttl = config.tmux_cache_ttl_seconds if max_age is None else max(0.0, max_age)
        cached = self._cached_windows(ttl)
        if cached is not None:
            return cached

        async with self._windows_cache_lock():
            cached = self._cached_windows(ttl)
            if cached is not None:
                return cached
            windows = await self._run(self._sync_list_windows)
            if windows is None:
                # tmux failed/timed out: serve the last snapshot rather than
                # pretend every window vanished (which would unbind sessions).
                return list(self._windows_cache or [])
            self._windows_cache = windows
            self._windows_cache_at = time.monotonic()
            return list(windows)

    async def find_window_by_name(self, window_name: str) -> TmuxWindow | None:
        """Find a window by its name.

        Args:
            window_name: The window name to match

        Returns:
            TmuxWindow if found, None otherwise
        """
        windows = await self.list_windows()
        for window in windows:
            if window.window_name == window_name:
                return window
        logger.debug("Window not found by name: %s", window_name)
        return None

    async def find_window_by_id(self, window_id: str) -> TmuxWindow | None:
        """Find a window by its tmux window ID (e.g. '@0', '@12').

        Args:
            window_id: The tmux window ID to match

        Returns:
            TmuxWindow if found, None otherwise
        """
        windows = await self.list_windows()
        for window in windows:
            if window.window_id == window_id:
                return window
        logger.debug("Window not found by id: %s", window_id)
        return None

    async def capture_pane(self, window_id: str, with_ansi: bool = False) -> str | None:
        """Capture the visible text content of a window's active pane.

        Args:
            window_id: The window ID to capture
            with_ansi: If True, capture with ANSI color codes

        Returns:
            The captured text, or None on failure.
        """
        # Run on the tmux executor, not via asyncio.create_subprocess_exec:
        # asyncio forks/execs synchronously on the loop thread, and under load
        # a spawn can take hundreds of ms — long enough to stall every
        # WebSocket and Telegram handler.
        return await self._run(self._sync_capture_pane, window_id, with_ansi)

    def _sync_capture_pane(self, window_id: str, with_ansi: bool) -> str | None:
        args = ["capture-pane", "-p", "-t", window_id]
        if with_ansi:
            args.insert(1, "-e")
        proc = self._tmux(*args)
        if proc is None:
            return None
        if proc.returncode != 0:
            # Window no longer exists (dormant placeholder, closed window, bad
            # id). Benign and expected — callers treat None as "no capture".
            # Logging this above DEBUG floods the log when a poller iterates
            # stale window_states keys.
            logger.debug("capture-pane %s failed: %s", window_id, proc.stderr.strip())
            return None
        out = proc.stdout
        if not with_ansi and out.endswith("\n"):
            # Plain captures historically came from libtmux as "\n".join(lines),
            # i.e. without the trailing newline tmux prints.
            out = out[:-1]
        return out

    async def send_keys(
        self, window_id: str, text: str, enter: bool = True, literal: bool = True
    ) -> bool:
        """Send keys to a specific window.

        Args:
            window_id: The window ID to send to
            text: Text to send
            enter: Whether to press enter after the text
            literal: If True, send text literally. If False, interpret special keys
                     like "Up", "Down", "Left", "Right", "Escape", "Enter".

        Returns:
            True if successful, False otherwise
        """
        if literal and enter:
            # Split into text + delay + Enter via libtmux.
            # Codex's TUI sometimes interprets a rapid-fire Enter
            # (arriving in the same input batch as the text) as a newline
            # rather than submit.  A 500ms gap lets the TUI process the
            # text before receiving Enter.
            def _send_literal(chars: str) -> bool:
                session = self.get_session()
                if not session:
                    logger.error("No tmux session found")
                    return False
                try:
                    window = session.windows.get(window_id=window_id)
                    if not window:
                        logger.error(f"Window {window_id} not found")
                        return False
                    pane = window.active_pane
                    if not pane:
                        logger.error(f"No active pane in window {window_id}")
                        return False
                    pane.send_keys(chars, enter=False, literal=True)
                    return True
                except Exception as e:
                    logger.error(f"Failed to send keys to window {window_id}: {e}")
                    return False

            def _send_enter() -> bool:
                session = self.get_session()
                if not session:
                    return False
                try:
                    window = session.windows.get(window_id=window_id)
                    if not window:
                        return False
                    pane = window.active_pane
                    if not pane:
                        return False
                    pane.send_keys("", enter=True, literal=False)
                    return True
                except Exception as e:
                    logger.error(f"Failed to send Enter to window {window_id}: {e}")
                    return False

            # Codex's ! command mode: send "!" first so the TUI
            # switches to bash mode, wait 1s, then send the rest.
            if text.startswith("!"):
                if not await self._run(_send_literal, "!"):
                    return False
                rest = text[1:]
                if rest:
                    await asyncio.sleep(1.0)
                    if not await self._run(_send_literal, rest):
                        return False
            else:
                if not await self._run(_send_literal, text):
                    return False
            await asyncio.sleep(0.5)
            return await self._run(_send_enter)

        # Other cases: special keys (literal=False) or no-enter
        def _sync_send_keys() -> bool:
            session = self.get_session()
            if not session:
                logger.error("No tmux session found")
                return False

            try:
                window = session.windows.get(window_id=window_id)
                if not window:
                    logger.error(f"Window {window_id} not found")
                    return False

                pane = window.active_pane
                if not pane:
                    logger.error(f"No active pane in window {window_id}")
                    return False

                pane.send_keys(text, enter=enter, literal=literal)
                return True

            except Exception as e:
                logger.error(f"Failed to send keys to window {window_id}: {e}")
                return False

        return await self._run(_sync_send_keys)

    async def get_pane_pid(self, window_id: str) -> int | None:
        """Return the OS PID of the active pane for the given window."""
        window = await self.find_window_by_id(window_id)
        return window.pane_pid if window else None

    async def rename_window(self, window_id: str, new_name: str) -> bool:
        """Rename a tmux window by its ID."""

        def _sync_rename() -> bool:
            session = self.get_session()
            if not session:
                return False
            try:
                window = session.windows.get(window_id=window_id)
                if not window:
                    return False
                window.rename_window(new_name)
                logger.info("Renamed window %s to '%s'", window_id, new_name)
                return True
            except Exception as e:
                logger.error(f"Failed to rename window {window_id}: {e}")
                return False

        renamed = await self._run(_sync_rename)
        if renamed:
            self.invalidate_windows_cache()
        return renamed

    async def kill_window(self, window_id: str) -> bool:
        """Kill a tmux window by its ID."""

        def _sync_kill() -> bool:
            session = self.get_session()
            if not session:
                return False
            try:
                window = session.windows.get(window_id=window_id)
                if not window:
                    return False
                window.kill()
                logger.info("Killed window %s", window_id)
                return True
            except Exception as e:
                logger.error(f"Failed to kill window {window_id}: {e}")
                return False

        killed = await self._run(_sync_kill)
        if killed:
            self.invalidate_windows_cache()
        return killed

    @staticmethod
    def _type_start_command(pane, cmd: str, wid: str) -> None:  # noqa: ANN001
        """Type the agent start command into a freshly created pane, robustly.

        Two races to defeat: (1) sending before the shell finished loading
        (oh-my-zsh etc.) drops the leading character ("claude" → "laude"); a
        rendered banner doesn't mean the shell accepts input yet. So we wait
        until the pane output goes *stable* (loading finished, prompt idle).
        (2) Even then the pty can occasionally drop the first char, so we type
        without Enter, verify the command landed intact, clear+retype if not,
        then submit.
        """

        def capture() -> str:
            try:
                return "\n".join(pane.capture_pane())
            except Exception:  # noqa: BLE001
                return ""

        # 1) Wait for the shell to finish loading: pane non-empty AND unchanged
        #    across two consecutive samples (idle at prompt).
        prev, stable = None, 0
        for _ in range(60):  # up to ~3s
            rendered = capture()
            if rendered.strip() and rendered == prev:
                stable += 1
                if stable >= 2:
                    break
            else:
                stable = 0
            prev = rendered
            time.sleep(0.08)
        time.sleep(0.1)

        # 2) Type without Enter, verify a distinctive prefix echoed, retry once.
        probe = cmd[:18]
        pane.send_keys(cmd, enter=False, literal=True)
        time.sleep(0.15)
        if probe and probe not in capture():
            logger.warning(
                "start command first char likely dropped; retrying (window=%s)", wid
            )
            pane.send_keys("C-u", enter=False, literal=False)  # clear input line
            time.sleep(0.1)
            pane.send_keys(cmd, enter=False, literal=True)
            time.sleep(0.1)
        pane.send_keys("Enter", enter=False, literal=False)

    async def create_window(
        self,
        work_dir: str,
        window_name: str | None = None,
        start_codex: bool = True,
        resume_session_id: str | None = None,
        *,
        runtime: AgentRuntime | None = None,
        approval_gate: bool = False,
        hooks_settings_path: str | None = None,
        system_prompt: str | None = None,
    ) -> tuple[bool, str, str, str]:
        """Create a new tmux window and optionally start the agent.

        Args:
            work_dir: Working directory for the new window
            window_name: Optional window name (defaults to directory name)
            start_codex: Whether to start the agent command in the new pane
            resume_session_id: If set, ask the runtime to resume this session
            runtime: Agent runtime providing the start command (defaults
                to the Codex runtime for backward compatibility)

        Returns:
            Tuple of (success, message, window_name, window_id)
        """
        # Validate directory first
        path = Path(work_dir).expanduser().resolve()
        if not path.exists():
            return False, f"Directory does not exist: {work_dir}", "", ""
        if not path.is_dir():
            return False, f"Not a directory: {work_dir}", "", ""

        # Create window name, adding suffix if name already exists
        final_window_name = window_name if window_name else path.name

        # Check for existing window name
        base_name = final_window_name
        counter = 2
        while await self.find_window_by_name(final_window_name):
            final_window_name = f"{base_name}-{counter}"
            counter += 1

        # Create window in thread
        def _create_and_start() -> tuple[bool, str, str, str]:
            session = self.get_or_create_session()
            try:
                # Create new window
                window = session.new_window(
                    window_name=final_window_name,
                    start_directory=str(path),
                )

                wid = window.window_id or ""

                # Prevent the agent from overriding the window name
                window.set_window_option("allow-rename", "off")

                # Start the agent if requested
                if start_codex:
                    pane = window.active_pane
                    if pane:
                        if runtime is not None:
                            cmd = runtime.build_start_command(
                                resume_session_id,
                                approval_gate=approval_gate,
                                hooks_settings_path=hooks_settings_path,
                                system_prompt=system_prompt,
                            )
                        else:
                            cmd = config.codex_command
                            if resume_session_id:
                                cmd = f"{cmd} resume {resume_session_id}"
                        self._type_start_command(pane, cmd, wid)

                logger.info(
                    "Created window '%s' (id=%s) at %s",
                    final_window_name,
                    wid,
                    path,
                )
                return (
                    True,
                    f"Created window '{final_window_name}' at {path}",
                    final_window_name,
                    wid,
                )

            except Exception as e:
                logger.error(f"Failed to create window: {e}")
                return False, f"Failed to create window: {e}", "", ""

        result = await self._run(_create_and_start)
        self.invalidate_windows_cache()
        return result


# Global instance with default session name
tmux_manager = TmuxManager()
