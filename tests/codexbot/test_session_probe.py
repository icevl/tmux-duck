"""SessionManager: cheap re-verification of established Claude windows."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from codexbot.session import SessionManager


@pytest.fixture
def mgr(monkeypatch: pytest.MonkeyPatch) -> SessionManager:
    monkeypatch.setattr(SessionManager, "_load_state", lambda self: None)
    monkeypatch.setattr(SessionManager, "_save_state", lambda self: None)
    return SessionManager()


def _claude_window():
    return type(
        "Window",
        (),
        {
            "window_id": "@1",
            "window_name": "codexbot",
            "cwd": "/tmp",
            "pane_current_command": "claude",
        },
    )()


async def test_established_window_probe_is_single_shot(
    mgr: SessionManager, tmp_path
) -> None:
    """A live transcript + known session id → one quick check, no 15s loop."""
    transcript = tmp_path / "live-session.jsonl"
    transcript.write_text("{}", encoding="utf-8")

    ws = mgr.get_window_state("@1")
    ws.session_id = "live-session"
    ws.cwd = "/tmp"
    ws.window_name = "codexbot"
    ws.runtime = "claude"

    mock_runtime = MagicMock()
    mock_runtime.discover_session_id = AsyncMock(return_value="live-session")

    with (
        patch.object(mgr, "_refresh_sessions_index", new=AsyncMock()) as refresh,
        patch("codexbot.session.get_runtime", return_value=mock_runtime),
        patch(
            "codexbot.session.tmux_manager.find_window_by_id",
            new=AsyncMock(return_value=_claude_window()),
        ),
        patch(
            "codexbot.session.tmux_manager.get_pane_pid",
            new=AsyncMock(return_value=1234),
        ),
    ):
        mgr._session_index = {"live-session": transcript}
        resolved = await mgr.refresh_window_session_if_stale("@1")

    assert resolved == "live-session"
    mock_runtime.discover_session_id.assert_awaited_once_with(
        window_id="@1",
        pane_pid=1234,
        cwd="/tmp",
        allow_cwd_fallback=False,
        timeout=0.0,
        advance_startup_prompts=False,
    )
    # Binding unchanged → no forced rescan of the sessions tree.
    assert all(not call.kwargs.get("force") for call in refresh.await_args_list)


async def test_rebind_forces_index_refresh(mgr: SessionManager, tmp_path) -> None:
    transcript = tmp_path / "old-session.jsonl"
    transcript.write_text("{}", encoding="utf-8")

    ws = mgr.get_window_state("@1")
    ws.session_id = "old-session"
    ws.cwd = "/tmp"
    ws.window_name = "codexbot"
    ws.runtime = "claude"

    mock_runtime = MagicMock()
    mock_runtime.discover_session_id = AsyncMock(return_value="new-session")

    with (
        patch.object(mgr, "_refresh_sessions_index", new=AsyncMock()) as refresh,
        patch("codexbot.session.get_runtime", return_value=mock_runtime),
        patch(
            "codexbot.session.tmux_manager.find_window_by_id",
            new=AsyncMock(return_value=_claude_window()),
        ),
        patch(
            "codexbot.session.tmux_manager.get_pane_pid",
            new=AsyncMock(return_value=1234),
        ),
    ):
        mgr._session_index = {"old-session": transcript}
        resolved = await mgr.refresh_window_session_if_stale("@1")

    assert resolved == "new-session"
    assert any(call.kwargs.get("force") for call in refresh.await_args_list)


async def test_missing_transcript_uses_full_discovery(
    mgr: SessionManager,
) -> None:
    """No transcript on disk → the window may still be booting: full loop."""
    ws = mgr.get_window_state("@1")
    ws.session_id = "stale-session"
    ws.cwd = "/tmp"
    ws.window_name = "codexbot"
    ws.runtime = "claude"

    mock_runtime = MagicMock()
    mock_runtime.discover_session_id = AsyncMock(return_value="fresh-session")

    with (
        patch.object(mgr, "_refresh_sessions_index", new=AsyncMock()),
        patch("codexbot.session.get_runtime", return_value=mock_runtime),
        patch(
            "codexbot.session.tmux_manager.find_window_by_id",
            new=AsyncMock(return_value=_claude_window()),
        ),
        patch(
            "codexbot.session.tmux_manager.get_pane_pid",
            new=AsyncMock(return_value=1234),
        ),
    ):
        mgr._session_index = {}
        resolved = await mgr.refresh_window_session_if_stale("@1")

    assert resolved == "fresh-session"
    kwargs = mock_runtime.discover_session_id.await_args.kwargs
    assert "timeout" not in kwargs
    assert "advance_startup_prompts" not in kwargs


async def test_get_session_file_paths_refreshes_once(
    mgr: SessionManager, tmp_path
) -> None:
    existing = tmp_path / "a.jsonl"
    existing.write_text("{}", encoding="utf-8")
    missing = tmp_path / "gone.jsonl"

    with patch.object(mgr, "_refresh_sessions_index", new=AsyncMock()) as refresh:
        mgr._session_index = {"a": existing, "gone": missing}
        paths = await mgr.get_session_file_paths(["a", "gone", "unknown"])
        single = await mgr.get_session_file_path("a")

    assert paths == {"a": existing}
    assert single == existing
    assert refresh.await_count == 2
