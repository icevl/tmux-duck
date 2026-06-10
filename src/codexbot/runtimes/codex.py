"""Codex agent runtime.

Wraps the existing Codex-specific behavior behind the `AgentRuntime`
interface without changing the underlying logic. Session detection in
particular is performed in `session.py` via transcript scanning; for the
Codex runtime `discover_session_id` is a no-op because the existing
`SessionManager.wait_for_session_map_entry` is still the authority.
"""

from __future__ import annotations

import logging
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
    ) -> str | None:
        # Codex session detection happens via SessionManager's transcript
        # scanning machinery (`wait_for_session_map_entry`), not through
        # this hook. Returning None signals the caller to use the existing
        # path, which is what we want during Phase 1.
        return None

    def pane_command_matches(self, pane_current_command: str) -> bool:
        if not isinstance(pane_current_command, str):
            return False
        return "codex" in pane_current_command.lower()
