"""Generation-owned local LanceDB index service."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from .contracts import SearchBackfillDocument, SearchIndexMetadata, SearchRowIdentity
from .embedding import EmbeddingProvider, get_embedding_provider
from .live import read_generation_documents
from .state import (
    SEARCH_SCHEMA_VERSION,
    generation_lancedb_dir,
    read_index_metadata,
    write_index_metadata,
)

DEFAULT_TABLE_NAME = "chunks"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def row_id_for_identity(identity: SearchRowIdentity) -> str:
    """Return a stable row id derived only from immutable transcript identity."""
    raw = json.dumps(
        identity.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "r_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def row_for_document(
    document: SearchBackfillDocument,
    vector: Sequence[float],
) -> dict[str, Any]:
    """Flatten one backfill document into a LanceDB-ready row."""
    routing = document.routing
    provenance = document.provenance
    return {
        "row_id": row_id_for_identity(document.identity),
        "text": document.text,
        "vector": [float(value) for value in vector],
        "runtime": provenance.runtime,
        "session_id": provenance.session_id,
        "transcript_source": provenance.transcript_source,
        "transcript_offset": provenance.transcript_offset,
        "transcript_index": provenance.transcript_index,
        "role": provenance.role,
        "content_type": provenance.content_type,
        "tool_name": provenance.tool_name,
        "tool_use_id": provenance.tool_use_id,
        "source_event_kind": provenance.source_event_kind,
        "timestamp": document.timestamp or provenance.timestamp,
        "source_order": document.source_order,
        "chunk_index": document.chunk_index,
        "chunk_count": document.chunk_count,
        "window_id": routing.window_id,
        "name": routing.name,
        "cwd": routing.cwd,
        "status": routing.status,
        "pinned": routing.pinned,
        "sort_order": routing.sort_order,
        "identity": document.identity.model_dump(mode="json"),
        "provenance": provenance.model_dump(mode="json"),
        "routing": routing.model_dump(mode="json"),
    }


def rows_for_documents(
    documents: list[SearchBackfillDocument],
    *,
    provider: EmbeddingProvider | None = None,
) -> tuple[list[dict[str, Any]], EmbeddingProvider]:
    """Embed and flatten backfill documents into index rows."""
    embedder = provider or get_embedding_provider()
    if not documents:
        return [], embedder
    vectors = embedder.embed_documents([document.text for document in documents])
    if len(vectors) != len(documents):
        raise ValueError("embedding provider returned an unexpected vector count")
    return [
        row_for_document(document, vector)
        for document, vector in zip(documents, vectors, strict=True)
    ], embedder


def connect_lancedb(generation_id: str) -> Any:
    """Open the local embedded LanceDB connection lazily."""
    import lancedb

    path = generation_lancedb_dir(generation_id)
    path.mkdir(parents=True, exist_ok=True)
    return lancedb.connect(str(path))


def _table_names(connection: Any) -> set[str]:
    names = connection.table_names()
    return {str(name) for name in names}


def open_or_create_table(
    connection: Any,
    *,
    table_name: str,
    rows: list[dict[str, Any]],
) -> Any:
    """Open an existing table or create it with the supplied row schema."""
    if table_name in _table_names(connection):
        return connection.open_table(table_name)
    return connection.create_table(table_name, data=rows)


def create_indexes(table: Any) -> None:
    """Create best-effort local FTS/scalar indexes supported by installed LanceDB."""
    try:
        table.create_fts_index("text", use_tantivy=False)
    except TypeError:
        try:
            table.create_fts_index("text")
        except Exception:
            pass
    except Exception:
        pass

    try:
        table.create_scalar_index("row_id")
    except Exception:
        pass


def upsert_rows(table: Any, rows: list[dict[str, Any]]) -> None:
    """Idempotently upsert rows by stable `row_id`."""
    if not rows:
        return
    merger = table.merge_insert("row_id")
    merger.when_matched_update_all().when_not_matched_insert_all().execute(rows)


def upsert_index_documents(
    generation_id: str,
    documents: list[SearchBackfillDocument],
    *,
    provider: EmbeddingProvider | None = None,
    connection: Any | None = None,
    table_name: str = DEFAULT_TABLE_NAME,
) -> SearchIndexMetadata:
    """Embed and upsert live documents into the generation-owned LanceDB table."""
    rows, embedder = rows_for_documents(documents, provider=provider)
    conn = connection or connect_lancedb(generation_id)
    table = open_or_create_table(conn, table_name=table_name, rows=rows)
    upsert_rows(table, rows)
    create_indexes(table)

    metadata = SearchIndexMetadata(
        schema_version=SEARCH_SCHEMA_VERSION,
        generation_id=generation_id,
        model_id=embedder.model_id,
        vector_dimension=embedder.vector_dimension,
        table_name=table_name,
        created_at=_now_iso(),
        completed=True,
    )
    write_index_metadata(metadata)
    return metadata


def materialize_generation_index(
    generation_id: str,
    *,
    documents: list[SearchBackfillDocument] | None = None,
    provider: EmbeddingProvider | None = None,
    connection: Any | None = None,
    table_name: str = DEFAULT_TABLE_NAME,
) -> SearchIndexMetadata:
    """Build or refresh the local index for one completed generation."""
    source_documents = (
        read_generation_documents(generation_id) if documents is None else documents
    )
    return upsert_index_documents(
        generation_id,
        source_documents,
        provider=provider,
        connection=connection,
        table_name=table_name,
    )


def has_completed_index(generation_id: str) -> bool:
    """Return whether a generation has completed local retrieval metadata."""
    return read_index_metadata(generation_id) is not None


__all__ = [
    "DEFAULT_TABLE_NAME",
    "connect_lancedb",
    "create_indexes",
    "has_completed_index",
    "materialize_generation_index",
    "open_or_create_table",
    "row_for_document",
    "row_id_for_identity",
    "rows_for_documents",
    "upsert_index_documents",
    "upsert_rows",
]
