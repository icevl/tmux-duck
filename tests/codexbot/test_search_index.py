"""Local search index metadata, row conversion, and lazy import tests."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

import pytest

from codexbot.search.contracts import (
    SearchBackfillDocument,
    SearchIndexMetadata,
    SearchRoutingMetadata,
    SearchRowIdentity,
    TranscriptProvenance,
)


class FakeEmbedder:
    model_id = "fake/qwen"
    vector_dimension = 1024

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [
            [float(index + 1)] * self.vector_dimension for index, _ in enumerate(texts)
        ]

    def embed_query(self, text: str) -> list[float]:
        return [0.5] * self.vector_dimension


class FakeMerge:
    def __init__(self, table: "FakeTable", key: str) -> None:
        self.table = table
        self.key = key

    def when_matched_update_all(self) -> "FakeMerge":
        self.table.matched = True
        return self

    def when_not_matched_insert_all(self) -> "FakeMerge":
        self.table.inserted = True
        return self

    def execute(self, rows: list[dict[str, Any]]) -> None:
        self.table.executed_rows = rows
        for row in rows:
            self.table.rows[row[self.key]] = row


class FakeTable:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = {row["row_id"]: row for row in rows or []}
        self.executed_rows: list[dict[str, Any]] = []
        self.merge_key: str | None = None
        self.fts_created = False
        self.scalar_created = False
        self.matched = False
        self.inserted = False

    def merge_insert(self, key: str) -> FakeMerge:
        self.merge_key = key
        return FakeMerge(self, key)

    def create_fts_index(self, _field: str, **_kwargs: object) -> None:
        self.fts_created = True

    def create_scalar_index(self, _field: str) -> None:
        self.scalar_created = True


class FakeConnection:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}

    def table_names(self) -> list[str]:
        return list(self.tables)

    def open_table(self, name: str) -> FakeTable:
        return self.tables[name]

    def create_table(self, name: str, data: list[dict[str, Any]]) -> FakeTable:
        table = FakeTable(data)
        self.tables[name] = table
        return table


def _doc(
    *,
    text: str = "index this callback failure",
    window_id: str = "@1",
    cwd: str = "/repo",
    status: str | None = "active",
) -> SearchBackfillDocument:
    provenance = TranscriptProvenance(
        runtime="codex",
        session_id="session-1",
        transcript_source="/tmp/session-1.jsonl",
        transcript_offset=10,
        transcript_index=1,
        role="assistant",
        content_type="text",
        tool_name=None,
        tool_use_id=None,
        source_event_kind="parsed_entry",
        timestamp="2026-05-22T10:00:00Z",
    )
    return SearchBackfillDocument(
        identity=SearchRowIdentity.from_provenance(provenance, chunk_index=0),
        provenance=provenance,
        routing=SearchRoutingMetadata(
            window_id=window_id,
            name="codex",
            cwd=cwd,
            runtime="codex",
            session_id="session-1",
            status=status,
            pinned=True,
            sort_order=1,
        ),
        text=text,
        timestamp=provenance.timestamp,
        source_order=10,
        chunk_index=0,
        chunk_count=1,
    )


def test_index_paths_are_generation_owned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.state import (
        generation_index_metadata_path,
        generation_lancedb_dir,
    )

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))

    assert generation_lancedb_dir("gen-a") == (
        tmp_path / "search" / "generations" / "gen-a" / "lancedb"
    )
    assert generation_index_metadata_path("gen-a") == (
        tmp_path / "search" / "generations" / "gen-a" / "index.json"
    )


def test_index_metadata_records_model_without_transcript_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.state import read_index_metadata, write_index_metadata

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    metadata = SearchIndexMetadata(
        schema_version=1,
        generation_id="gen-a",
        model_id="Qwen/Qwen3-Embedding-0.6B",
        vector_dimension=1024,
        table_name="chunks",
        created_at="2026-05-22T10:00:00Z",
        completed=True,
    )

    write_index_metadata(metadata)

    dumped = read_index_metadata("gen-a").model_dump()  # type: ignore[union-attr]
    assert dumped["model_id"] == "Qwen/Qwen3-Embedding-0.6B"
    assert dumped["vector_dimension"] == 1024
    assert "index this callback failure" not in str(dumped)
    assert "text" not in dumped


def test_embedding_index_and_worker_imports_are_lazy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    heavy = {"lancedb", "sentence_transformers", "torch", "transformers"}
    for name in list(sys.modules):
        if name.split(".", 1)[0] in heavy:
            monkeypatch.delitem(sys.modules, name, raising=False)

    importlib.import_module("codexbot.search.embedding")
    importlib.import_module("codexbot.search.index")
    importlib.import_module("codexbot.search.worker")

    assert not (heavy & {name.split(".", 1)[0] for name in sys.modules})


def test_rows_for_documents_uses_fake_embedder_and_stable_identity() -> None:
    from codexbot.search.index import row_id_for_identity, rows_for_documents

    doc = _doc()
    rows, embedder = rows_for_documents([doc], provider=FakeEmbedder())

    assert embedder.model_id == "fake/qwen"
    assert len(rows) == 1
    row = rows[0]
    assert row["row_id"] == row_id_for_identity(doc.identity)
    assert row["text"] == doc.text
    assert row["vector"] == [1.0] * 1024
    assert row["runtime"] == "codex"
    assert row["window_id"] == "@1"
    assert row["cwd"] == "/repo"
    assert row["pinned"] is True
    assert row["identity"] == doc.identity.model_dump(mode="json")


def test_materialize_generation_index_upserts_by_row_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.index import materialize_generation_index, row_id_for_identity
    from codexbot.search.state import read_index_metadata

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    connection = FakeConnection()
    first = _doc(cwd="/repo/old")
    second = first.model_copy(
        update={
            "routing": first.routing.model_copy(update={"cwd": "/repo/new"}),
        }
    )

    materialize_generation_index(
        "gen-a",
        documents=[first],
        provider=FakeEmbedder(),
        connection=connection,
    )
    metadata = materialize_generation_index(
        "gen-a",
        documents=[second],
        provider=FakeEmbedder(),
        connection=connection,
    )

    table = connection.tables["chunks"]
    row_id = row_id_for_identity(first.identity)
    assert table.merge_key == "row_id"
    assert table.matched is True
    assert table.inserted is True
    assert table.fts_created is True
    assert table.scalar_created is True
    assert list(table.rows) == [row_id]
    assert table.rows[row_id]["cwd"] == "/repo/new"
    assert metadata.completed is True
    assert read_index_metadata("gen-a") == metadata
