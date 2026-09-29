"""Codex agent runtime.

Wraps the existing Codex-specific behavior behind the `AgentRuntime`
interface without changing the underlying logic. Session detection in
particular is performed in `session.py` via transcript scanning; for the
Codex runtime `discover_session_id` is a no-op because the existing
`SessionManager.wait_for_session_map_entry` is still the authority.
"""

from __future__ import annotations

import asyncio
import logging
import re
import shlex

from ..config import config

logger = logging.getLogger(__name__)

# Flags that disable Codex's approval prompts. They must be stripped in
# connector (approval-gate) mode, otherwise they override the `untrusted`
# policy and the write-gate never fires.
_BYPASS_FLAGS = {
    "--dangerously-bypass-approvals-and-sandbox",
    "--yolo",
    "--full-auto",
}
# Flags taking a value we re-specify ourselves in gate mode.
_VALUE_FLAGS = {"--ask-for-approval", "-a", "--sandbox", "-s"}


# Codex's first launch in a folder asks
#   "Do you trust the contents of this directory? …"
#   › 1. Yes, continue
#     2. No, quit
# and blocks until answered. The web UI can't show it, so Codi answers yes —
# the user picked this folder for the session.
_RE_TRUST_PROMPT = re.compile(r"do you trust the contents of this directory", re.I)
_RE_TRUST_OPTION = re.compile(r"^\s*([›❯>])?\s*(\d+)\.\s+(yes|no)\b", re.I)
# How long after launch to keep watching for the prompt, and how often.
STARTUP_WATCH_SECONDS = 30.0
STARTUP_POLL_SECONDS = 0.5


def trust_prompt_keys(pane_text: str) -> list[str] | None:
    """Keys that pick "Yes" in a visible trust prompt, or None if none is shown."""
    if not _RE_TRUST_PROMPT.search(pane_text):
        return None
    options: list[tuple[bool, bool]] = []  # (has cursor, is yes)
    for line in pane_text.splitlines():
        match = _RE_TRUST_OPTION.match(line)
        if match:
            options.append((bool(match.group(1)), match.group(3).lower() == "yes"))
    cursor = next((i for i, (has, _) in enumerate(options) if has), None)
    target = next((i for i, (_, yes) in enumerate(options) if yes), None)
    if cursor is None or target is None:
        return None
    step = "Down" if target > cursor else "Up"
    return [step] * abs(target - cursor) + ["Enter"]


async def accept_startup_prompts(window_id: str) -> bool:
    """Watch a freshly launched Codex pane and accept its trust prompt.

    Returns True when a prompt was answered. Gives up after
    ``STARTUP_WATCH_SECONDS`` — on an already trusted folder there is none.
    """
    from ..tmux_manager import tmux_manager

    loop = asyncio.get_running_loop()
    deadline = loop.time() + STARTUP_WATCH_SECONDS
    while loop.time() < deadline:
        pane_text = await tmux_manager.capture_pane(window_id)
        keys = trust_prompt_keys(pane_text) if pane_text else None
        if keys:
            for index, key in enumerate(keys):
                if index:
                    await asyncio.sleep(0.2)
                await tmux_manager.send_keys(window_id, key, enter=False, literal=False)
            logger.info("auto-accepted codex trust prompt window=%s", window_id)
            return True
        await asyncio.sleep(STARTUP_POLL_SECONDS)
    return False


def _strip_approval_flags(command: str) -> str:
    """Remove bypass/approval/sandbox flags so we can set our own policy."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return command
    out: list[str] = []
    skip_next = False
    for tok in tokens:
        if skip_next:
            skip_next = False
            continue
        if tok in _BYPASS_FLAGS:
            continue
        if tok in _VALUE_FLAGS:
            skip_next = True
            continue
        if tok.startswith(("--ask-for-approval=", "--sandbox=")):
            continue
        out.append(tok)
    return " ".join(shlex.quote(t) if " " in t else t for t in out)


# Strong refs so the startup watchers aren't garbage-collected mid-run.
_startup_tasks: set[asyncio.Task[bool]] = set()


class CodexRuntime:
    name = "codex"
    display_name = "Codex"
    display_emoji = "🔧"

    def build_start_command(
        self,
        resume_session_id: str | None,
        *,
        approval_gate: bool = False,
        hooks_settings_path: str | None = None,
        system_prompt: str | None = None,  # not a Codex CLI flag; injected per-message
    ) -> str:
        cmd = config.codex_command
        if approval_gate:
            # Strip any bypass/yolo flag (it would silence approvals) and pin
            # the native "untrusted" policy: trusted reads (ls/cat/sed/…) run
            # without asking; everything else escalates to an approval prompt
            # in the pane, which the connector surfaces to Slack.
            cmd = _strip_approval_flags(cmd)
            cmd = f"{cmd} --ask-for-approval untrusted"
        if resume_session_id:
            cmd = f"{cmd} resume {resume_session_id}"
        return cmd

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
        # Codex session detection happens via SessionManager's transcript
        # scanning machinery (`wait_for_session_map_entry`), not through
        # this hook. Returning None signals the caller to use the existing
        # path, which is what we want during Phase 1.
        return None

    def watch_startup(self, window_id: str) -> None:
        """Answer Codex's launch-time prompts in the background."""
        task = asyncio.get_running_loop().create_task(
            accept_startup_prompts(window_id),
            name=f"codex-startup:{window_id}",
        )
        _startup_tasks.add(task)
        task.add_done_callback(_startup_tasks.discard)

    def pane_command_matches(self, pane_current_command: str) -> bool:
        if not isinstance(pane_current_command, str):
            return False
        return "codex" in pane_current_command.lower()
