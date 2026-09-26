"""Claude Code agent runtime.

Claude Code writes a per-process file at `~/.claude/sessions/<pid>.json`
containing `{sessionId, cwd, ...}` as soon as it starts. Phase 1 uses
that file plus a process-tree walk from the tmux pane PID to discover
the runtime session id for a newly created window.

Fallback when the PID walk doesn't return a result in time: scan the
sessions directory for the most recently started entry whose `cwd`
matches the target window.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shlex
import tempfile
import time
from pathlib import Path

from ..config import config
from ..profiles import Profile, default_profile
from ..tmux_manager import tmux_manager
from ..utils import codexbot_dir

logger = logging.getLogger(__name__)
_SHELL_COMMANDS = {"bash", "fish", "sh", "zsh"}
# `ps -A` normally returns in milliseconds; under heavy load it can take
# seconds, and a too-tight limit made every probe look like "no process".
_PS_TIMEOUT_SECONDS = 5.0


class ProcessScanUnavailable(RuntimeError):
    """`ps` could not be consulted, so the pane's process tree is unknown."""


_RE_CLAUDE_VERSION_TITLE = re.compile(r"^\d+\.\d+\.\d+$")

_RE_BYPASS_PERMISSIONS_PROMPT = re.compile(
    r"bypass permissions mode",
    re.IGNORECASE,
)
_RE_WORKSPACE_TRUST_PROMPT = re.compile(
    # ≤ 2.1.2x: "Do you trust the files in this folder?"
    # 2.1.28x: "Quick safety check: Is this a project you created or one you
    # trust?" over an unnumbered "❯ No, exit / Yes, I trust this folder".
    r"do you trust the files in this|yes, i trust this folder",
    re.IGNORECASE,
)
# A Yes/No menu row, numbered ("❯ 1. Yes, proceed") or not ("  Yes, I trust
# this folder"). Which row is the default differs per prompt and version.
_RE_STARTUP_OPTION = re.compile(r"^\s*(❯)?\s*(?:\d+\.\s+)?(yes|no)\b", re.IGNORECASE)


def _write_system_prompt_file(system_prompt: str | None) -> str | None:
    """Persist the connector system prompt to a file; return its path or None.

    Claude reads it via ``--append-system-prompt-file`` at launch, so the
    (possibly multi-line) instructions never get typed into the pane.
    """
    if not system_prompt or not system_prompt.strip():
        return None
    prompts_dir = codexbot_dir() / "connectors" / "sysprompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    fd, path = tempfile.mkstemp(
        prefix="sysprompt-", suffix=".txt", dir=str(prompts_dir)
    )
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(system_prompt.strip() + "\n")
    return path


