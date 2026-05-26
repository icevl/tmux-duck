"""Generation-owned local LanceDB index service."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from .contracts import (
    SearchBackfillDocument,
    SearchIndexMetadata,
    SearchRoutingMetadata,
    SearchRowIdentity,
    TranscriptProvenance,
)
from .embedding import EmbeddingProvider, get_embedding_provider
from .live import read_generation_documents
from .state import (
    SEARCH_SCHEMA_VERSION,
    generation_lancedb_dir,
    read_index_metadata,
    write_index_metadata,
)

# Batch size for incremental embedding. Each batch on CPU takes roughly
# (size / cores) × per-doc-latency seconds, so we keep it small enough
# that the UI ticks at least every ~30s on a 4-core machine. Set
# CODEXBOT_SEARCH_BATCH_SIZE separately for the sentence-transformers
# internal batch (the value here is the *callback* granularity).
EMBED_PROGRESS_BATCH_SIZE = 16

ProgressCallback = Callable[[int, int], None]

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


def _embed_batch(
    embedder: EmbeddingProvider,
    documents: list[SearchBackfillDocument],
) -> list[dict[str, Any]]:
    """Embed one batch of docs into LanceDB rows."""
    if not documents:
        return []
    vectors = embedder.embed_documents([d.text for d in documents])
    if len(vectors) != len(documents):
        raise ValueError("embedding provider returned an unexpected vector count")
    return [
        row_for_document(document, vector)
        for document, vector in zip(documents, vectors, strict=True)
    ]


def rows_for_documents(
    documents: list[SearchBackfillDocument],
    *,
    provider: EmbeddingProvider | None = None,
    progress_cb: ProgressCallback | None = None,
    batch_size: int = EMBED_PROGRESS_BATCH_SIZE,
) -> tuple[list[dict[str, Any]], EmbeddingProvider]:
    """Embed and flatten backfill documents into index rows.

    Used only by the no-incremental-persist path (e.g. live-drain
    snapshots). For the long-running backfill, `upsert_index_documents`
    embeds and upserts one batch at a time so a killed worker doesn't
    lose all its work.
    """
    embedder = provider or get_embedding_provider()
    if not documents:
        if progress_cb is not None:
            progress_cb(0, 0)
        return [], embedder
    total = len(documents)
    if progress_cb is None:
        return _embed_batch(embedder, documents), embedder

    rows: list[dict[str, Any]] = []
    progress_cb(0, total)
    for start in range(0, total, batch_size):
        chunk = documents[start : start + batch_size]
        rows.extend(_embed_batch(embedder, chunk))
        progress_cb(start + len(chunk), total)
    return rows, embedder


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
    progress_cb: ProgressCallback | None = None,
    batch_size: int = EMBED_PROGRESS_BATCH_SIZE,
) -> SearchIndexMetadata:
    """Embed and upsert documents into the generation-owned LanceDB table.

    Embedding and upsert happen one batch at a time so the on-disk index
    grows incrementally. A killed worker preserves every completed batch,
    and `existing_row_ids()` on resume reports those rows so we skip
    re-embedding them. Without per-batch persistence we'd lose hours of
    embedding work on every restart.
    """
    embedder = provider or get_embedding_provider()
    total = len(documents)
    if progress_cb is not None:
        progress_cb(0, total)
    if not documents:
        # Still write metadata so callers see a "completed" record even
        # for an empty pass (e.g. fully-resumed generation).
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

    conn = connection or connect_lancedb(generation_id)
    table: Any | None = None
    for start in range(0, total, batch_size):
        chunk = documents[start : start + batch_size]
        rows = _embed_batch(embedder, chunk)
        if table is None:
            table = open_or_create_table(conn, table_name=table_name, rows=rows)
        upsert_rows(table, rows)
        if progress_cb is not None:
            progress_cb(start + len(chunk), total)
    if table is not None:
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
    progress_cb: ProgressCallback | None = None,
) -> SearchIndexMetadata:
    """Build or refresh the local index for one completed generation."""
    source_documents = (
        read_generation_documents(generation_id) if documents is None else documents
    )
    return upsert_index_documents(
        generation_id,
        source_documents,
        progress_cb=progress_cb,
        provider=provider,
        connection=connection,
        table_name=table_name,
    )


def existing_row_ids(
    generation_id: str,
    *,
    table_name: str = DEFAULT_TABLE_NAME,
) -> set[str]:
    """Return all row_ids already written to this generation's LanceDB table.

    Used by the worker to resume a partially-finished backfill: docs whose
    row_id is in this set were embedded in a previous run and can be
    skipped on the next pass."""
    from .state import generation_lancedb_dir

    path = generation_lancedb_dir(generation_id)
    if not path.exists():
        return set()
    try:
        conn = connect_lancedb(generation_id)
        if table_name not in _table_names(conn):
            return set()
        table = conn.open_table(table_name)
        rows = table.to_pandas(columns=["row_id"])
    except Exception:  # noqa: BLE001
        # If the table is corrupt or unreadable we'd rather re-embed from
        # scratch than silently skip rows we couldn't verify.
        return set()
    return {str(value) for value in rows["row_id"].tolist() if value}


def delete_session_rows(
    generation_id: str,
    window_id: str,
    *,
    table_name: str = DEFAULT_TABLE_NAME,
) -> int:
    """Delete all index rows belonging to one tmux window. Returns the
    number of rows removed. Safe to call when no table exists yet."""
    from .state import generation_lancedb_dir

    path = generation_lancedb_dir(generation_id)
    if not path.exists():
        return 0
    try:
        conn = connect_lancedb(generation_id)
        if table_name not in _table_names(conn):
            return 0
        table = conn.open_table(table_name)
        before = table.count_rows()
        # Embedded single-quote injection is impossible here — window ids
        # match tmux's `@<int>` pattern.
        table.delete(f"window_id = '{window_id}'")
        after = table.count_rows()
        return max(0, before - after)
    except Exception:  # noqa: BLE001
        return 0


def has_completed_index(generation_id: str) -> bool:
    """Return whether a generation has completed local retrieval metadata."""
    return read_index_metadata(generation_id) is not None


def document_from_row(row: dict[str, Any]) -> SearchBackfillDocument:
    """Rehydrate a search document from a flattened LanceDB row."""
    identity_raw = row.get("identity")
    provenance_raw = row.get("provenance")
    routing_raw = row.get("routing")
    identity = (
        SearchRowIdentity(**identity_raw)
        if isinstance(identity_raw, dict)
        else SearchRowIdentity(
            runtime=str(row["runtime"]),
            transcript_source=str(row["transcript_source"]),
            transcript_offset=row.get("transcript_offset"),
            transcript_index=row.get("transcript_index"),
            role=str(row["role"]),
            content_type=str(row["content_type"]),
            tool_use_id=row.get("tool_use_id"),
            chunk_index=int(row.get("chunk_index") or 0),
        )
    )
    provenance = (
        TranscriptProvenance(**provenance_raw)
        if isinstance(provenance_raw, dict)
        else TranscriptProvenance(
            runtime=str(row["runtime"]),
            session_id=row.get("session_id"),
            transcript_source=str(row["transcript_source"]),
            transcript_offset=row.get("transcript_offset"),
            transcript_index=row.get("transcript_index"),
            role=str(row["role"]),
            content_type=str(row["content_type"]),
            tool_name=row.get("tool_name"),
            tool_use_id=row.get("tool_use_id"),
            source_event_kind=str(row.get("source_event_kind") or "indexed_row"),
            timestamp=row.get("timestamp"),
        )
    )
    routing = (
        SearchRoutingMetadata(**routing_raw)
        if isinstance(routing_raw, dict)
        else SearchRoutingMetadata(
            window_id=str(row["window_id"]),
            name=row.get("name"),
            cwd=str(row["cwd"]),
            runtime=str(row["runtime"]),
            session_id=row.get("session_id"),
            status=row.get("status"),
            pinned=bool(row.get("pinned", False)),
            sort_order=row.get("sort_order"),
        )
    )
    return SearchBackfillDocument(
        identity=identity,
        provenance=provenance,
        routing=routing,
        text=str(row.get("text") or ""),
        timestamp=row.get("timestamp"),
        source_order=int(row.get("source_order") or 0),
        chunk_index=int(row.get("chunk_index") or identity.chunk_index),
        chunk_count=int(row.get("chunk_count") or 1),
    )


def semantic_scores_for_query(
    generation_id: str,
    *,
    query: str,
    limit: int,
    provider: EmbeddingProvider | None = None,
    connection: Any | None = None,
    table_name: str = DEFAULT_TABLE_NAME,
) -> dict[str, float]:
    """Return normalized semantic candidate scores keyed by stable row id."""
    embedder = provider or get_embedding_provider()
    query_vector = embedder.embed_query(query)
    conn = connection or connect_lancedb(generation_id)
    table = conn.open_table(table_name)
    rows = table.search(query_vector).limit(limit).to_list()
    scores: dict[str, float] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        row_id = row.get("row_id")
        if not isinstance(row_id, str):
            continue
        raw_score = row.get("_relevance_score", row.get("_score"))
        if isinstance(raw_score, int | float):
            score = max(0.0, min(1.0, float(raw_score)))
        else:
            score = max(0.0, 1.0 - (index * 0.05))
        scores[row_id] = score
    return scores


__all__ = [
    "DEFAULT_TABLE_NAME",
    "connect_lancedb",
    "create_indexes",
    "document_from_row",
    "has_completed_index",
    "delete_session_rows",
    "existing_row_ids",
    "materialize_generation_index",
    "open_or_create_table",
    "row_for_document",
    "row_id_for_identity",
    "rows_for_documents",
    "semantic_scores_for_query",
    "upsert_index_documents",
    "upsert_rows",
]
