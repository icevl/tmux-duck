"""Search worker lifecycle, status, and generation-state tests."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from codexbot.search.contracts import SearchCounters


def _manifest(generation_id: str, *, indexed_chunks: int = 7):
    from codexbot.search.contracts import SearchBackfillManifest

    return SearchBackfillManifest(
        generation={
            "schema_version": 1,
            "generation_id": generation_id,
            "created_at": "2026-05-21T21:30:00Z",
            "active": False,
        },
        counters=SearchCounters(
            open_sessions=2,
            indexed_sessions=2,
            indexed_chunks=indexed_chunks,
            failed_items=0,
        ),
        document_count=indexed_chunks,
        completed=True,
        errors=[],
    )


def _write_generation_files(generation_id: str, manifest) -> None:
    from codexbot.search.state import (
        generation_documents_path,
        write_generation_manifest,
    )

    docs_path = generation_documents_path(generation_id)
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    docs_path.write_text('{"text":"indexed"}\n', encoding="utf-8")
    write_generation_manifest(manifest)


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


def test_initial_backfill_worker_materializes_generation_and_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Worker command writes artifacts and a completed status for the generation."""
    from codexbot.search.state import read_worker_status
    from codexbot.search.worker import main

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    manifest = _manifest("gen-test")

    async_materialize = AsyncMock(return_value=manifest)
    activate_generation = Mock(return_value=manifest.generation)
    monkeypatch.setattr(
        "codexbot.search.worker.materialize_initial_backfill",
        async_materialize,
    )
    monkeypatch.setattr(
        "codexbot.search.worker.activate_generation",
        activate_generation,
    )

    assert main(["initial-backfill"]) == 0

    async_materialize.assert_awaited_once()
    activate_generation.assert_called_once_with(manifest)
    status = read_worker_status()
    assert status is not None
    assert status.status == "completed"
    assert status.current_task == "initial_backfill"
    assert status.counters == manifest.counters


def test_rebuild_worker_activates_fresh_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-04/D-10: explicit local rebuild creates and activates a new generation."""
    from codexbot.search.state import activate_generation, read_generation_metadata
    from codexbot.search.worker import main

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    old_manifest = _manifest("gen-old", indexed_chunks=1)
    _write_generation_files("gen-old", old_manifest)
    activate_generation(old_manifest)

    new_manifest = _manifest("gen-new", indexed_chunks=8)
    _write_generation_files("gen-new", new_manifest)
    async_materialize = AsyncMock(return_value=new_manifest)
    monkeypatch.setattr(
        "codexbot.search.worker.materialize_initial_backfill",
        async_materialize,
    )

    assert main(["rebuild"]) == 0

    async_materialize.assert_awaited_once()
    active = read_generation_metadata()
    assert active is not None
    assert active.generation_id == "gen-new"
    assert active.active is True


@pytest.mark.asyncio
async def test_supervisor_starts_initial_backfill_only_when_no_active_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-04/D-12: startup reruns missing generation and skips active generation."""
    from codexbot.search import supervisor
    from codexbot.search.state import activate_generation

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    async def fake_create_subprocess_exec(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        return object()

    monkeypatch.setattr(
        supervisor.asyncio,
        "create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    await supervisor.start_worker_if_needed()
    assert len(calls) == 1
    assert calls[0][0][-1] == "initial-backfill"

    calls.clear()
    active_manifest = _manifest("gen-active", indexed_chunks=3)
    _write_generation_files("gen-active", active_manifest)
    activate_generation(active_manifest)

    await supervisor.start_worker_if_needed()
    assert calls == []
