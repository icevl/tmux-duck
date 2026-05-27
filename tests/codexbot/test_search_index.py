"""Local search index metadata, row conversion, and lazy import tests."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import ModuleType
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

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
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
        self.table.executed_batches.append(rows)
        for row in rows:
            self.table.rows[row[self.key]] = row


class FakeTable:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = {row["row_id"]: row for row in rows or []}
        self.executed_rows: list[dict[str, Any]] = []
        self.executed_batches: list[list[dict[str, Any]]] = []
        self.added_batches: list[list[dict[str, Any]]] = []
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

    def add(self, rows: list[dict[str, Any]]) -> None:
        self.added_batches.append(rows)
        for row in rows:
            self.rows[row["row_id"]] = row


class FakeConnection:
    def __init__(self) -> None:
        self.tables: dict[str, FakeTable] = {}

    def table_names(self) -> list[str]:
        return list(self.tables)

    def open_table(self, name: str) -> FakeTable:
        return self.tables[name]

    def create_table(
        self,
        name: str,
        data: list[dict[str, Any]],
        schema: object | None = None,
    ) -> FakeTable:
        table = FakeTable(data)
        self.tables[name] = table
        return table


def _doc(
    *,
    text: str = "index this callback failure",
    window_id: str = "@1",
    cwd: str = "/repo",
    status: str | None = "active",
    transcript_offset: int = 10,
    transcript_index: int = 1,
) -> SearchBackfillDocument:
    provenance = TranscriptProvenance(
        runtime="codex",
        session_id="session-1",
        transcript_source="/tmp/session-1.jsonl",
        transcript_offset=transcript_offset,
        transcript_index=transcript_index,
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
        source_order=transcript_offset,
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


def test_embedding_config_supports_device_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from codexbot.search.embedding import embedding_config_from_env

    monkeypatch.setenv("CODEXBOT_SEARCH_DEVICE", "0")
    assert embedding_config_from_env().device == "cuda:0"

    monkeypatch.setenv("CODEXBOT_SEARCH_DEVICE", "cuda:1")
    assert embedding_config_from_env().device == "cuda:1"


def test_sentence_transformer_provider_passes_device(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from codexbot.search.embedding import (
        EmbeddingConfig,
        SentenceTransformerEmbeddingProvider,
    )

    module = ModuleType("sentence_transformers")
    seen: dict[str, Any] = {}

    class FakeSentenceTransformer:
        def __init__(self, model_id: str, **kwargs: object) -> None:
            seen["model_id"] = model_id
            seen["kwargs"] = kwargs

        def encode(self, texts: list[str], **kwargs: object) -> list[list[float]]:
            seen["encode"] = kwargs
            return [[1.0, 2.0, 3.0] for _ in texts]

    module.SentenceTransformer = FakeSentenceTransformer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    provider = SentenceTransformerEmbeddingProvider(
        EmbeddingConfig(
            model_id="fake/qwen",
            vector_dimension=3,
            batch_size=4,
            local_files_only=True,
            device="cuda:0",
        )
    )

    assert provider.embed_documents(["a"]) == [[1.0, 2.0, 3.0]]
    assert seen["model_id"] == "fake/qwen"
    assert seen["kwargs"] == {"local_files_only": True, "device": "cuda:0"}
    assert seen["encode"]["batch_size"] == 4


def test_embedding_provider_is_cached_per_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from codexbot.search.embedding import (
        clear_embedding_provider_cache,
        get_embedding_provider,
    )

    module = ModuleType("sentence_transformers")
    constructed: list[str] = []

    class FakeSentenceTransformer:
        def __init__(self, model_id: str, **_kwargs: object) -> None:
            constructed.append(model_id)

        def encode(self, texts: list[str], **_kwargs: object) -> list[list[float]]:
            return [[1.0, 0.0, 0.0] for _ in texts]

    module.SentenceTransformer = FakeSentenceTransformer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    monkeypatch.setenv("CODEXBOT_SEARCH_MODEL_ID", "fake/cached")
    monkeypatch.setenv("CODEXBOT_SEARCH_VECTOR_DIM", "3")
    monkeypatch.setenv("CODEXBOT_SEARCH_BATCH_SIZE", "2")
    clear_embedding_provider_cache()

    first = get_embedding_provider()
    second = get_embedding_provider()

    assert first is second
    assert first.embed_query("one") == [1.0, 0.0, 0.0]
    assert second.embed_query("two") == [1.0, 0.0, 0.0]
    assert constructed == ["fake/cached"]
    clear_embedding_provider_cache()


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
    assert json.loads(row["identity"]) == doc.identity.model_dump(mode="json")


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


def test_materialize_generation_index_batches_documents_and_reports_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.search.index import materialize_generation_index
    from codexbot.search.state import read_index_metadata

    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    connection = FakeConnection()
    embedder = FakeEmbedder()
    progress: list[int] = []
    documents = [
        _doc(
            text=f"document {index}",
            transcript_offset=index,
            transcript_index=index,
        )
        for index in range(5)
    ]

    metadata = materialize_generation_index(
        "gen-batch",
        documents=documents,
        provider=embedder,
        connection=connection,
        batch_size=2,
        progress_callback=progress.append,
    )

    table = connection.tables["chunks"]
    assert [len(call) for call in embedder.calls] == [2, 2, 1]
    assert [len(batch) for batch in table.executed_batches] == [2, 1]
    assert table.added_batches == []
    assert progress == [2, 4, 5]
    assert len(table.rows) == 5
    assert table.fts_created is True
    assert table.scalar_created is True
    assert metadata.completed is True
    assert read_index_metadata("gen-batch") == metadata
