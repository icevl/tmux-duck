"""Parser-backed open-session search backfill tests."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from codexbot.session import CodexSession, SessionManager, WindowState
from codexbot.tmux_manager import TmuxWindow
from codexbot.transcript_parser import ParsedEntry, TranscriptParser


@dataclass
class FakeTmuxManager:
    windows: list[TmuxWindow]

    async def list_windows(self) -> list[TmuxWindow]:
        return list(self.windows)


@pytest.fixture
def mgr(monkeypatch: pytest.MonkeyPatch) -> SessionManager:
    monkeypatch.setattr(SessionManager, "_load_state", lambda self: None)
    monkeypatch.setattr(SessionManager, "_save_state", lambda self: None)
    return SessionManager()


def _write_jsonl(path: Path, *entries: dict) -> None:
    path.write_text(
        "".join(json.dumps(entry, ensure_ascii=False) + "\n" for entry in entries),
        encoding="utf-8",
    )


def _assistant_entry(*content: dict, timestamp: str = "2026-05-21T10:00:00Z") -> dict:
    return {
        "type": "assistant",
        "timestamp": timestamp,
        "message": {"content": list(content)},
        "sessionId": "session-1",
        "cwd": "/repo",
    }


def _user_entry(*content: dict | str, timestamp: str = "2026-05-21T10:00:01Z") -> dict:
    return {
        "type": "user",
        "timestamp": timestamp,
        "message": {"content": list(content)},
        "sessionId": "session-1",
        "cwd": "/repo",
    }


def _text(text: str) -> dict:
    return {"type": "text", "text": text}


def _thinking(text: str) -> dict:
    return {"type": "thinking", "thinking": text}


def _tool_use(tool_id: str, name: str, input_data: dict) -> dict:
    return {"type": "tool_use", "id": tool_id, "name": name, "input": input_data}


def _tool_result(tool_id: str, content: list[dict] | str) -> dict:
    return {"type": "tool_result", "tool_use_id": tool_id, "content": content}


def _image_block() -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": "image/png",
            "data": "iVBORw0KGgo=",
        },
    }


@pytest.mark.asyncio
async def test_session_helper_returns_parser_backed_transcript_entries(
    mgr: SessionManager, tmp_path: Path
) -> None:
    transcript = tmp_path / "codex.jsonl"
    _write_jsonl(
        transcript,
        _assistant_entry(
            _text("assistant text"),
            _tool_use("tool-1", "Bash", {"command": "pwd"}),
        ),
        _user_entry(_tool_result("tool-1", [{"type": "text", "text": "/repo"}])),
    )
    session = CodexSession("session-1", "", 2, str(transcript))
    mgr.window_states["@1"] = WindowState(
        session_id="session-1",
        cwd="/repo",
        window_name="codex",
        runtime="codex",
    )

    with (
        patch.object(
            mgr,
            "resolve_session_for_window",
            new=AsyncMock(return_value=session),
        ),
        patch(
            "codexbot.session.TranscriptParser.parse_entries",
            wraps=TranscriptParser.parse_entries,
        ) as parse_entries,
    ):
        parsed = await mgr.read_parsed_transcript_for_window("@1")

    assert parsed is not None
    assert parsed.session == session
    assert parsed.runtime == "codex"
    assert parsed.transcript_source == str(transcript)
    assert [entry.content_type for entry in parsed.entries] == [
        "text",
        "tool_use",
        "tool_result",
    ]
    assert parsed.entries[0].transcript_offset == 0
    assert parsed.entries[0].transcript_index == 0
    assert parse_entries.call_count == 1


@pytest.mark.asyncio
async def test_backfill_enumerates_current_windows_and_skips_unresolved(
    mgr: SessionManager, tmp_path: Path
) -> None:
    from codexbot.search.backfill import collect_open_session_documents

    codex_transcript = tmp_path / "codex.jsonl"
    claude_transcript = tmp_path / "claude.jsonl"
    _write_jsonl(codex_transcript, _user_entry(_text("codex prompt")))
    _write_jsonl(claude_transcript, _assistant_entry(_text("claude answer")))
    sessions = {
        "@1": CodexSession("codex-session", "", 1, str(codex_transcript)),
        "@2": CodexSession("claude-session", "", 1, str(claude_transcript)),
    }
    mgr.window_states.update(
        {
            "@1": WindowState(
                session_id="codex-session",
                cwd="/repo/codex",
                window_name="codex",
                runtime="codex",
            ),
            "@2": WindowState(
                session_id="claude-session",
                cwd="/repo/claude",
                window_name="claude",
                runtime="claude",
                pinned=True,
                sort_order=1,
            ),
            "@stale": WindowState(
                session_id="stale-session",
                cwd="/repo/stale",
                window_name="stale",
                runtime="codex",
            ),
        }
    )
    tmux = FakeTmuxManager(
        [
            TmuxWindow("@1", "codex", "/repo/codex", "codex"),
            TmuxWindow("@2", "claude", "/repo/claude", "claude"),
            TmuxWindow("@3", "untracked", "/repo/untracked", "codex"),
        ]
    )

    async def resolve(window_id: str) -> CodexSession | None:
        return sessions.get(window_id)

    with patch.object(
        mgr, "resolve_session_for_window", new=AsyncMock(side_effect=resolve)
    ):
        result = await collect_open_session_documents(
            session_manager=mgr,
            tmux_manager=tmux,
        )

    assert result.counters.open_sessions == 3
    assert result.counters.indexed_sessions == 2
    assert result.counters.failed_items == 1
    assert {doc.routing.window_id for doc in result.documents} == {"@1", "@2"}
    assert {doc.routing.runtime for doc in result.documents} == {"codex", "claude"}
    assert all(
        doc.provenance.transcript_source
        in {str(codex_transcript), str(claude_transcript)}
        for doc in result.documents
    )


@pytest.mark.asyncio
async def test_backfill_indexes_all_text_bearing_parser_entry_types(
    mgr: SessionManager, tmp_path: Path
) -> None:
    from codexbot.search.backfill import collect_open_session_documents

    transcript = tmp_path / "session.jsonl"
    _write_jsonl(
        transcript,
        _assistant_entry(
            _text("assistant text"),
            _thinking("chain of thought surrogate"),
            _tool_use("tool-1", "Bash", {"command": "pwd"}),
        ),
        _user_entry(_tool_result("tool-1", [{"type": "text", "text": "/repo"}])),
        _user_entry(
            _text(
                "<command-name>pwd</command-name>"
                "<local-command-stdout>/repo\n</local-command-stdout>"
            ),
        ),
        _user_entry(_text("user prompt")),
        _user_entry(_tool_result("image-only", [_image_block()])),
    )
    session = CodexSession("session-1", "", 5, str(transcript))
    mgr.window_states["@1"] = WindowState(
        session_id="session-1",
        cwd="/repo",
        window_name="codex",
        runtime="codex",
    )
    tmux = FakeTmuxManager([TmuxWindow("@1", "codex", "/repo", "codex")])

    with patch.object(
        mgr,
        "resolve_session_for_window",
        new=AsyncMock(return_value=session),
    ):
        result = await collect_open_session_documents(
            session_manager=mgr,
            tmux_manager=tmux,
        )

    content_types = [doc.provenance.content_type for doc in result.documents]
    assert content_types == [
        "text",
        "thinking",
        "tool_use",
        "tool_result",
        "local_command",
        "text",
    ]
    assert all(doc.text.strip() for doc in result.documents)
    assert not any(
        doc.provenance.tool_use_id == "image-only" for doc in result.documents
    )
    tool_use = next(
        doc for doc in result.documents if doc.provenance.content_type == "tool_use"
    )
    assert tool_use.provenance.tool_name == "Bash"
    assert tool_use.provenance.tool_use_id == "tool-1"
    assert tool_use.provenance.runtime == "codex"
    assert tool_use.provenance.session_id == "session-1"
    assert tool_use.provenance.transcript_offset == 0
    assert tool_use.provenance.transcript_index == 2
    assert tool_use.routing.window_id == "@1"
    assert tool_use.routing.cwd == "/repo"
    assert tool_use.routing.name == "codex"


@pytest.mark.asyncio
async def test_long_entries_split_into_stable_chunk_identities(
    mgr: SessionManager, tmp_path: Path
) -> None:
    from codexbot.search.backfill import collect_open_session_documents

    transcript = tmp_path / "session.jsonl"
    _write_jsonl(transcript, _assistant_entry(_text("alpha beta gamma delta epsilon")))
    session = CodexSession("session-1", "", 1, str(transcript))
    mgr.window_states["@1"] = WindowState(
        session_id="session-1",
        cwd="/repo",
        window_name="codex",
        runtime="codex",
    )
    tmux = FakeTmuxManager([TmuxWindow("@1", "codex", "/repo", "codex")])

    with patch.object(
        mgr,
        "resolve_session_for_window",
        new=AsyncMock(return_value=session),
    ):
        result = await collect_open_session_documents(
            session_manager=mgr,
            tmux_manager=tmux,
            chunk_max_chars=10,
            chunk_overlap_chars=0,
        )

    assert [doc.chunk_index for doc in result.documents] == [0, 1, 2]
    assert all(doc.chunk_count == 3 for doc in result.documents)
    identities = [doc.identity.model_dump_json() for doc in result.documents]
    assert len(set(identities)) == 3
    assert [doc.identity.chunk_index for doc in result.documents] == [0, 1, 2]


def test_public_document_builder_matches_backfill_chunking() -> None:
    from codexbot.search.backfill import documents_for_entry, routing_for_source
    from codexbot.session import ParsedTranscriptSession

    session = CodexSession("session-1", "", 1, "/tmp/session.jsonl")
    state = WindowState(
        session_id="session-1",
        cwd="/repo",
        window_name="codex",
        runtime="codex",
    )
    source = ParsedTranscriptSession(
        window_id="@1",
        session=session,
        state=state,
        transcript_source="/tmp/session.jsonl",
        entries=[],
        pending_tools={},
    )
    routing = routing_for_source(source, TmuxWindow("@1", "codex", "/repo", "codex"))
    assert routing is not None

    docs = documents_for_entry(
        source=source,
        routing=routing,
        entry=ParsedEntry(
            role="assistant",
            text="alpha beta gamma delta epsilon",
            content_type="text",
            timestamp="2026-05-22T10:00:00Z",
            transcript_offset=42,
            transcript_index=3,
        ),
        fallback_order=0,
        chunk_max_chars=10,
        chunk_overlap_chars=0,
    )

    assert [doc.text for doc in docs] == ["alpha beta", "gamma del", "ta epsilon"]
    assert [doc.chunk_index for doc in docs] == [0, 1, 2]
    assert all(doc.identity.transcript_offset == 42 for doc in docs)
    assert all(doc.provenance.transcript_source == "/tmp/session.jsonl" for doc in docs)


@pytest.mark.asyncio
async def test_materialize_inactive_generation_writes_search_owned_artifacts(
    mgr: SessionManager, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.backfill import materialize_backfill_generation
    from codexbot.search.state import (
        active_generation_metadata_path,
        generation_documents_path,
        generation_manifest_path,
    )

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    transcript = tmp_path / "session.jsonl"
    _write_jsonl(transcript, _user_entry(_text("index me")))
    session = CodexSession("session-1", "", 1, str(transcript))
    mgr.window_states["@1"] = WindowState(
        session_id="session-1",
        cwd="/repo",
        window_name="codex",
        runtime="codex",
    )
    tmux = FakeTmuxManager([TmuxWindow("@1", "codex", "/repo", "codex")])

    with patch.object(
        mgr,
        "resolve_session_for_window",
        new=AsyncMock(return_value=session),
    ):
        manifest = await materialize_backfill_generation(
            "generation-test",
            session_manager=mgr,
            tmux_manager=tmux,
        )

    docs_path = generation_documents_path("generation-test")
    manifest_path = generation_manifest_path("generation-test")
    assert manifest.generation.generation_id == "generation-test"
    assert manifest.generation.active is False
    assert manifest.counters.open_sessions == 1
    assert manifest.counters.indexed_chunks == 1
    assert (
        docs_path
        == tmp_path / "search" / "generations" / "generation-test" / "documents.jsonl"
    )
    assert (
        manifest_path
        == tmp_path / "search" / "generations" / "generation-test" / "manifest.json"
    )
    assert docs_path.exists()
    assert manifest_path.exists()
    assert not active_generation_metadata_path().exists()
    assert (
        json.loads(docs_path.read_text(encoding="utf-8").splitlines()[0])["text"]
        == "index me"
    )
