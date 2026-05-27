"""Search worker lifecycle, status, and generation-state tests."""

from __future__ import annotations

import json
import asyncio
import tomllib
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

from codexbot.search.contracts import (
    SearchBackfillDocument,
    SearchCounters,
    SearchRoutingMetadata,
    SearchRowIdentity,
    TranscriptProvenance,
)


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


def _document(index: int, *, text: str | None = None) -> SearchBackfillDocument:
    provenance = TranscriptProvenance(
        runtime="codex",
        session_id="session-1",
        transcript_source="/tmp/session-1.jsonl",
        transcript_offset=index * 10,
        transcript_index=index,
        role="assistant",
        content_type="text",
        source_event_kind="parsed_entry",
        timestamp="2026-05-22T10:00:00Z",
    )
    return SearchBackfillDocument(
        identity=SearchRowIdentity.from_provenance(provenance, chunk_index=0),
        provenance=provenance,
        routing=SearchRoutingMetadata(
            window_id="@1",
            name="codex",
            cwd="/repo",
            runtime="codex",
            session_id="session-1",
        ),
        text=text or f"document {index}",
        timestamp=provenance.timestamp,
        source_order=index * 10,
        chunk_index=0,
        chunk_count=1,
    )


def _activate_empty_generation(tmp_path: Path, generation_id: str = "gen-live") -> None:
    from codexbot.search.state import (
        activate_generation,
        generation_documents_path,
        write_generation_manifest,
    )

    manifest = _manifest(generation_id, indexed_chunks=0)
    docs_path = generation_documents_path(generation_id)
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    docs_path.write_text("", encoding="utf-8")
    write_generation_manifest(manifest)
    activate_generation(manifest)


def _read_docs(generation_id: str) -> list[dict]:
    from codexbot.search.state import generation_documents_path

    path = generation_documents_path(generation_id)
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


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
    monkeypatch.setenv("CODEXBOT_SEARCH_WORKER_STALE_SECONDS", "999999999")
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
    assert body["operations"]["worker"]["stale"] is False
    assert body["operations"]["progress"]["indexed_chunks"] == 11


def test_stale_running_worker_without_generation_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OPS-04: stale workers stop advertising active indexing readiness."""
    from codexbot.search.client import get_status
    from codexbot.search.contracts import SearchWorkerStatus
    from codexbot.search.state import write_worker_status

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    monkeypatch.setenv("CODEXBOT_SEARCH_WORKER_STALE_SECONDS", "1")
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

    body = get_status(open_session_count=2).model_dump(mode="json")

    assert body["state"] == "unavailable"
    assert body["available"] is False
    assert "heartbeat is stale" in (body["reason"] or "")
    assert body["operations"]["worker"]["stale"] is True
    assert body["operations"]["progress"]["indexed_chunks"] == 11


def test_stale_running_worker_with_generation_stays_degraded_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OPS-04/OPS-06: stale worker does not hide usable lexical generation data."""
    from codexbot.search.client import get_status
    from codexbot.search.contracts import SearchWorkerStatus
    from codexbot.search.state import activate_generation, write_worker_status

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    monkeypatch.setenv("CODEXBOT_SEARCH_WORKER_STALE_SECONDS", "1")
    manifest = _manifest("gen-stale", indexed_chunks=3)
    _write_generation_files("gen-stale", manifest)
    activate_generation(manifest)
    write_worker_status(
        SearchWorkerStatus(
            status="running",
            current_task="live_loop",
            heartbeat_at="2026-05-21T21:01:00Z",
        )
    )

    body = get_status(open_session_count=3).model_dump(mode="json")

    assert body["state"] == "degraded"
    assert body["available"] is True
    assert body["generation"]["generation_id"] == "gen-stale"
    assert "heartbeat is stale" in (body["reason"] or "")
    assert body["operations"]["worker"]["stale"] is True


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
    materialize_index = Mock()
    monkeypatch.setattr(
        "codexbot.search.worker.materialize_initial_backfill",
        async_materialize,
    )
    monkeypatch.setattr(
        "codexbot.search.worker.activate_generation",
        activate_generation,
    )
    monkeypatch.setattr(
        "codexbot.search.worker.materialize_generation_index",
        materialize_index,
    )

    assert main(["initial-backfill"]) == 0

    async_materialize.assert_awaited_once()
    materialize_index.assert_called_once()
    args, kwargs = materialize_index.call_args
    assert args == ("gen-test",)
    assert callable(kwargs["progress_callback"])
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
    materialize_index = Mock()
    monkeypatch.setattr(
        "codexbot.search.worker.materialize_initial_backfill",
        async_materialize,
    )
    monkeypatch.setattr(
        "codexbot.search.worker.materialize_generation_index",
        materialize_index,
    )

    assert main(["rebuild"]) == 0

    async_materialize.assert_awaited_once()
    materialize_index.assert_called_once()
    args, kwargs = materialize_index.call_args
    assert args == ("gen-new",)
    assert callable(kwargs["progress_callback"])
    active = read_generation_metadata()
    assert active is not None
    assert active.generation_id == "gen-new"
    assert active.active is True