class ClaudeRuntime:
    name = "claude"
    display_name = "Claude Code"
    display_emoji = "🧠"

    def __init__(self, profile: Profile | None = None) -> None:
        self.profile = profile or default_profile(self.name)

    def build_start_command(
        self,
        resume_session_id: str | None,
        *,
        approval_gate: bool = False,
        hooks_settings_path: str | None = None,
        system_prompt: str | None = None,
    ) -> str:
        cmd = config.claude_command
        if resume_session_id:
            cmd = f"{cmd} --resume {resume_session_id}"
        if approval_gate:
            # Connector mode: full auto so reads never prompt; a PreToolUse
            # hook (loaded from the connector's settings file) gates writes.
            if "--dangerously-skip-permissions" not in cmd:
                cmd = f"{cmd} --dangerously-skip-permissions"
            if hooks_settings_path:
                cmd = f"{cmd} --settings {shlex.quote(hooks_settings_path)}"
            prompt_file = _write_system_prompt_file(system_prompt)
            if prompt_file:
                # Pass via a FILE, not inline: a multi-line/quoted prompt typed
                # into the pane breaks shell quoting (instructions spilled into
                # the shell as commands). The command line stays single-line.
                cmd = f"{cmd} --append-system-prompt-file {shlex.quote(prompt_file)}"
        else:
            if config.claude_auto_approve_dangerous:
                if "--dangerously-skip-permissions" not in cmd:
                    cmd = f"{cmd} --dangerously-skip-permissions"
            if config.claude_event_hooks and "--settings" not in cmd:
                from ..claude_hooks import ensure_event_hook_settings

                cmd = f"{cmd} --settings {shlex.quote(ensure_event_hook_settings())}"
        env = " ".join(f"{k}={shlex.quote(v)}" for k, v in self.profile.env().items())
        return f"{env} {cmd}" if env else cmd

    async def discover_session_id(
        self,
        *,
        window_id: str,
        pane_pid: int | None,
        cwd: str,
        allow_cwd_fallback: bool = True,
        timeout: float | None = None,
        advance_startup_prompts: bool = True,
    ) -> str | None:
        """Resolve the live Claude session id for a pane.

        Retries every `claude_session_detect_interval` until `timeout` (default
        `claude_session_detect_timeout`) — a fresh window needs a few seconds
        before Claude writes its sessions file. `timeout=0` makes exactly one
        attempt, which is all a periodic re-check of an established window
        needs. `advance_startup_prompts` auto-confirms Claude's first-run
        prompts between attempts; disable it when the pane is known to be past
        startup.
        """
        sessions_dir = self.profile.claude_sessions_path
        if not sessions_dir.exists():
            logger.debug("claude sessions dir does not exist: %s", sessions_dir)
            return None

        wait = (
            config.claude_session_detect_timeout
            if timeout is None
            else max(0.0, timeout)
        )
        loop = asyncio.get_running_loop()
        deadline = loop.time() + wait
        started_at_floor = time.time() - 5.0  # ignore entries written long ago
        last_startup_action_at: dict[str, float] = {}
        scan_unavailable = False
        while True:
            if advance_startup_prompts:
                await _maybe_advance_startup_prompt(
                    window_id,
                    last_action_at=last_startup_action_at,
                )
            try:
                sid = await asyncio.to_thread(
                    _read_claude_session_for_pane,
                    pane_pid,
                    cwd,
                    sessions_dir,
                    started_at_floor,
                    allow_cwd_fallback,
                )
            except ProcessScanUnavailable:
                # `ps` didn't answer in time (machine under load). That is
                # "unknown", not "no session" — never let it look like a
                # rebind candidate; retry within the deadline if we have one.
                sid = None
                scan_unavailable = True
            if sid:
                return sid
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            await asyncio.sleep(min(config.claude_session_detect_interval, remaining))

        if wait > 0:
            logger.warning(
                "claude session detection timed out for window=%s cwd=%s pane_pid=%s",
                window_id,
                cwd,
                pane_pid,
            )
        elif scan_unavailable:
            logger.debug(
                "claude session probe skipped (process scan unavailable) window=%s",
                window_id,
            )
        return None

    def pane_command_matches(self, pane_current_command: str) -> bool:
        if not isinstance(pane_current_command, str):
            return False
        cmd = pane_current_command.lower()
        # Claude Code ≥ 2.1 retitles its process to the bare version
        # ("2.1.282"), so that is what tmux reports as the pane command.
        return cmd.startswith("claude") or bool(_RE_CLAUDE_VERSION_TITLE.match(cmd))


async def _maybe_advance_startup_prompt(
    window_id: str,
    *,
    last_action_at: dict[str, float],
) -> None:
    """Accept the Claude startup prompts that block session creation.

    Only the prompts shown before Claude starts its working session:
      - the bypass-permissions warning (accept),
      - the workspace trust prompt (trust the folder).
    The cursor is moved onto the "Yes" row before Enter, since the default row
    is "No, exit" in some versions.
    """
    window = await tmux_manager.find_window_by_id(window_id)
    if not window:
        return
    if window.pane_current_command.lower() in _SHELL_COMMANDS:
        return

    pane_text = await tmux_manager.capture_pane(window_id)
    if not pane_text:
        return

    prompt = _startup_prompt(pane_text)
    if prompt is None:
        return
    action, keys = prompt

    now = time.monotonic()
    if now - last_action_at.get(action, 0.0) < 2.0:
        return

    for index, key in enumerate(keys):
        if index:
            await asyncio.sleep(0.2)
        if not await tmux_manager.send_keys(window_id, key, enter=False, literal=False):
            return
    last_action_at[action] = now
    logger.info(
        "auto-advanced claude startup prompt window=%s action=%s",
        window_id,
        action,
    )


def _keys_to_accept(pane_text: str) -> list[str] | None:
    """Keys that move the menu cursor onto the "Yes" row and confirm it."""
    runs: list[list[tuple[bool, bool]]] = [[]]
    for line in pane_text.splitlines():
        match = _RE_STARTUP_OPTION.match(line)
        if match:
            runs[-1].append((bool(match.group(1)), match.group(2).lower() == "yes"))
        elif runs[-1]:
            runs.append([])
    for options in reversed(runs):
        cursor = next(
            (i for i, (has_cursor, _) in enumerate(options) if has_cursor), None
        )
        target = next((i for i, (_, is_yes) in enumerate(options) if is_yes), None)
        if cursor is None or target is None or len(options) < 2:
            continue
        step = "Down" if target > cursor else "Up"
        return [step] * abs(target - cursor) + ["Enter"]
    return None


