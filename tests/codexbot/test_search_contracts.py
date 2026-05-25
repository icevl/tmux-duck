"""Search contract tests for provenance, identity, request bounds, and imports."""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_INDEX_STATES = {
    "missing",
    "building",
    "partial",
    "ready",
    "stale",
    "degraded",
    "unavailable",
}
HEAVY_IMPORT_ROOTS = {
    "fastembed",
    "lancedb",
    "sentence_transformers",
    "torch",
    "transformers",
}
SEARCH_IMPLEMENTATION_MODULES = {
    "index",
    "queue",
    "ranking",
    "retrieval",
    "worker",
}


def _sample_provenance(**overrides: Any):
    from codexbot.search.contracts import TranscriptProvenance

    values = {
        "runtime": "codex",
        "session_id": "session-123",
        "transcript_source": "~/.codex/sessions/session-123.jsonl",
        "transcript_offset": 4096,
        "transcript_index": 2,
        "role": "assistant",
        "content_type": "tool_result",
        "tool_name": "Bash",
        "tool_use_id": "toolu_123",
        "source_event_kind": "jsonl_entry",
    }
    values.update(overrides)
    return TranscriptProvenance(**values)


def test_provenance_contract_contains_required_fields() -> None:
    """CORP-03, D-01, D-02, and D-04: provenance is runtime-neutral."""
    provenance = _sample_provenance()

    assert provenance.runtime == "codex"
    assert provenance.session_id == "session-123"
    assert provenance.transcript_source.endswith("session-123.jsonl")
    assert provenance.transcript_offset == 4096
    assert provenance.transcript_index == 2
    assert provenance.role == "assistant"
    assert provenance.content_type == "tool_result"
    assert provenance.tool_name == "Bash"
    assert provenance.tool_use_id == "toolu_123"
    assert provenance.source_event_kind == "jsonl_entry"

    without_optional_session = _sample_provenance(session_id=None)
    assert without_optional_session.session_id is None


def test_row_identity_excludes_mutable_window_metadata() -> None:
    """CORP-04 and D-03: row identity is stable when routing metadata changes."""
    from codexbot.search.contracts import SearchRoutingMetadata, SearchRowIdentity

    provenance = _sample_provenance()
    identity = SearchRowIdentity.from_provenance(provenance, chunk_index=0)
    varied_identity = SearchRowIdentity.from_provenance(provenance, chunk_index=0)

    first_route = SearchRoutingMetadata(
        window_id="@12",
        name="billing-prod",
        cwd="/repo/a",
        runtime="codex",
        session_id="session-123",
        status="active",
        pinned=True,
        sort_order=1,
    )
    second_route = SearchRoutingMetadata(
        window_id="@98",
        name="renamed-session",
        cwd="/repo/b",
        runtime="codex",
        session_id="session-123",
        status="idle",
        pinned=False,
        sort_order=99,
    )

    assert first_route != second_route
    assert identity == varied_identity
    assert identity.model_dump() == varied_identity.model_dump()
    assert set(identity.model_dump()).isdisjoint(
        {"window_id", "name", "cwd", "status", "pinned", "sort_order"}
    )


def test_row_identity_supports_multiple_chunks_for_one_transcript_message() -> None:
    """D-01: one transcript message can map to multiple chunk-level rows."""
    from codexbot.search.contracts import SearchRowIdentity

    provenance = _sample_provenance()

    first_chunk = SearchRowIdentity.from_provenance(provenance, chunk_index=0)
    second_chunk = SearchRowIdentity.from_provenance(provenance, chunk_index=1)

    assert first_chunk != second_chunk
    assert first_chunk.chunk_index == 0
    assert second_chunk.chunk_index == 1


def test_search_request_bounds_reject_oversized_inputs() -> None:
    """T-01-02: request DTO bounds query text, total hits, and per-session hits."""
    from codexbot.search.contracts import SearchRequest

    with pytest.raises(ValueError):
        SearchRequest(query="x" * 501, limit=10, hits_per_session=3)

    with pytest.raises(ValueError):
        SearchRequest(query="find stack trace", limit=0, hits_per_session=3)

    with pytest.raises(ValueError):
        SearchRequest(query="find stack trace", limit=51, hits_per_session=3)

    with pytest.raises(ValueError):
        SearchRequest(query="find stack trace", limit=10, hits_per_session=0)

    with pytest.raises(ValueError):
        SearchRequest(query="find stack trace", limit=10, hits_per_session=11)

    with pytest.raises(ValueError):
        SearchRequest(query="find stack trace", recent_seconds=0)