def test_rebuild_worker_updates_status_during_index_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search import worker

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    manifest = _manifest("gen-progress", indexed_chunks=8)
    _write_generation_files("gen-progress", manifest)
    statuses = []
    real_write_status = worker.write_worker_status

    async_materialize = AsyncMock(return_value=manifest)

    def capture_status(status) -> None:
        statuses.append(status)
        real_write_status(status)

    def materialize_index(_generation_id: str, **kwargs: object) -> None:
        progress_callback = kwargs["progress_callback"]
        assert callable(progress_callback)
        progress_callback(3)
        progress_callback(8)

    monkeypatch.setattr(worker, "materialize_initial_backfill", async_materialize)
    monkeypatch.setattr(worker, "materialize_generation_index", materialize_index)
    monkeypatch.setattr(worker, "write_worker_status", capture_status)

    assert worker.main(["rebuild"]) == 0

    running_counts = [
        status.counters.indexed_chunks
        for status in statuses
        if status.status == "running" and status.counters is not None
    ]
    assert 0 in running_counts
    assert 3 in running_counts
    assert 8 in running_counts
    assert statuses[-1].status == "completed"
    assert statuses[-1].counters == manifest.counters


def test_smoke_search_index_reports_model_dimension_and_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from codexbot.search.contracts import SearchIndexMetadata
    from codexbot.search.worker import main

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))

    def fake_materialize(generation_id: str, **_kwargs: object) -> SearchIndexMetadata:
        return SearchIndexMetadata(
            schema_version=1,
            generation_id=generation_id,
            model_id="fake/qwen",
            vector_dimension=1024,
            table_name="chunks",
            created_at="2026-05-22T10:00:00Z",
            completed=True,
        )

    monkeypatch.setattr(
        "codexbot.search.worker.materialize_generation_index",
        fake_materialize,
    )

    assert main(["smoke-search-index"]) == 0
    body = json.loads(capsys.readouterr().out)
    assert body["ok"] is True
    assert body["model_id"] == "fake/qwen"
    assert body["vector_dimension"] == 1024
    assert body["index_path"].endswith("/lancedb")


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


def test_live_drain_flushes_at_32_ready_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.queue import (
        enqueue_documents,
        get_queue_snapshot,
        record_queue_error,
    )
    from codexbot.search.worker import drain_live_queue_once

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    _activate_empty_generation(tmp_path)
    upsert_index = Mock()
    monkeypatch.setattr("codexbot.search.worker.upsert_index_documents", upsert_index)
    record_queue_error("transient queue error")
    enqueue_documents([_document(i) for i in range(31)])

    assert drain_live_queue_once(batch_size=32) == 0
    assert get_queue_snapshot().queued_items == 31
    assert get_queue_snapshot().recent_error is not None

    enqueue_documents([_document(31)])

    assert drain_live_queue_once(batch_size=32) == 32
    upsert_index.assert_called_once()
    assert get_queue_snapshot().queued_items == 0
    assert get_queue_snapshot().recent_error is None
    assert len(_read_docs("gen-live")) == 32


def test_live_drain_flushes_smaller_batch_after_timer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import UTC, datetime, timedelta

    from codexbot.search import worker
    from codexbot.search.queue import enqueue_documents, get_queue_snapshot

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    _activate_empty_generation(tmp_path)
    upsert_index = Mock()
    monkeypatch.setattr("codexbot.search.worker.upsert_index_documents", upsert_index)
    base = datetime(2026, 5, 22, 10, 0, tzinfo=UTC)
    worker._last_live_flush_at = base
    enqueue_documents([_document(1), _document(2)])

    assert (
        worker.drain_live_queue_once(
            batch_size=32,
            flush_interval_seconds=60,
            now=base + timedelta(seconds=59),
        )
        == 0
    )
    assert get_queue_snapshot().queued_items == 2

    assert (
        worker.drain_live_queue_once(
            batch_size=32,
            flush_interval_seconds=60,
            now=base + timedelta(seconds=60),
        )
        == 2
    )
    upsert_index.assert_called_once()
    assert get_queue_snapshot().queued_items == 0
    worker._last_live_flush_at = None


