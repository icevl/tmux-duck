"""Search retrieval and exact-first ranking tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codexbot.search.contracts import (
    SearchBackfillDocument,
    SearchBackfillManifest,
    SearchCounters,
    SearchRequest,
    SearchRoutingMetadata,
    SearchRowIdentity,
    TranscriptProvenance,
)


def _doc(
    *,
    text: str,
    window_id: str = "@1",
    name: str = "codex",
    cwd: str = "/repo/codi",
    runtime: str = "codex",
    session_id: str = "session-1",
    role: str = "assistant",
    content_type: str = "text",
    status: str | None = "active",
    pinned: bool = False,
    source_order: int = 1,
    transcript_source: str = "/tmp/session-1.jsonl",
    timestamp: str = "2026-05-22T10:00:00Z",
) -> SearchBackfillDocument:
    provenance = TranscriptProvenance(
        runtime=runtime,
        session_id=session_id,
        transcript_source=transcript_source,
        transcript_offset=source_order,
        transcript_index=source_order,
        role=role,
        content_type=content_type,
        source_event_kind="parsed_entry",
        timestamp=timestamp,
    )
    return SearchBackfillDocument(
        identity=SearchRowIdentity.from_provenance(provenance, chunk_index=0),
        provenance=provenance,
        routing=SearchRoutingMetadata(
            window_id=window_id,
            name=name,
            cwd=cwd,
            runtime=runtime,
            session_id=session_id,
            status=status,
            pinned=pinned,
        ),
        text=text,
        timestamp=timestamp,
        source_order=source_order,
        chunk_index=0,
        chunk_count=1,
    )


def _activate_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    documents: list[SearchBackfillDocument],
    *,
    generation_id: str = "gen-retrieval",
) -> None:
    from codexbot.search.state import (
        activate_generation,
        generation_documents_path,
        write_generation_manifest,
    )

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    docs_path = generation_documents_path(generation_id)
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    docs_path.write_text(
        "".join(
            json.dumps(doc.model_dump(mode="json"), ensure_ascii=False) + "\n"
            for doc in documents
        ),
        encoding="utf-8",
    )
    manifest = SearchBackfillManifest(
        generation={
            "schema_version": 1,
            "generation_id": generation_id,
            "created_at": "2026-05-22T10:00:00Z",
            "active": False,
        },
        counters=SearchCounters(
            open_sessions=len({doc.routing.window_id for doc in documents}),
            indexed_sessions=len({doc.routing.session_id for doc in documents}),
            indexed_chunks=len(documents),
            failed_items=0,
        ),
        document_count=len(documents),
        completed=True,
        errors=[],
    )
    write_generation_manifest(manifest)
    activate_generation(manifest)


def test_lexical_exact_technical_match_returns_grouped_highlighted_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.client import search

    _activate_generation(
        tmp_path,
        monkeypatch,
        [
            _doc(
                text="Failure is in src/codexbot/web/api.py after RuntimeError stack trace",
                window_id="@10",
                name="direct",
                source_order=1,
            ),
            _doc(
                text="api api api api api general discussion without the exact path",
                window_id="@11",
                name="repeated",
                source_order=2,
            ),
        ],
    )

    body = search(
        SearchRequest(query="src/codexbot/web/api.py", limit=5, hits_per_session=3)
    ).model_dump(mode="json")

    assert body["outcome"] == "ok"
    assert body["status"]["state"] == "degraded"
    assert body["status"]["available"] is True
    assert body["results"][0]["routing"]["window_id"] == "@10"
    first_hit = body["results"][0]["hits"][0]
    assert "lexical" in first_hit["outcomes"]
    assert "path" in first_hit["match_labels"]
    assert first_hit["source_order"] == 1
    assert first_hit["highlights"]
    assert 0 <= first_hit["score"] <= 1
    assert "raw_score" not in json.dumps(body)


def test_lexical_filters_narrow_backend_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.client import search

    _activate_generation(
        tmp_path,
        monkeypatch,
        [
            _doc(
                text="callback failure in active pinned codex assistant text",
                window_id="@20",
                cwd="/repo/codi",
                runtime="codex",
                session_id="session-codex",
                role="assistant",
                content_type="text",
                status="active",
                pinned=True,
                timestamp="2026-05-22T10:10:00Z",
            ),
            _doc(
                text="callback failure in older claude tool result",
                window_id="@21",
                cwd="/repo/other",
                runtime="claude",
                session_id="session-claude",
                role="user",
                content_type="tool_result",
                status="idle",
                pinned=False,
                timestamp="2026-05-21T10:10:00Z",
            ),
        ],
    )

    body = search(
        SearchRequest(
            query="callback failure",
            runtime="codex",
            cwd="/repo/codi",
            role="assistant",
            content_type="text",
            status="active",
            window_id="@20",
            session_id="session-codex",
            pinned=True,
            recent_after="2026-05-22T00:00:00Z",
        )
    ).model_dump(mode="json")

    assert [result["routing"]["window_id"] for result in body["results"]] == ["@20"]


def test_metadata_only_matches_do_not_create_top_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.client import search

    _activate_generation(
        tmp_path,
        monkeypatch,
        [
            _doc(
                text="plain unrelated transcript content",
                name="billing-prod",
                window_id="@30",
                source_order=1,
            ),
            _doc(
                text="billing-prod transcript evidence and callback failure",
                name="plain",
                window_id="@31",
                source_order=2,
            ),
        ],
    )

    body = search(SearchRequest(query="billing-prod")).model_dump(mode="json")

    assert [result["routing"]["window_id"] for result in body["results"]] == ["@31"]


def test_stale_generation_sources_are_hidden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.client import search
    from codexbot.search.queue import replace_stale_sources

    _activate_generation(
        tmp_path,
        monkeypatch,
        [
            _doc(
                text="open callback failure",
                window_id="@40",
                transcript_source="/tmp/open.jsonl",
            ),
            _doc(
                text="closed callback failure",
                window_id="@41",
                transcript_source="/tmp/closed.jsonl",
            ),
        ],
    )
    replace_stale_sources([("/tmp/closed.jsonl", "codex", "session-1")])

    body = search(SearchRequest(query="callback failure")).model_dump(mode="json")

    assert [result["routing"]["window_id"] for result in body["results"]] == ["@40"]


def test_no_lexical_matches_returns_empty_ok_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.client import search

    _activate_generation(
        tmp_path,
        monkeypatch,
        [_doc(text="only unrelated content", window_id="@50")],
    )

    body = search(SearchRequest(query="absent-symbol")).model_dump(mode="json")

    assert body["outcome"] == "ok"
    assert body["status"]["state"] == "degraded"
    assert body["results"] == []
    assert body["total_results"] == 0
