"""Search state namespace and missing-index provider tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codexbot.search.contracts import SearchRequest


def _manifest(
    generation_id: str,
    *,
    completed: bool = True,
    indexed_chunks: int = 4,
):
    from codexbot.search.contracts import SearchBackfillManifest, SearchCounters

    return SearchBackfillManifest(
        generation={
            "schema_version": 1,
            "generation_id": generation_id,
            "created_at": "2026-05-21T22:20:00Z",
            "active": False,
        },
        counters=SearchCounters(
            open_sessions=2,
            indexed_sessions=2,
            indexed_chunks=indexed_chunks,
            failed_items=0,
        ),
        document_count=indexed_chunks,
        completed=completed,
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


def test_search_dir_resolves_configured_and_default_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-09: search state lives under the configured Codi state directory."""
    from codexbot.search.state import search_dir

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    assert search_dir() == tmp_path / "search"

    monkeypatch.delenv("CODEXBOT_DIR", raising=False)
    assert search_dir() == Path.home() / ".codexbot" / "search"


def test_queue_db_path_stays_under_search_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-10: live queue state is search-owned, not monitor/session state."""
    from codexbot.search.state import queue_db_path, search_dir

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))

    assert queue_db_path() == tmp_path / "search" / "queue.sqlite"
    assert queue_db_path().parent == search_dir()
    assert queue_db_path().is_relative_to(search_dir())


def test_generation_metadata_path_stays_under_search_dir_and_missing_reads_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CORP-06 and D-11: generation metadata is derived search-owned state."""
    from codexbot.search.state import (
        generation_metadata_path,
        read_generation_metadata,
        search_dir,
    )

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))

    metadata_path = generation_metadata_path()

    assert metadata_path.parent == search_dir()
    assert metadata_path.is_relative_to(search_dir())
    assert read_generation_metadata() is None


def test_generation_metadata_reader_rejects_non_active_or_invalid_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-11: only active metadata for the current schema is trusted."""
    from codexbot.search.state import (
        SEARCH_SCHEMA_VERSION,
        generation_metadata_path,
        read_generation_metadata,
    )

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    metadata_path = generation_metadata_path()
    metadata_path.parent.mkdir(parents=True)

    metadata_path.write_text("{invalid json", encoding="utf-8")
    assert read_generation_metadata() is None

    metadata_path.write_text(
        json.dumps(
            {
                "schema_version": SEARCH_SCHEMA_VERSION + 1,
                "generation_id": "gen-newer",
                "created_at": "2026-05-21T13:00:00Z",
                "active": True,
            }
        ),
        encoding="utf-8",
    )
    assert read_generation_metadata() is None

    metadata_path.write_text(
        json.dumps(
            {
                "schema_version": SEARCH_SCHEMA_VERSION,
                "generation_id": "gen-inactive",
                "created_at": "2026-05-21T13:00:00Z",
                "active": False,
            }
        ),
        encoding="utf-8",
    )
    assert read_generation_metadata() is None


def test_activate_generation_is_success_only_and_atomic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-09: active metadata is written only after a complete generation exists."""
    from codexbot.search.state import (
        activate_generation,
        active_generation_metadata_path,
        read_generation_metadata,
    )

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    incomplete = _manifest("gen-incomplete", completed=False)
    _write_generation_files("gen-incomplete", incomplete)

    with pytest.raises(ValueError):
        activate_generation(incomplete)

    assert read_generation_metadata() is None
    assert not active_generation_metadata_path().exists()

    complete = _manifest("gen-complete", completed=True)
    _write_generation_files("gen-complete", complete)
    activated = activate_generation(complete)

    assert activated.active is True
    assert read_generation_metadata() == activated
    assert active_generation_metadata_path().exists()


