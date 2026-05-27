"""Generation-owned local LanceDB index service."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable, Iterable, Iterator

from .contracts import (
    SearchBackfillDocument,
    SearchIndexMetadata,
    SearchRoutingMetadata,
    SearchRowIdentity,
    TranscriptProvenance,
)
from .embedding import EmbeddingProvider, get_embedding_provider
from .queue import parse_document
from .state import (
    SEARCH_SCHEMA_VERSION,
    generation_documents_path,
    generation_lancedb_dir,
    read_index_metadata,
    write_index_metadata,
)

DEFAULT_TABLE_NAME = "chunks"
DEFAULT_INDEX_BATCH_SIZE = 16
IndexProgressCallback = Callable[[int], None]


@dataclass(frozen=True)
class SemanticSearchCandidate:
    """One rehydrated vector-search hit with a normalized semantic score."""

    row_id: str
    document: SearchBackfillDocument
    score: float


@dataclass(frozen=True)
class FullTextSearchCandidate:
    """One rehydrated full-text hit from LanceDB FTS."""

    row_id: str
    document: SearchBackfillDocument
    score: float


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _index_batch_size_from_env() -> int:
    raw = os.getenv("CODEXBOT_SEARCH_INDEX_BATCH_SIZE", str(DEFAULT_INDEX_BATCH_SIZE))
    try:
        return max(1, int(raw))
    except ValueError:
        return DEFAULT_INDEX_BATCH_SIZE


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
        "identity": json.dumps(
            document.identity.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
        ),
        "provenance": json.dumps(
            provenance.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
        ),
        "routing": json.dumps(
            routing.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
        ),
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


def iter_generation_documents(generation_id: str) -> Iterator[SearchBackfillDocument]:
    """Yield valid generation documents without loading the whole corpus."""
    path = generation_documents_path(generation_id)
    try:
        with path.open(encoding="utf-8") as f:
            for line in f:
                document = parse_document(line)
                if document is not None:
                    yield document
    except OSError:
        return


def document_batches(
    documents: Iterable[SearchBackfillDocument],
    *,
    batch_size: int,
) -> Iterator[list[SearchBackfillDocument]]:
    """Yield bounded document batches for embedding/index writes."""
    batch: list[SearchBackfillDocument] = []
    for document in documents:
        batch.append(document)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


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


def index_schema(vector_dimension: int) -> Any:
    """Return a stable LanceDB schema for all optional search row columns."""
    import pyarrow as pa

    return pa.schema(
        [
            pa.field("row_id", pa.string()),
            pa.field("text", pa.string()),
            pa.field("vector", pa.list_(pa.float32(), vector_dimension)),
            pa.field("runtime", pa.string()),
            pa.field("session_id", pa.string()),
            pa.field("transcript_source", pa.string()),
            pa.field("transcript_offset", pa.int64()),
            pa.field("transcript_index", pa.int64()),
            pa.field("role", pa.string()),
            pa.field("content_type", pa.string()),
            pa.field("tool_name", pa.string()),
            pa.field("tool_use_id", pa.string()),
            pa.field("source_event_kind", pa.string()),
            pa.field("timestamp", pa.string()),
            pa.field("source_order", pa.int64()),
            pa.field("chunk_index", pa.int64()),
            pa.field("chunk_count", pa.int64()),
            pa.field("window_id", pa.string()),
            pa.field("name", pa.string()),
            pa.field("cwd", pa.string()),
            pa.field("status", pa.string()),
            pa.field("pinned", pa.bool_()),
            pa.field("sort_order", pa.int64()),
            pa.field("identity", pa.string()),
            pa.field("provenance", pa.string()),
            pa.field("routing", pa.string()),
        ]
    )


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
    table = None
    if rows:
        if table_name in _table_names(conn):
            table = conn.open_table(table_name)
            upsert_rows(table, rows)
        else:
            table = conn.create_table(
                table_name,
                data=rows,
                schema=index_schema(embedder.vector_dimension),
            )
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
    batch_size: int | None = None,
    progress_callback: IndexProgressCallback | None = None,
) -> SearchIndexMetadata:
    """Build or refresh the local index for one completed generation."""
    embedder = provider or get_embedding_provider()
    source_documents: Iterable[SearchBackfillDocument] = (
        iter_generation_documents(generation_id) if documents is None else documents
    )
    conn = connection or connect_lancedb(generation_id)
    table = None
    processed = 0
    effective_batch_size = batch_size or _index_batch_size_from_env()

    for batch in document_batches(source_documents, batch_size=effective_batch_size):
        rows, embedder = rows_for_documents(batch, provider=embedder)
        if table is None:
            if table_name in _table_names(conn):
                table = conn.open_table(table_name)
            else:
                table = conn.create_table(
                    table_name,
                    data=rows,
                    schema=index_schema(embedder.vector_dimension),
                )
                rows = []
        if rows:
            upsert_rows(table, rows)
        processed += len(batch)
        if progress_callback is not None:
            progress_callback(processed)

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


def has_completed_index(generation_id: str) -> bool:
    """Return whether a generation has completed local retrieval metadata."""
    return read_index_metadata(generation_id) is not None


def document_from_row(row: dict[str, Any]) -> SearchBackfillDocument:
    """Rehydrate a search document from a flattened LanceDB row."""
    identity_raw = row.get("identity")
    provenance_raw = row.get("provenance")
    routing_raw = row.get("routing")
    if isinstance(identity_raw, str):
        try:
            identity_raw = json.loads(identity_raw)
        except json.JSONDecodeError:
            identity_raw = None
    if isinstance(provenance_raw, str):
        try:
            provenance_raw = json.loads(provenance_raw)
        except json.JSONDecodeError:
            provenance_raw = None
    if isinstance(routing_raw, str):
        try:
            routing_raw = json.loads(routing_raw)
        except json.JSONDecodeError:
            routing_raw = None
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


def _semantic_score_from_row(row: dict[str, Any], index: int) -> float:
    raw_score = row.get("_relevance_score", row.get("_score"))
    if isinstance(raw_score, int | float):
        return max(0.0, min(1.0, float(raw_score)))
    raw_distance = row.get("_distance")
    if isinstance(raw_distance, int | float):
        return max(0.0, min(1.0, 1.0 / (1.0 + max(0.0, float(raw_distance)))))
    return max(0.0, 1.0 - (index * 0.05))


def semantic_candidates_for_query(
    generation_id: str,
    *,
    query: str,
    limit: int,
    provider: EmbeddingProvider | None = None,
    connection: Any | None = None,
    table_name: str = DEFAULT_TABLE_NAME,
) -> list[SemanticSearchCandidate]:
    """Return bounded semantic candidates rehydrated from LanceDB rows."""
    embedder = provider or get_embedding_provider()
    query_vector = embedder.embed_query(query)
    conn = connection or connect_lancedb(generation_id)
    table = conn.open_table(table_name)
    rows = table.search(query_vector).limit(limit).to_list()
    candidates: list[SemanticSearchCandidate] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        row_id = row.get("row_id")
        if not isinstance(row_id, str):
            continue
        try:
            document = document_from_row(row)
        except Exception:
            continue
        candidates.append(
            SemanticSearchCandidate(
                row_id=row_id,
                document=document,
                score=_semantic_score_from_row(row, index),
            )
        )
    return candidates


def full_text_candidates_for_query(
    generation_id: str,
    *,
    query: str,
    limit: int,
    connection: Any | None = None,
    table_name: str = DEFAULT_TABLE_NAME,
) -> list[FullTextSearchCandidate]:
    """Return bounded lexical candidates from the generation FTS index."""
    conn = connection or connect_lancedb(generation_id)
    table = conn.open_table(table_name)
    rows = table.search(query, query_type="fts").limit(limit).to_list()
    candidates: list[FullTextSearchCandidate] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        row_id = row.get("row_id")
        if not isinstance(row_id, str):
            continue
        try:
            document = document_from_row(row)
        except Exception:
            continue
        candidates.append(
            FullTextSearchCandidate(
                row_id=row_id,
                document=document,
                score=_semantic_score_from_row(row, index),
            )
        )
    return candidates


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
    candidates = semantic_candidates_for_query(
        generation_id,
        query=query,
        limit=limit,
        provider=provider,
        connection=connection,
        table_name=table_name,
    )
    scores: dict[str, float] = {}
    for candidate in candidates:
        scores[candidate.row_id] = candidate.score
    return scores


__all__ = [
    "DEFAULT_TABLE_NAME",
    "FullTextSearchCandidate",
    "connect_lancedb",
    "create_indexes",
    "document_from_row",
    "document_batches",
    "full_text_candidates_for_query",
    "has_completed_index",
    "index_schema",
    "iter_generation_documents",
    "materialize_generation_index",
    "open_or_create_table",
    "row_for_document",
    "row_id_for_identity",
    "rows_for_documents",
    "SemanticSearchCandidate",
    "semantic_candidates_for_query",
    "semantic_scores_for_query",
    "upsert_index_documents",
    "upsert_rows",
]