def test_generation_document_upsert_is_idempotent_and_updates_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.live import (
        read_generation_documents,
        upsert_generation_documents,
    )
    from codexbot.search.state import read_generation_manifest

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    _activate_empty_generation(tmp_path)

    first = _document(1, text="first")
    second = first.model_copy(update={"text": "updated"})

    assert upsert_generation_documents("gen-live", [first]) == 1
    assert upsert_generation_documents("gen-live", [second]) == 1

    documents = read_generation_documents("gen-live")
    manifest = read_generation_manifest("gen-live")
    assert len(documents) == 1
    assert documents[0].text == "updated"
    assert manifest is not None
    assert manifest.document_count == 1
    assert manifest.counters.indexed_chunks == 1


def test_live_drain_retries_then_dead_letters_and_explicitly_requeues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search import worker
    from codexbot.search.queue import (
        enqueue_documents,
        get_queue_snapshot,
        read_queue_item,
        requeue_failed_items,
    )

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    _activate_empty_generation(tmp_path)
    [queue_id] = enqueue_documents([_document(1)])

    def fail_upsert(
        _generation_id: str, _documents: list[SearchBackfillDocument]
    ) -> int:
        raise RuntimeError("temporary write failure")

    monkeypatch.setattr(worker, "upsert_index_documents", fail_upsert)

    assert worker.drain_live_queue_once(force=True, max_attempts=2) == 0
    assert read_queue_item(queue_id).status == "queued"  # type: ignore[union-attr]

    assert worker.drain_live_queue_once(force=True, max_attempts=2) == 0
    failed = read_queue_item(queue_id)
    assert failed is not None
    assert failed.status == "failed"
    assert get_queue_snapshot().failed_items == 1

    assert requeue_failed_items() == 1
    requeued = read_queue_item(queue_id)
    assert requeued is not None
    assert requeued.status == "queued"
    assert requeued.attempts == 0


def test_failed_queue_rows_do_not_block_later_live_drain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search import worker
    from codexbot.search.queue import (
        enqueue_documents,
        fail_items,
        get_queue_snapshot,
        lease_ready_items,
        read_queue_item,
    )

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    _activate_empty_generation(tmp_path)
    [failed_id] = enqueue_documents([_document(1, text="failed")])
    lease_ready_items(limit=1)
    fail_items([failed_id], RuntimeError("dead letter"), max_attempts=1)
    [later_id] = enqueue_documents([_document(2, text="later")])
    upsert_index = Mock()
    monkeypatch.setattr(worker, "upsert_index_documents", upsert_index)

    assert worker.drain_live_queue_once(force=True) == 1

    failed = read_queue_item(failed_id)
    later = read_queue_item(later_id)
    assert failed is not None
    assert later is not None
    assert failed.status == "failed"
    assert later.status == "done"
    assert get_queue_snapshot().failed_items == 1
    upsert_index.assert_called_once()


@pytest.mark.asyncio
async def test_supervisor_live_queue_loop_runs_drain_without_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from codexbot.search import supervisor

    calls = 0

    def fake_drain() -> int:
        nonlocal calls
        calls += 1
        if calls >= 2:
            raise asyncio.CancelledError
        return 0

    async def fake_sleep(_seconds: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(supervisor, "drain_live_queue_once", fake_drain)
    monkeypatch.setattr(supervisor.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await supervisor.live_queue_loop()

    assert calls == 1


@pytest.mark.asyncio
async def test_supervisor_start_worker_ignores_subprocess_launch_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search import supervisor

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))

    async def fake_create_subprocess_exec(*_args: object, **_kwargs: object) -> object:
        raise OSError("worker executable missing")

    monkeypatch.setattr(
        supervisor.asyncio,
        "create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    await supervisor.start_worker_if_needed()


@pytest.mark.asyncio
async def test_supervisor_live_queue_loop_continues_after_ordinary_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from codexbot.search import supervisor

    calls = 0
    sleeps = 0

    def fake_drain() -> int:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("index write failed")
        raise asyncio.CancelledError

    async def fake_sleep(_seconds: float) -> None:
        nonlocal sleeps
        sleeps += 1

    monkeypatch.setattr(supervisor, "drain_live_queue_once", fake_drain)
    monkeypatch.setattr(supervisor.asyncio, "sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await supervisor.live_queue_loop()

    assert calls == 2
    assert sleeps == 1