def test_incomplete_generation_manifest_is_ignored_by_recovery_and_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-12/D-15: interrupted generations stay inactive and rerunnable."""
    from codexbot.search.client import get_status
    from codexbot.search.state import read_generation_manifest, read_generation_metadata

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    incomplete = _manifest("gen-interrupted", completed=False)
    _write_generation_files("gen-interrupted", incomplete)

    assert read_generation_manifest("gen-interrupted") is None
    assert read_generation_metadata() is None
    status = get_status(open_session_count=2).model_dump(mode="json")
    assert status["state"] == "missing"
    assert status["available"] is False
    assert status["generation"] is None


def test_active_generation_without_query_backend_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-05 and D-11: active metadata does not imply query availability yet."""
    from codexbot.search.client import get_status, search
    from codexbot.search.state import SEARCH_SCHEMA_VERSION, generation_metadata_path

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    metadata_path = generation_metadata_path()
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text(
        json.dumps(
            {
                "schema_version": SEARCH_SCHEMA_VERSION,
                "generation_id": "gen-active",
                "created_at": "2026-05-21T13:00:00Z",
                "active": True,
            }
        ),
        encoding="utf-8",
    )

    status = get_status(open_session_count=3).model_dump(mode="json")
    response = search(SearchRequest(query="term")).model_dump(mode="json")

    assert status["state"] == "unavailable"
    assert status["available"] is False
    assert status["reason"] == "search query backend is not available"
    assert status["counters"]["open_sessions"] == 3
    assert status["generation"]["generation_id"] == "gen-active"
    assert response["status"]["state"] == "unavailable"
    assert response["status"]["available"] is False
    assert response["outcome"] == "not_ready"
    assert response["results"] == []


def test_active_generation_status_reads_manifest_counters_and_degrades_to_lexical(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-14/D-15: completed Phase 2 backfill is visible but not query-ready."""
    from codexbot.search.client import get_status, search
    from codexbot.search.state import activate_generation

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    manifest = _manifest("gen-active", indexed_chunks=9)
    _write_generation_files("gen-active", manifest)
    activate_generation(manifest)

    status = get_status(open_session_count=5).model_dump(mode="json")
    response = search(SearchRequest(query="term")).model_dump(mode="json")

    assert status["state"] == "degraded"
    assert status["available"] is True
    assert (
        status["reason"] == "semantic index is unavailable; lexical search is available"
    )
    assert status["generation"]["generation_id"] == "gen-active"
    assert status["counters"] == {
        "open_sessions": 5,
        "indexed_sessions": 2,
        "indexed_chunks": 9,
        "queued_items": 0,
        "failed_items": 0,
    }
    assert response["status"]["generation"]["generation_id"] == "gen-active"
    assert response["outcome"] == "ok"
    assert response["results"] == []


def test_search_state_does_not_modify_monitor_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-10 and T-01-04: status/search do not mutate monitor_state.json."""
    from codexbot.search.client import get_status, search

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    monitor_state = tmp_path / "monitor_state.json"
    original_bytes = (
        b'{"tracked_sessions":{"s1":{"session_id":"s1","file_path":"/a.jsonl",'
        b'"last_byte_offset":42}}}\n'
    )
    monitor_state.write_bytes(original_bytes)

    get_status()
    search(SearchRequest(query="term"))

    assert monitor_state.read_bytes() == original_bytes

    monitor_state.unlink()
    get_status()
    search(SearchRequest(query="term"))

    assert not monitor_state.exists()


def test_missing_index_status_serializes_as_safe_typed_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-05, D-07, and T-01-03: missing-index status is typed and safe."""
    from codexbot.search.client import get_status

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    monkeypatch.setenv("WEB_UI_PASSWORD", "super-secret-password")

    body = get_status().model_dump(mode="json")

    assert body["state"] == "missing"
    assert body["available"] is False
    assert body["scope"] == "open_sessions"
    assert body["counters"] is None
    assert body["generation"] is None

    status_with_count = get_status(open_session_count=7).model_dump(mode="json")
    assert status_with_count["counters"]["open_sessions"] == 7

    serialized = json.dumps(body)
    assert str(tmp_path) not in serialized
    assert "WEB_UI_PASSWORD" not in serialized
    assert "super-secret-password" not in serialized
    assert "raw transcript content" not in serialized
    assert "/tmp/" not in serialized


def test_missing_index_search_returns_not_ready_empty_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-05 and D-07: search returns a typed not-ready response, not an error."""
    from codexbot.search.client import search

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))

    body = search(SearchRequest(query="term", limit=7, hits_per_session=2)).model_dump(
        mode="json"
    )

    assert body["query"] == "term"
    assert body["status"]["state"] == "missing"
    assert body["status"]["available"] is False
    assert body["results"] == []
    assert body["total_results"] == 0
    assert body["limit"] == 7
    assert body["hits_per_session"] == 2
    assert body["outcome"] == "not_ready"
