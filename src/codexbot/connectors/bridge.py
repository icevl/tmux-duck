"""Session bridging shared by connectors.

Turns an external conversation id (e.g. a Slack ``channel:thread_ts``) into
a live tmux window running the configured agent, and routes agent output
back by mapping a transcript ``session_id`` to the owning window. Distilled
from the web UI's ``create_session`` path so connectors reuse the exact
window-creation + session-discovery behavior.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..runtimes import get_runtime
from ..session import session_manager
from ..tmux_manager import tmux_manager
from . import store

logger = logging.getLogger(__name__)


async def ensure_window(
    *,
    connector_id: str,
    external_id: str,
    runtime_name: str,
    cwd: str,
    window_name: str | None = None,
    instructions: str = "",
) -> tuple[str, bool]:
    """Return the tmux window backing ``external_id``, creating it if needed.

    On first contact for a conversation a new window is created, the agent's
    session id discovered, and the mapping persisted. Connector ``instructions``
    are applied without typing into the pane: Claude gets them as a launch
    system prompt; for Codex the caller prepends them to the first message.

    Returns ``(window_id, created)``. Raises ``RuntimeError`` if the window
    cannot be created.
    """
    mapping = store.get_session_mapping(connector_id, external_id)
    if mapping is not None:
        window = await tmux_manager.find_window_by_id(mapping.window_id)
        if window is not None:
            return mapping.window_id, False
        # Window died (e.g. process restart killed the pane). Drop the stale
        # mapping and fall through to recreate.
        logger.info(
            "connector window gone external_id=%s window_id=%s; recreating",
            external_id,
            mapping.window_id,
        )
        store.delete_session_mapping(connector_id, external_id)

    runtime = get_runtime(runtime_name)
    path = Path(cwd).expanduser()
    if not path.is_absolute():
        path = path.resolve()
    if not path.exists() or not path.is_dir():
        raise RuntimeError(f"connector cwd not found: {path}")

    # Connector sessions always run the write-gate: reads flow freely, writes
    # require approval. Claude needs a PreToolUse hook settings file; Codex
    # uses its native untrusted approval policy (no settings file).
    hooks_settings_path = None
    system_prompt = None
    if runtime.name == "claude":
        from .approval import ensure_claude_hook_settings

        hooks_settings_path = ensure_claude_hook_settings()
        # Claude takes the instructions as a system prompt at launch (never
        # typed into the pane → no echo, no menu false-positives).
        system_prompt = instructions.strip() or None

    success, message, wname, wid = await tmux_manager.create_window(
        str(path),
        window_name=window_name,
        resume_session_id=None,
        runtime=runtime,
        approval_gate=True,
        hooks_settings_path=hooks_settings_path,
        system_prompt=system_prompt,
    )
    if not success:
        raise RuntimeError(f"failed to create window: {message}")

    ws = session_manager.get_window_state(wid)
    ws.runtime = runtime.name
    ws.cwd = str(path)
    ws.window_name = wname
    ws.connector_id = connector_id  # hides it from the web/Telegram lists
    session_manager._save_state()

    await _discover_session_id(runtime, wid, str(path))
    # NB: no slash-command hint discovery here — it probes the pane by typing
    # `/help`, which would collide with the first user message we send below
    # (observed as a garbled "/helpздаров" prompt). Connectors don't need the
    # slash-command autocomplete anyway.

    store.upsert_session_mapping(
        connector_id=connector_id,
        external_id=external_id,
        window_id=wid,
        runtime=runtime.name,
        cwd=str(path),
    )

    # Instructions are NOT typed into the pane. Claude got them as a system
    # prompt above; Codex (no such flag) has them prepended to its first user
    # message by the connector (it knows whether this is a fresh window).
    return wid, True


async def _discover_session_id(runtime, window_id: str, cwd: str) -> None:
    """Best-effort transcript session-id discovery for a fresh window."""
    if runtime.name == "claude":
        pane_pid = await tmux_manager.get_pane_pid(window_id)
        sid = await runtime.discover_session_id(
            window_id=window_id,
            pane_pid=pane_pid,
            cwd=cwd,
            allow_cwd_fallback=True,
        )
        if sid:
            ws = session_manager.get_window_state(window_id)
            ws.session_id = sid
            session_manager._save_state()
    else:
        session_manager.mark_window_for_new_session(window_id, clear_existing=False)
        try:
            await session_manager.wait_for_session_map_entry(window_id, timeout=5.0)
        except Exception as exc:  # noqa: BLE001
            logger.debug("connector session detect raised %s", exc)


async def send_user_message(window_id: str, text: str) -> bool:
    """Forward a user message into the agent running in ``window_id``."""
    ok, _msg = await session_manager.send_to_window(window_id, text)
    return ok


def window_for_session(session_id: str) -> str | None:
    """Reverse a transcript ``session_id`` to its tmux window id."""
    for window_id, state in session_manager.window_states.items():
        if state.session_id == session_id:
            return window_id
    return None


def tag_connector_windows() -> None:
    """Backfill ``connector_id`` on already-mapped windows.

    Windows created before the field existed (or before this connector was
    tracked) are tagged so the web/Telegram session lists hide them.
    """
    changed = False
    for connector in store.list_connectors():
        for mapping in store.list_session_mappings(connector.id):
            ws = session_manager.window_states.get(mapping.window_id)
            if ws is not None and ws.connector_id != connector.id:
                ws.connector_id = connector.id
                changed = True
    if changed:
        session_manager._save_state()


__all__ = [
    "ensure_window",
    "send_user_message",
    "window_for_session",
]
