"""Durable live search queue tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from codexbot.search.contracts import (
    SearchBackfillDocument,
    SearchRoutingMetadata,
    SearchRowIdentity,
    TranscriptProvenance,
)


def _doc(
    *,
    text: str = "hello from transcript",
    offset: int = 10,
    index: int = 0,
    chunk_index: int = 0,
    cwd: str = "/repo",
    window_id: str = "@1",
) -> SearchBackfillDocument:
    provenance = TranscriptProvenance(
        runtime="codex",
        session_id="session-1",
        transcript_source="/tmp/session-1.jsonl",
        transcript_offset=offset,
        transcript_index=index,
        role="assistant",
        content_type="text",
        source_event_kind="parsed_entry",
        timestamp="2026-05-22T10:00:00Z",
    )
    return SearchBackfillDocument(
        identity=SearchRowIdentity.from_provenance(
            provenance,
            chunk_index=chunk_index,
        ),
        provenance=provenance,
        routing=SearchRoutingMetadata(
            window_id=window_id,
            name="codex",
            cwd=cwd,
            runtime="codex",
            session_id="session-1",
        ),
        text=text,
        timestamp=provenance.timestamp,
        source_order=offset,
        chunk_index=chunk_index,
        chunk_count=1,
    )


def test_queue_path_is_search_owned_and_monitor_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.queue import enqueue_document
    from codexbot.search.state import queue_db_path

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    monitor_state = tmp_path / "monitor_state.json"
    session_state = tmp_path / "state.json"
    monitor_state.write_text('{"ok": true}\n', encoding="utf-8")
    session_state.write_text('{"ok": true}\n', encoding="utf-8")

    enqueue_document(_doc())

    assert queue_db_path() == tmp_path / "search" / "queue.sqlite"
    assert queue_db_path().exists()
    assert monitor_state.read_text(encoding="utf-8") == '{"ok": true}\n'
    assert session_state.read_text(encoding="utf-8") == '{"ok": true}\n'


def test_duplicate_enqueue_is_idempotent_and_identity_is_routing_independent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.queue import (
        enqueue_document,
        get_queue_snapshot,
        queue_id_for_document,
        read_queue_item,
    )

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    first = _doc(cwd="/repo/first", window_id="@1")
    second = _doc(cwd="/repo/renamed", window_id="@99")

    first_id = enqueue_document(first)
    second_id = enqueue_document(second)
    item = read_queue_item(first_id)

    assert first_id == second_id == queue_id_for_document(first)
    assert get_queue_snapshot().queued_items == 1
    assert item is not None
    assert item.queue_id == first_id
    assert item.identity == first.identity
    assert item.document.identity == first.identity
    assert item.document.routing.cwd == "/repo/renamed"


def test_leases_expire_and_bounded_retries_dead_letter_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.queue import (
        enqueue_document,
        fail_item,
        get_queue_snapshot,
        lease_ready_items,
        read_queue_item,
    )

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    queue_id = enqueue_document(_doc())
    now = datetime(2026, 5, 22, 10, 0, tzinfo=UTC)

    [leased] = lease_ready_items(
        limit=1,
        lease_owner="worker-a",
        lease_seconds=1,
        now=now,
    )
    assert leased.queue_id == queue_id
    assert leased.status == "leased"
    assert leased.attempts == 1
    assert leased.lease_owner == "worker-a"
    assert leased.lease_expires_at is not None

    assert lease_ready_items(limit=1, now=now) == []

    [expired] = lease_ready_items(limit=1, now=now + timedelta(seconds=2))
    assert expired.queue_id == queue_id
    assert expired.attempts == 2

    assert fail_item(queue_id, "WEB_UI_PASSWORD=secret /tmp/private.jsonl", max_attempts=3) == "queued"
    [retry] = lease_ready_items(limit=1, now=now + timedelta(seconds=3))
    assert retry.attempts == 3
    assert fail_item(queue_id, RuntimeError("raw transcript content"), max_attempts=3) == "failed"

    failed = read_queue_item(queue_id)
    assert failed is not None
    assert failed.status == "failed"
    assert failed.last_error is not None
    assert "raw transcript content" in failed.last_error
    snapshot = get_queue_snapshot()
    assert snapshot.failed_items == 1
    assert snapshot.recent_error is not None
    assert "WEB_UI_PASSWORD" not in snapshot.recent_error
    assert "secret" not in snapshot.recent_error
    assert "/tmp/private" not in snapshot.recent_error


def test_watermarks_persist_by_runtime_and_transcript_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.queue import read_watermark, upsert_watermark

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))

    upsert_watermark(
        runtime="codex",
        session_id="session-1",
        transcript_source="/tmp/session-1.jsonl",
        transcript_offset=512,
        transcript_index=7,
    )

    watermark = read_watermark("codex", "/tmp/session-1.jsonl")
    assert watermark is not None
    assert watermark.runtime == "codex"
    assert watermark.session_id == "session-1"
    assert watermark.transcript_offset == 512
    assert watermark.transcript_index == 7


def test_search_status_includes_queue_lag_and_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.client import get_status
    from codexbot.search.queue import enqueue_document, fail_item, lease_ready_items

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    queue_id = enqueue_document(_doc())
    lease_ready_items(limit=1)
    fail_item(queue_id, "queue write failed", max_attempts=1)

    body = get_status(open_session_count=2).model_dump(mode="json")

    assert body["state"] == "degraded"
    assert body["available"] is False
    assert body["counters"]["open_sessions"] == 2
    assert body["counters"]["failed_items"] == 1
    assert "queue" in body["reason"]
