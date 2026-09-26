"""Claude runtime session discovery: single-shot probes and `ps` failures."""

from __future__ import annotations

import json
import logging
import subprocess
import time
from unittest.mock import AsyncMock, patch

import pytest

from codexbot.config import config
from codexbot.runtimes import claude as claude_mod
from codexbot.runtimes.claude import (
    ClaudeRuntime,
    ProcessScanUnavailable,
    _descendant_pids,
    _read_claude_session_for_pane,
)


def test_descendant_pids_walks_the_tree() -> None:
    with patch("subprocess.check_output", return_value="1 0\n10 1\n11 10\n20 2\n"):
        assert _descendant_pids(1) == [10, 11]


def test_descendant_pids_returns_none_when_ps_times_out() -> None:
    with patch(
        "subprocess.check_output",
        side_effect=subprocess.TimeoutExpired(cmd="ps", timeout=5),
    ):
        # None = "unknown", distinct from [] = "no descendants".
        assert _descendant_pids(1) is None


def test_read_session_raises_when_scan_unavailable_without_fallback(
    tmp_path,
) -> None:
    with patch.object(claude_mod, "_descendant_pids", return_value=None):
        with pytest.raises(ProcessScanUnavailable):
            _read_claude_session_for_pane(1, str(tmp_path), tmp_path, 0.0, False)


def test_read_session_falls_back_to_cwd_scan_when_scan_unavailable(
    tmp_path,
) -> None:
    (tmp_path / "77.json").write_text(
        json.dumps(
            {
                "sessionId": "sid-77",
                "cwd": str(tmp_path),
                "startedAt": int(time.time() * 1000),
            }
        ),
        encoding="utf-8",
    )
    with patch.object(claude_mod, "_descendant_pids", return_value=None):
        sid = _read_claude_session_for_pane(
            1, str(tmp_path), tmp_path, time.time() - 60, True
        )
    assert sid == "sid-77"


@pytest.fixture
def runtime(monkeypatch: pytest.MonkeyPatch, tmp_path) -> ClaudeRuntime:
    monkeypatch.setattr(config, "claude_sessions_path", tmp_path)
    monkeypatch.setattr(config, "claude_session_detect_interval", 0.01)
    return ClaudeRuntime()


async def test_single_attempt_probe_skips_startup_prompts(
    runtime: ClaudeRuntime, tmp_path
) -> None:
    reads: list[int | None] = []

    def fake_read(pane_pid, cwd, sessions_dir, floor, allow_fallback):  # noqa: ANN001
        reads.append(pane_pid)
        return None

    with (
        patch.object(
            claude_mod, "_read_claude_session_for_pane", side_effect=fake_read
        ),
        patch.object(
            claude_mod, "_maybe_advance_startup_prompt", new=AsyncMock()
        ) as advance,
    ):
        sid = await runtime.discover_session_id(
            window_id="@1",
            pane_pid=5,
            cwd=str(tmp_path),
            allow_cwd_fallback=False,
            timeout=0.0,
            advance_startup_prompts=False,
        )

    assert sid is None
    assert reads == [5]
    advance.assert_not_awaited()


async def test_scan_unavailable_returns_none_without_timeout_warning(
    runtime: ClaudeRuntime, tmp_path, caplog: pytest.LogCaptureFixture
) -> None:
    with (
        patch.object(
            claude_mod,
            "_read_claude_session_for_pane",
            side_effect=ProcessScanUnavailable(5),
        ),
        patch.object(claude_mod, "_maybe_advance_startup_prompt", new=AsyncMock()),
        caplog.at_level(logging.WARNING, logger="codexbot.runtimes.claude"),
    ):
        sid = await runtime.discover_session_id(
            window_id="@1",
            pane_pid=5,
            cwd=str(tmp_path),
            allow_cwd_fallback=False,
            timeout=0.0,
            advance_startup_prompts=False,
        )

    # "Unknown" must neither rebind nor spam the log as a detection timeout.
    assert sid is None
    assert "timed out" not in caplog.text


async def test_fresh_window_discovery_retries_until_found(
    runtime: ClaudeRuntime, tmp_path
) -> None:
    attempts = 0

    def fake_read(*args):  # noqa: ANN002
        nonlocal attempts
        attempts += 1
        return "sid-ok" if attempts == 3 else None

    with (
        patch.object(
            claude_mod, "_read_claude_session_for_pane", side_effect=fake_read
        ),
        patch.object(
            claude_mod, "_maybe_advance_startup_prompt", new=AsyncMock()
        ) as advance,
    ):
        sid = await runtime.discover_session_id(
            window_id="@1", pane_pid=5, cwd=str(tmp_path), timeout=2.0
        )

    assert sid == "sid-ok"
    assert attempts == 3
    assert advance.await_count == 3


async def test_fresh_window_discovery_times_out_with_warning(
    runtime: ClaudeRuntime, tmp_path, caplog: pytest.LogCaptureFixture
) -> None:
    with (
        patch.object(claude_mod, "_read_claude_session_for_pane", return_value=None),
        patch.object(claude_mod, "_maybe_advance_startup_prompt", new=AsyncMock()),
        caplog.at_level(logging.WARNING, logger="codexbot.runtimes.claude"),
    ):
        sid = await runtime.discover_session_id(
            window_id="@1", pane_pid=5, cwd=str(tmp_path), timeout=0.05
        )

    assert sid is None
    assert "timed out" in caplog.text