def test_phase4_search_request_exposes_backend_filters() -> None:
    """D-07: Phase 4 backend filters are part of the request contract."""
    from codexbot.search.contracts import SearchRequest

    req = SearchRequest(
        query="callback failure",
        window_id="@12",
        session_id="session-12",
        runtime="codex",
        cwd="/repo/codi",
        role="assistant",
        content_type="text",
        status="active",
        pinned=True,
        recent_after="2026-05-22T10:00:00Z",
        recent_seconds=600,
    )

    assert req.window_id == "@12"
    assert req.session_id == "session-12"
    assert req.pinned is True
    assert req.recent_after == "2026-05-22T10:00:00Z"
    assert req.recent_seconds == 600


def test_lifecycle_vocabulary_matches_phase_contract() -> None:
    """D-06: lifecycle states are exactly the approved search vocabulary."""
    from codexbot.search.contracts import SEARCH_INDEX_STATES

    assert set(SEARCH_INDEX_STATES) == EXPECTED_INDEX_STATES
    assert len(SEARCH_INDEX_STATES) == len(EXPECTED_INDEX_STATES)


def test_status_response_supports_typed_not_ready_state() -> None:
    """D-05: not-yet-indexed search is represented as a typed response."""
    from codexbot.search.contracts import SearchStatusResponse

    status = SearchStatusResponse(
        state="missing",
        available=False,
        scope="open_sessions",
        reason="search index has not been built",
        counters=None,
        generation=None,
    )

    assert status.state == "missing"
    assert status.available is False
    assert status.scope == "open_sessions"
    assert "index" in (status.reason or "")
    assert status.counters is None
    assert status.generation is None
    assert status.index is None


def test_status_response_exposes_operations_without_raw_content() -> None:
    """OPS-03/OPS-06: status carries compact health details and commands."""
    from codexbot.search.contracts import (
        SearchBackfillProgress,
        SearchOperationalStatus,
        SearchQueueHealth,
        SearchRecoveryCommand,
        SearchStatusResponse,
        SearchWorkerHealth,
    )

    status = SearchStatusResponse(
        state="degraded",
        available=True,
        reason="search queue has 1 failed item(s)",
        operations=SearchOperationalStatus(
            worker=SearchWorkerHealth(
                status="running",
                current_task="live_loop",
                heartbeat_at="2026-05-25T10:00:00Z",
                heartbeat_age_seconds=12.5,
                stale=False,
                stale_after_seconds=120,
            ),
            queue=SearchQueueHealth(
                queued_items=2,
                leased_items=1,
                failed_items=1,
                stale_sources=0,
                lagging=True,
                recent_error="[path] failed",
            ),
            progress=SearchBackfillProgress(
                open_sessions=4,
                indexed_sessions=3,
                indexed_chunks=42,
                queued_items=3,
                failed_items=1,
                generation_id="gen-live",
                model_id="Qwen/Qwen3-Embedding-0.6B",
                vector_dimension=1024,
                table_name="chunks",
            ),
            recent_errors=["[path] failed"],
            recovery_commands=[
                SearchRecoveryCommand(
                    label="Rebuild index",
                    command="codexbot-search-worker rebuild",
                )
            ],
        ),
    )

    dumped = status.model_dump(mode="json")

    assert dumped["operations"]["worker"]["status"] == "running"
    assert dumped["operations"]["queue"]["lagging"] is True
    assert dumped["operations"]["progress"]["indexed_chunks"] == 42
    assert dumped["operations"]["recent_errors"] == ["[path] failed"]
    assert "raw transcript" not in json.dumps(dumped)


