"""Session monitor: transcript reads must not wait on window-binding refresh."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from codexbot.session_monitor import SessionInfo, SessionMonitor


async def test_monitor_keeps_reading_while_binding_refresh_is_stuck(
    tmp_path,
) -> None:
    """Regression: a slow tmux/`ps` used to block the whole poll loop.

    The refresh now runs as its own task; the loop polls transcripts with the
    last known bindings meanwhile.
    """
    monitor = SessionMonitor(
        projects_path=tmp_path / "projects",
        poll_interval=0.01,
        state_file=tmp_path / "monitor_state.json",
    )
    release = asyncio.Event()

    async def stuck_refresh() -> dict[str, str]:
        await release.wait()
        return {}

    reads: list[set[str]] = []

    async def fake_check(active_ids, *, bootstrap):  # noqa: ANN001
        reads.append(set(active_ids))
        return []

    with (
        patch.object(monitor, "_cleanup_all_stale_sessions", new=AsyncMock()),
        patch.object(
            monitor,
            "_load_current_window_sessions",
            new=AsyncMock(return_value={"@1": "sid-1"}),
        ),
        patch.object(monitor, "_refresh_bindings", side_effect=stuck_refresh),
        patch.object(monitor, "check_for_updates", side_effect=fake_check),
    ):
        monitor.start()
        try:
            for _ in range(300):
                await asyncio.sleep(0.01)
                if len(reads) >= 3:
                    break
        finally:
            release.set()
            await monitor.stop()

    assert len(reads) >= 3
    assert all(active == {"sid-1"} for active in reads)


async def test_monitor_picks_up_new_bindings_from_finished_refresh(
    tmp_path,
) -> None:
    monitor = SessionMonitor(
        projects_path=tmp_path / "projects",
        poll_interval=0.01,
        state_file=tmp_path / "monitor_state.json",
    )
    reads: list[set[str]] = []

    async def fake_check(active_ids, *, bootstrap):  # noqa: ANN001
        reads.append(set(active_ids))
        return []

    async def refresh() -> dict[str, str]:
        # Mirrors _detect_and_cleanup_changes, which stores the new map.
        monitor._last_window_sessions = {"@1": "sid-1", "@2": "sid-2"}
        return monitor._last_window_sessions

    with (
        patch.object(monitor, "_cleanup_all_stale_sessions", new=AsyncMock()),
        patch.object(
            monitor,
            "_load_current_window_sessions",
            new=AsyncMock(return_value={"@1": "sid-1"}),
        ),
        patch.object(monitor, "_refresh_bindings", side_effect=refresh),
        patch.object(monitor, "check_for_updates", side_effect=fake_check),
    ):
        monitor.start()
        try:
            for _ in range(300):
                await asyncio.sleep(0.01)
                if any(active == {"sid-1", "sid-2"} for active in reads):
                    break
        finally:
            await monitor.stop()

    assert {"sid-1", "sid-2"} in reads


async def test_resolve_active_sessions_refreshes_index_once(tmp_path) -> None:
    monitor = SessionMonitor(
        projects_path=tmp_path / "projects",
        state_file=tmp_path / "monitor_state.json",
    )
    transcript = tmp_path / "a.jsonl"
    transcript.write_text("{}\n", encoding="utf-8")

    with patch("codexbot.session.session_manager") as mock_sm:
        mock_sm.get_session_file_paths = AsyncMock(return_value={"a": transcript})
        infos = await monitor._resolve_active_sessions({"b", "a"})

    mock_sm.get_session_file_paths.assert_awaited_once_with(["a", "b"])
    assert infos == [SessionInfo(session_id="a", file_path=transcript)]