def _startup_prompt(pane_text: str) -> tuple[str, list[str]] | None:
    """Return (action name, keys to accept) for a startup prompt snapshot."""
    if _RE_BYPASS_PERMISSIONS_PROMPT.search(pane_text):
        action = "bypass_permissions"
    elif _RE_WORKSPACE_TRUST_PROMPT.search(pane_text):
        action = "workspace_trust"
    else:
        return None
    keys = _keys_to_accept(pane_text)
    return (action, keys) if keys else None


def _classify_startup_prompt(pane_text: str) -> str | None:
    """Return the known startup prompt action name for a pane snapshot."""
    prompt = _startup_prompt(pane_text)
    return prompt[0] if prompt else None


def _read_claude_session_for_pane(
    pane_pid: int | None,
    cwd: str,
    sessions_dir: Path,
    started_at_floor: float,
    allow_cwd_fallback: bool,
) -> str | None:
    """Synchronous fast-path for session discovery.

    Walks the pane's descendant PIDs and reads
    ``~/.claude/sessions/<pid>.json``; falls back to a cwd-based scan.
    """
    if pane_pid is not None:
        candidate_pids = _descendant_pids(pane_pid)
        if candidate_pids is None:
            if not allow_cwd_fallback:
                raise ProcessScanUnavailable(pane_pid)
            candidate_pids = []
        for pid in candidate_pids:
            sid = _read_session_file_for_pid(sessions_dir, pid, cwd)
            if sid:
                return sid

    if not allow_cwd_fallback:
        return None

    # Fallback: scan all session files, filter by cwd, prefer most recent
    norm_cwd = _normalize_cwd(cwd)
    best_sid: str | None = None
    best_started_at = -1.0
    try:
        entries = list(sessions_dir.glob("*.json"))
    except OSError:
        return None

    for path in entries:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if _normalize_cwd(data.get("cwd", "")) != norm_cwd:
            continue
        started_at_ms = data.get("startedAt")
        if not isinstance(started_at_ms, (int, float)):
            continue
        # startedAt is ms since epoch; filter recent entries
        started_at = started_at_ms / 1000.0
        if started_at < started_at_floor:
            continue
        if started_at > best_started_at:
            sid = data.get("sessionId")
            if isinstance(sid, str) and sid:
                best_sid = sid
                best_started_at = started_at
    return best_sid


def _read_session_file_for_pid(sessions_dir: Path, pid: int, cwd: str) -> str | None:
    path = sessions_dir / f"{pid}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if _normalize_cwd(data.get("cwd", "")) != _normalize_cwd(cwd):
        # The pane's claude process may have started in a different cwd
        # than the window's recorded cwd. Trust the PID match.
        logger.debug(
            "claude session file pid=%s cwd mismatch: file=%s window=%s",
            pid,
            data.get("cwd"),
            cwd,
        )
    sid = data.get("sessionId")
    if isinstance(sid, str) and sid:
        return sid
    return None


def _descendant_pids(root_pid: int) -> list[int] | None:
    """Return ``root_pid``'s descendants ordered breadth-first.

    Shells out to ``ps`` once and walks the parent/child relations in
    Python. The list excludes ``root_pid`` itself. Returns None when ``ps``
    could not be consulted (timeout under load, exec failure) so callers can
    tell "unknown" from "no descendants".
    """
    import subprocess

    try:
        out = subprocess.check_output(
            ["ps", "-A", "-o", "pid=,ppid="],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=_PS_TIMEOUT_SECONDS,
        )
    except (subprocess.SubprocessError, OSError) as e:
        logger.debug("ps scan unavailable for pid %s: %s", root_pid, e)
        return None

    children: dict[int, list[int]] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) != 2:
            continue
        try:
            pid = int(parts[0])
            ppid = int(parts[1])
        except ValueError:
            continue
        children.setdefault(ppid, []).append(pid)

    result: list[int] = []
    queue: list[int] = list(children.get(root_pid, []))
    while queue:
        pid = queue.pop(0)
        result.append(pid)
        queue.extend(children.get(pid, []))
    return result


def _normalize_cwd(cwd: str) -> str:
    try:
        return str(Path(cwd).expanduser().resolve())
    except (OSError, RuntimeError, ValueError):
        return cwd