def test_search_hit_exposes_highlights_and_rejects_invalid_spans() -> None:
    """D-06/D-08: hits expose normalized scores and exact spans only."""
    from codexbot.search.contracts import (
        SearchHighlight,
        SearchHit,
        SearchRowIdentity,
    )

    provenance = _sample_provenance()
    identity = SearchRowIdentity.from_provenance(provenance, chunk_index=0)
    hit = SearchHit(
        identity=identity,
        provenance=provenance,
        snippet="open src/codexbot/web/api.py and inspect the stack trace",
        score=0.82,
        outcomes=["lexical"],
        source_order=17,
        timestamp="2026-05-22T10:00:00Z",
        highlights=[SearchHighlight(start=5, end=31, label="path")],
        match_labels=["path", "lexical"],
    )

    dumped = hit.model_dump()
    assert dumped["score"] == 0.82
    assert dumped["source_order"] == 17
    assert dumped["highlights"] == [{"start": 5, "end": 31, "label": "path"}]
    assert "raw_score" not in dumped
    assert "backend_score" not in dumped

    with pytest.raises(ValueError):
        SearchHighlight(start=10, end=10, label="exact")

    with pytest.raises(ValueError):
        SearchHit(
            identity=identity,
            provenance=provenance,
            snippet="short",
            score=0.5,
            outcomes=["lexical"],
            source_order=1,
            highlights=[SearchHighlight(start=0, end=8, label="exact")],
        )


def test_generation_metadata_carries_rebuildable_identity() -> None:
    """D-11: index generations expose rebuild metadata without transcript text."""
    from codexbot.search.contracts import SearchGenerationMetadata

    generation = SearchGenerationMetadata(
        schema_version=1,
        generation_id="gen-20260521",
        created_at="2026-05-21T13:00:00Z",
        active=True,
    )

    dumped = generation.model_dump()
    assert dumped == {
        "schema_version": 1,
        "generation_id": "gen-20260521",
        "created_at": "2026-05-21T13:00:00Z",
        "active": True,
    }
    assert "text" not in dumped
    assert "content" not in dumped


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
            continue
        if isinstance(node, ast.ImportFrom):
            modules.update(_resolve_import_from(path, node))

    return modules


def _resolve_import_from(path: Path, node: ast.ImportFrom) -> set[str]:
    module = node.module or ""
    if node.level == 0:
        base = module
    else:
        try:
            relative = path.resolve().relative_to(ROOT / "src")
        except ValueError:
            return {module} if module else set()

        package_parts = list(relative.with_suffix("").parts[:-1])
        trim = max(node.level - 1, 0)
        if trim:
            package_parts = package_parts[:-trim]
        if module:
            package_parts.extend(module.split("."))
        base = ".".join(package_parts)

    modules = {base} if base else set()
    if base == "codexbot.search":
        modules.update(
            f"{base}.{alias.name}" for alias in node.names if alias.name != "*"
        )
    return modules


def test_relative_import_resolver_catches_web_search_submodules() -> None:
    """T-01-05: Web API relative imports resolve to full search submodules."""
    api_path = ROOT / "src" / "codexbot" / "web" / "api.py"
    tree = ast.parse(
        "from ..search import client as search_client, retrieval\n",
        filename=str(api_path),
    )
    [node] = [n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]

    assert _resolve_import_from(api_path, node) == {
        "codexbot.search",
        "codexbot.search.client",
        "codexbot.search.retrieval",
    }


def test_web_search_boundary_has_no_heavy_imports() -> None:
    """D-08 and T-01-05: request-path search imports stay lightweight."""
    search_dir = ROOT / "src" / "codexbot" / "search"
    paths = [ROOT / "src" / "codexbot" / "web" / "api.py"]
    if search_dir.exists():
        paths.extend(
            search_dir / name
            for name in ("__init__.py", "contracts.py", "state.py", "client.py")
            if (search_dir / name).exists()
        )

    violations: list[str] = []
    for path in paths:
        for module in _imported_modules(path):
            root = module.split(".", 1)[0]
            if root in HEAVY_IMPORT_ROOTS:
                violations.append(f"{path.relative_to(ROOT)} imports {module}")
            if path.name == "api.py" and module.startswith("codexbot.search."):
                leaf = module.rsplit(".", 1)[-1]
                if leaf in SEARCH_IMPLEMENTATION_MODULES:
                    violations.append(f"{path.relative_to(ROOT)} imports {module}")

    assert not violations


def test_web_api_does_not_import_search_queue_directly() -> None:
    """D-15: Web API status stays behind the lightweight search client boundary."""
    api_path = ROOT / "src" / "codexbot" / "web" / "api.py"

    assert "codexbot.search.queue" not in _imported_modules(api_path)
