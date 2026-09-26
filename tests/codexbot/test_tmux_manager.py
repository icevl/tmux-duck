"""TmuxManager: single-fork window listing, TTL cache, direct pane capture."""

from __future__ import annotations

import asyncio
import subprocess
from unittest.mock import patch

import pytest

from codexbot.config import config
from codexbot.tmux_manager import _LIST_PANES_FIELD_SEP, TmuxManager, TmuxWindow


def _row(
    window_id: str,
    name: str,
    cwd: str = "/repo",
    cmd: str = "claude",
    pid: str = "123",
    active: str = "1",
) -> str:
    return _LIST_PANES_FIELD_SEP.join([window_id, name, cwd, cmd, pid, active])


def test_parse_list_panes_keeps_active_pane_and_skips_main_window() -> None:
    out = (
        "\n".join(
            [
                _row("@0", config.tmux_main_window_name, "/Users/me", "zsh", "10"),
                _row("@1", "api", "/repo/api", "claude", "200"),
                _row("@1", "api", "/repo/api", "zsh", "201", active="0"),
                _row("@2", "web", "/repo/web", "node", "notapid"),
                "garbage line without separators",
            ]
        )
        + "\n"
    )

    windows = TmuxManager._parse_list_panes(out)

    assert windows == [
        TmuxWindow("@1", "api", "/repo/api", "claude", 200),
        TmuxWindow("@2", "web", "/repo/web", "node", None),
    ]


@pytest.fixture
def manager(monkeypatch: pytest.MonkeyPatch) -> TmuxManager:
    monkeypatch.setattr(config, "tmux_cache_ttl_seconds", 60.0)
    return TmuxManager(session_name="test-session")


async def test_list_windows_is_cached_and_shared_between_callers(
    manager: TmuxManager,
) -> None:
    calls = 0

    def fake_list() -> list[TmuxWindow]:
        nonlocal calls
        calls += 1
        return [TmuxWindow("@1", "api", "/repo", "claude", 42)]

    with patch.object(manager, "_sync_list_windows", side_effect=fake_list):
        first, second = await asyncio.gather(
            manager.list_windows(), manager.list_windows()
        )
        found = await manager.find_window_by_id("@1")
        pid = await manager.get_pane_pid("@1")

    # Concurrent callers share one refresh; lookups are served from the cache.
    assert calls == 1
    assert first == second == [TmuxWindow("@1", "api", "/repo", "claude", 42)]
    assert found is not None and found.window_id == "@1"
    assert pid == 42


async def test_list_windows_returns_copies(manager: TmuxManager) -> None:
    with patch.object(
        manager,
        "_sync_list_windows",
        return_value=[TmuxWindow("@1", "api", "/repo", "claude", 42)],
    ):
        first = await manager.list_windows()
        first.clear()
        second = await manager.list_windows()

    assert len(second) == 1


async def test_invalidate_and_max_age_zero_force_refresh(
    manager: TmuxManager,
) -> None:
    with patch.object(manager, "_sync_list_windows", return_value=[]) as sync_list:
        await manager.list_windows()
        await manager.list_windows()
        assert sync_list.call_count == 1

        manager.invalidate_windows_cache()
        await manager.list_windows()
        assert sync_list.call_count == 2

        await manager.list_windows(max_age=0)
        assert sync_list.call_count == 3


async def test_list_windows_serves_last_snapshot_when_tmux_fails(
    manager: TmuxManager,
) -> None:
    snapshot = [TmuxWindow("@1", "api", "/repo", "claude", 42)]
    # First call succeeds; the forced refresh hits a tmux timeout (None).
    with patch.object(manager, "_sync_list_windows", side_effect=[snapshot, None]):
        assert await manager.list_windows() == snapshot
        assert await manager.list_windows(max_age=0) == snapshot


async def test_capture_pane_uses_tmux_directly(manager: TmuxManager) -> None:
    completed = subprocess.CompletedProcess(
        args=[], returncode=0, stdout="line1\nline2\n", stderr=""
    )
    with patch.object(manager, "_tmux", return_value=completed) as tmux:
        plain = await manager.capture_pane("@1")
        ansi = await manager.capture_pane("@1", with_ansi=True)

    # Plain output keeps libtmux's "\n".join(lines) shape (no trailing newline);
    # the ANSI variant is raw tmux output as before.
    assert plain == "line1\nline2"
    assert ansi == "line1\nline2\n"
    assert [c.args for c in tmux.call_args_list] == [
        ("capture-pane", "-p", "-t", "@1"),
        ("capture-pane", "-e", "-p", "-t", "@1"),
    ]


async def test_capture_pane_returns_none_for_missing_window(
    manager: TmuxManager,
) -> None:
    completed = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="can't find window: @404"
    )
    with patch.object(manager, "_tmux", return_value=completed):
        assert await manager.capture_pane("@404") is None


def test_tmux_returns_none_on_timeout(manager: TmuxManager) -> None:
    with patch(
        "codexbot.tmux_manager.subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="tmux", timeout=1),
    ):
        assert manager._tmux("list-panes") is None


def test_sync_list_windows_treats_missing_session_as_empty(
    manager: TmuxManager,
) -> None:
    completed = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="no server running"
    )
    with patch.object(manager, "_tmux", return_value=completed) as tmux:
        assert manager._sync_list_windows() == []
    # Exact-name session target, single call.
    assert tmux.call_args.args[:4] == ("list-panes", "-s", "-t", "=test-session")
