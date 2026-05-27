"""Durable live search queue tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from codexbot.session import CodexSession, ParsedTranscriptSession, WindowState
from codexbot.search.contracts import (
    SearchBackfillDocument,
    SearchRoutingMetadata,
    SearchRowIdentity,
    TranscriptProvenance,
)
from codexbot.session_monitor import NewMessage
from codexbot.tmux_manager import TmuxWindow
from codexbot.transcript_parser import ParsedEntry


class FakeTmuxManager:
    def __init__(self, windows: list[TmuxWindow]) -> None:
        self.windows = windows

    async def list_windows(self) -> list[TmuxWindow]:
        return list(self.windows)


class FakeSessionManager:
    def __init__(self, source: ParsedTranscriptSession | None) -> None:
        self.source = source
        self.window_states = {
            "@1": WindowState(
                session_id="session-1",
                cwd="/repo",
                window_name="codex",
                runtime="codex",
            )
        }

    async def read_parsed_transcript_for_window(
        self,
        window_id: str,
    ) -> ParsedTranscriptSession | None:
        if window_id == "@1":
            return self.source
        return None


def _doc(
    *,
    text: str = "hello from transcript",
    offset: int = 10,
    index: int = 0,
    chunk_index: int = 0,
    cwd: str = "/repo",
    window_id: str = "@1",
    transcript_source: str = "/tmp/session-1.jsonl",
) -> SearchBackfillDocument:
    provenance = TranscriptProvenance(
        runtime="codex",
        session_id="session-1",
        transcript_source=transcript_source,
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


def _source(entries: list[ParsedEntry] | None = None) -> ParsedTranscriptSession:
    return ParsedTranscriptSession(
        window_id="@1",
        session=CodexSession("session-1", "", 1, "/tmp/session-1.jsonl"),
        state=WindowState(
            session_id="session-1",
            cwd="/repo",
            window_name="codex",
            runtime="codex",
        ),
        transcript_source="/tmp/session-1.jsonl",
        entries=entries or [],
        pending_tools={},
    )


def _source_with_path(path: str) -> ParsedTranscriptSession:
    source = _source([])
    return ParsedTranscriptSession(
        window_id=source.window_id,
        session=source.session,
        state=source.state,
        transcript_source=path,
        entries=source.entries,
        pending_tools=source.pending_tools,
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

    assert (
        fail_item(queue_id, "WEB_UI_PASSWORD=secret /tmp/private.jsonl", max_attempts=3)
        == "queued"
    )
    [retry] = lease_ready_items(limit=1, now=now + timedelta(seconds=3))
    assert retry.attempts == 3
    assert (
        fail_item(queue_id, RuntimeError("raw transcript content"), max_attempts=3)
        == "failed"
    )

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


@pytest.mark.asyncio
async def test_live_producer_enqueues_useful_monitor_messages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.live import LiveQueueProducer
    from codexbot.search.queue import get_queue_snapshot, read_watermark

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    producer = LiveQueueProducer(
        session_manager=FakeSessionManager(_source()),
        tmux_manager=FakeTmuxManager([TmuxWindow("@1", "codex", "/repo", "codex")]),
    )

    await producer.listener(
        NewMessage(
            session_id="session-1",
            text="live answer",
            is_complete=False,
            role="assistant",
            content_type="text",
            timestamp="2026-05-22T10:00:00Z",
            transcript_offset=100,
            transcript_index=2,
        )
    )
    await producer.drain_pending()

    snapshot = get_queue_snapshot()
    assert snapshot.queued_items == 1
    watermark = read_watermark("codex", "/tmp/session-1.jsonl")
    assert watermark is not None
    assert watermark.transcript_offset == 100

    from codexbot.search.queue import lease_ready_items

    [item] = lease_ready_items(limit=1)
    assert item.document.text == "live answer"
    assert item.document.provenance.transcript_offset == 100
    assert item.document.routing.window_id == "@1"


@pytest.mark.asyncio
async def test_live_producer_skips_completion_and_empty_messages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.live import LiveQueueProducer
    from codexbot.search.queue import get_queue_snapshot

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    producer = LiveQueueProducer(
        session_manager=FakeSessionManager(_source()),
        tmux_manager=FakeTmuxManager([TmuxWindow("@1", "codex", "/repo", "codex")]),
    )

    await producer.enqueue_message(
        NewMessage(
            session_id="session-1",
            text="",
            is_complete=True,
            message_type="completion",
            content_type="completion",
        )
    )
    await producer.enqueue_message(
        NewMessage(session_id="session-1", text="   ", is_complete=False)
    )

    assert get_queue_snapshot().queued_items == 0


@pytest.mark.asyncio
async def test_live_producer_records_safe_errors_without_raising(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search import live
    from codexbot.search.live import LiveQueueProducer
    from codexbot.search.queue import get_queue_snapshot

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))

    def fail_enqueue(_documents: list[SearchBackfillDocument]) -> list[str]:
        raise RuntimeError("WEB_UI_PASSWORD=secret /tmp/session.jsonl")

    monkeypatch.setattr(live, "enqueue_documents", fail_enqueue)
    producer = LiveQueueProducer(
        session_manager=FakeSessionManager(_source()),
        tmux_manager=FakeTmuxManager([TmuxWindow("@1", "codex", "/repo", "codex")]),
    )

    await producer.enqueue_message(
        NewMessage(
            session_id="session-1",
            text="live answer",
            is_complete=False,
            transcript_offset=1,
            transcript_index=0,
        )
    )

    snapshot = get_queue_snapshot()
    assert snapshot.recent_error is not None
    assert "WEB_UI_PASSWORD" not in snapshot.recent_error
    assert "secret" not in snapshot.recent_error
    assert "/tmp/session" not in snapshot.recent_error


@pytest.mark.asyncio
async def test_replay_uses_watermarks_and_updates_after_enqueue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.live import replay_open_session_queue
    from codexbot.search.queue import (
        get_queue_snapshot,
        lease_ready_items,
        read_watermark,
        upsert_watermark,
    )

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    monitor_state = tmp_path / "monitor_state.json"
    monitor_state.write_text('{"tracked_sessions":{}}\n', encoding="utf-8")
    entries = [
        ParsedEntry(
            role="assistant",
            text="already queued",
            content_type="text",
            transcript_offset=10,
            transcript_index=0,
        ),
        ParsedEntry(
            role="assistant",
            text="missed after restart",
            content_type="text",
            transcript_offset=20,
            transcript_index=0,
        ),
    ]
    upsert_watermark(
        runtime="codex",
        session_id="session-1",
        transcript_source="/tmp/session-1.jsonl",
        transcript_offset=10,
        transcript_index=0,
    )

    queued = await replay_open_session_queue(
        session_manager=FakeSessionManager(_source(entries)),
        tmux_manager=FakeTmuxManager([TmuxWindow("@1", "codex", "/repo", "codex")]),
    )

    assert queued == 1
    assert get_queue_snapshot().queued_items == 1
    [item] = lease_ready_items(limit=1)
    assert item.document.text == "missed after restart"
    watermark = read_watermark("codex", "/tmp/session-1.jsonl")
    assert watermark is not None
    assert watermark.transcript_offset == 20
    assert monitor_state.read_text(encoding="utf-8") == '{"tracked_sessions":{}}\n'


@pytest.mark.asyncio
async def test_stale_source_helper_hides_closed_session_documents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.live import (
        filter_stale_documents,
        read_generation_documents,
        refresh_stale_sources,
        upsert_generation_documents,
    )
    from codexbot.search.queue import list_stale_sources

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    open_doc = _doc(text="open", transcript_source="/tmp/open.jsonl")
    stale_doc = _doc(
        text="closed",
        offset=20,
        index=1,
        transcript_source="/tmp/closed.jsonl",
    )
    upsert_generation_documents("gen-stale", [open_doc, stale_doc])

    stale_sources = await refresh_stale_sources(
        session_manager=FakeSessionManager(_source_with_path("/tmp/open.jsonl")),
        tmux_manager=FakeTmuxManager([TmuxWindow("@1", "codex", "/repo", "codex")]),
        generation_id="gen-stale",
    )

    documents = read_generation_documents("gen-stale")
    routeable = filter_stale_documents(documents)
    assert stale_sources == {"/tmp/closed.jsonl"}
    assert list_stale_sources() == {"/tmp/closed.jsonl"}
    assert [doc.text for doc in routeable] == ["open"]


def test_generation_documents_cache_reuses_and_invalidates_after_upsert(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.live import read_generation_documents, upsert_generation_documents

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    first = _doc(text="cached first", transcript_source="/tmp/cache.jsonl")
    second = first.model_copy(update={"text": "cached updated"})

    upsert_generation_documents("gen-cache", [first])
    first_read = read_generation_documents("gen-cache")
    second_read = read_generation_documents("gen-cache")

    assert first_read is second_read
    assert [document.text for document in first_read] == ["cached first"]

    upsert_generation_documents("gen-cache", [second])
    third_read = read_generation_documents("gen-cache")

    assert third_read is not first_read
    assert [document.text for document in third_read] == ["cached updated"]
