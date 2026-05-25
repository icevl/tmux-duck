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


def _write_ready_index(
    monkeypatch: pytest.MonkeyPatch,
    generation_id: str = "gen-retrieval",
) -> None:
    from codexbot.search.contracts import SearchIndexMetadata
    from codexbot.search.state import write_index_metadata

    write_index_metadata(
        SearchIndexMetadata(
            schema_version=1,
            generation_id=generation_id,
            model_id="fake/qwen",
            vector_dimension=1024,
            table_name="chunks",
            created_at="2026-05-22T10:00:00Z",
            completed=True,
        )
    )


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


def test_semantic_paraphrase_can_retrieve_without_lexical_overlap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.client import search
    from codexbot.search.index import row_id_for_identity

    target = _doc(
        text="persistent shell survives attach mode and browser tab reload",
        window_id="@60",
    )
    distractor = _doc(text="unrelated billing callback issue", window_id="@61")
    _activate_generation(tmp_path, monkeypatch, [target, distractor])
    _write_ready_index(monkeypatch)
    target_row_id = row_id_for_identity(target.identity)

    monkeypatch.setattr(
        "codexbot.search.retrieval.semantic_scores_for_query",
        lambda *_args, **_kwargs: {target_row_id: 0.96},
    )

    body = search(SearchRequest(query="keep console alive")).model_dump(mode="json")

    assert body["status"]["state"] == "ready"
    assert body["results"][0]["routing"]["window_id"] == "@60"
    hit = body["results"][0]["hits"][0]
    assert "semantic" in hit["outcomes"]
    assert "semantic" in hit["match_labels"]


def test_hybrid_hit_label_when_lexical_and_semantic_match(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.client import search
    from codexbot.search.index import row_id_for_identity

    target = _doc(
        text="inspect src/codexbot/web/api.py for search route validation",
        window_id="@70",
    )
    _activate_generation(tmp_path, monkeypatch, [target])
    _write_ready_index(monkeypatch)

    monkeypatch.setattr(
        "codexbot.search.retrieval.semantic_scores_for_query",
        lambda *_args, **_kwargs: {row_id_for_identity(target.identity): 0.91},
    )

    body = search(SearchRequest(query="src/codexbot/web/api.py")).model_dump(
        mode="json"
    )

    hit = body["results"][0]["hits"][0]
    assert body["status"]["state"] == "ready"
    assert "hybrid" in hit["outcomes"]
    assert "hybrid" in hit["match_labels"]


def test_semantic_exception_returns_sanitized_lexical_degraded_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.client import search

    target = _doc(
        text="callback failure handled by lexical fallback",
        window_id="@80",
    )
    _activate_generation(tmp_path, monkeypatch, [target])
    _write_ready_index(monkeypatch)

    def fail_semantic(*_args: object, **_kwargs: object) -> dict[str, float]:
        raise RuntimeError("WEB_UI_PASSWORD=secret /tmp/private/session.jsonl")

    monkeypatch.setattr(
        "codexbot.search.retrieval.semantic_scores_for_query",
        fail_semantic,
    )

    body = search(SearchRequest(query="callback failure")).model_dump(mode="json")
    serialized = json.dumps(body)

    assert body["status"]["state"] == "degraded"
    assert body["status"]["available"] is True
    assert body["results"][0]["routing"]["window_id"] == "@80"
    assert "lexical" in body["results"][0]["hits"][0]["outcomes"]
    assert "semantic retrieval degraded" in (body["status"]["reason"] or "")
    assert body["status"]["operations"] is not None
    assert "WEB_UI_PASSWORD" not in serialized
    assert "secret" not in serialized
    assert "/tmp/private" not in serialized


def test_semantic_failure_returns_safe_lexical_degraded_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.client import search

    _activate_generation(
        tmp_path,
        monkeypatch,
        [_doc(text="callback failure in worker output", window_id="@80")],
    )
    _write_ready_index(monkeypatch)

    def fail_semantic(*_args: object, **_kwargs: object) -> dict[str, float]:
        raise RuntimeError("WEB_UI_PASSWORD=secret /tmp/private/session.jsonl")

    monkeypatch.setattr(
        "codexbot.search.retrieval.semantic_scores_for_query",
        fail_semantic,
    )

    body = search(SearchRequest(query="callback failure")).model_dump(mode="json")
    serialized = json.dumps(body)

    assert body["status"]["state"] == "degraded"
    assert body["status"]["available"] is True
    assert body["results"][0]["routing"]["window_id"] == "@80"
    assert "WEB_UI_PASSWORD" not in serialized
    assert "secret" not in serialized
    assert "/tmp/private" not in serialized


def test_ready_index_no_matches_differs_from_missing_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.client import get_status, search

    _activate_generation(
        tmp_path,
        monkeypatch,
        [_doc(text="unrelated session output", window_id="@90")],
    )
    _write_ready_index(monkeypatch)
    monkeypatch.setattr(
        "codexbot.search.retrieval.semantic_scores_for_query",
        lambda *_args, **_kwargs: {},
    )

    status = get_status().model_dump(mode="json")
    body = search(SearchRequest(query="missing query")).model_dump(mode="json")

    assert status["state"] == "ready"
    assert status["available"] is True
    assert body["outcome"] == "ok"
    assert body["results"] == []
