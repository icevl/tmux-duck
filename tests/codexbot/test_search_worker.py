"""Search worker lifecycle, status, and generation-state tests."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import pytest

from codexbot.search.contracts import SearchCounters


def test_worker_status_write_is_search_owned_and_monitor_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-03/D-11: worker status is derived search state, not monitor state."""
    from codexbot.search.contracts import SearchWorkerStatus
    from codexbot.search.state import (
        read_worker_status,
        worker_status_path,
        write_worker_status,
    )

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    monitor_state = tmp_path / "monitor_state.json"
    original_monitor = b'{"tracked_sessions":{"s1":{"last_byte_offset":42}}}\n'
    monitor_state.write_bytes(original_monitor)

    status = SearchWorkerStatus(
        status="running",
        current_task="initial_backfill",
        heartbeat_at="2026-05-21T21:00:00Z",
        counters=SearchCounters(
            open_sessions=3,
            indexed_sessions=1,
            indexed_chunks=9,
            failed_items=0,
        ),
    )

    write_worker_status(status)

    assert worker_status_path() == tmp_path / "search" / "worker_status.json"
    assert worker_status_path().exists()
    assert monitor_state.read_bytes() == original_monitor
    assert read_worker_status() == status


def test_running_worker_status_makes_search_status_building(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-13/D-14: running initial backfill is exposed as building status."""
    from codexbot.search.client import get_status
    from codexbot.search.contracts import SearchWorkerStatus
    from codexbot.search.state import write_worker_status

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    write_worker_status(
        SearchWorkerStatus(
            status="running",
            current_task="initial_backfill",
            heartbeat_at="2026-05-21T21:01:00Z",
            counters=SearchCounters(
                open_sessions=2,
                indexed_sessions=1,
                indexed_chunks=11,
                failed_items=0,
            ),
        )
    )

    body = get_status(open_session_count=5).model_dump(mode="json")

    assert body["state"] == "building"
    assert body["available"] is False
    assert body["generation"] is None
    assert body["counters"] == {
        "open_sessions": 5,
        "indexed_sessions": 1,
        "indexed_chunks": 11,
        "queued_items": 0,
        "failed_items": 0,
    }


def test_failed_worker_status_is_sanitized(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T-02-06: status reports failure without leaking local/private details."""
    from codexbot.search.client import get_status
    from codexbot.search.contracts import SearchWorkerStatus
    from codexbot.search.state import write_worker_status

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    write_worker_status(
        SearchWorkerStatus(
            status="failed",
            current_task="initial_backfill",
            heartbeat_at="2026-05-21T21:02:00Z",
            recent_error=(
                "Traceback (most recent call last):\n"
                "WEB_UI_PASSWORD=secret\n"
                f"{tmp_path}/sessions/session.jsonl\n"
                "raw transcript content should not leak"
            ),
            counters=SearchCounters(
                open_sessions=1,
                indexed_sessions=0,
                indexed_chunks=0,
                failed_items=1,
            ),
        )
    )

    body = get_status(open_session_count=1).model_dump(mode="json")
    serialized = json.dumps(body)

    assert body["state"] == "unavailable"
    assert body["available"] is False
    assert body["counters"]["failed_items"] == 1
    assert "search worker failed" in (body["reason"] or "")
    for forbidden in (
        "Traceback",
        "WEB_UI_PASSWORD",
        "secret",
        str(tmp_path),
        "session.jsonl",
        "raw transcript content",
    ):
        assert forbidden not in serialized


def test_pyproject_exposes_search_worker_script() -> None:
    """D-01: the local search worker has an explicit CLI/process boundary."""
    data = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))

    assert (
        data["project"]["scripts"]["codexbot-search-worker"]
        == "codexbot.search.worker:main"
    )
