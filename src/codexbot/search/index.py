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

# Batch size for incremental embedding. Each batch on CPU takes roughly
# (size / cores) * per-doc-latency seconds, so we keep it small enough
# that the UI ticks at least every ~30s on a 4-core machine. Set
# CODEXBOT_SEARCH_BATCH_SIZE separately for the sentence-transformers
# internal batch (the value here is the *callback* granularity).
EMBED_PROGRESS_BATCH_SIZE = 16

ProgressCallback = Callable[[int, int], None]

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
    vector_dimension: int | None = None,
) -> Any:
    """Open an existing table or create it with the supplied row schema."""
    if table_name in _table_names(connection):
        return connection.open_table(table_name)
    if vector_dimension is not None:
        return connection.create_table(
            table_name,
            data=rows,
            schema=index_schema(vector_dimension),
        )
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
    effective_batch_size = max(1, batch_size)
    for start in range(0, total, effective_batch_size):
        chunk = documents[start : start + effective_batch_size]
        rows = _embed_batch(embedder, chunk)
        created_table = False
        if table is None:
            table_exists = table_name in _table_names(conn)
            table = open_or_create_table(
                conn,
                table_name=table_name,
                rows=rows,
                vector_dimension=embedder.vector_dimension,
            )
            created_table = not table_exists
        if not created_table:
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
    batch_size: int | None = None,
    progress_callback: IndexProgressCallback | None = None,
    progress_cb: ProgressCallback | None = None,
) -> SearchIndexMetadata:
    """Build or refresh the local index for one completed generation."""
    source_documents = list(
        iter_generation_documents(generation_id) if documents is None else documents
    )

    def relay_progress(processed: int, total: int) -> None:
        if progress_cb is not None:
            progress_cb(processed, total)
        if progress_callback is not None and processed > 0:
            progress_callback(processed)

    return upsert_index_documents(
        generation_id,
        source_documents,
        progress_cb=relay_progress
        if progress_cb is not None or progress_callback is not None
        else None,
        provider=provider,
        connection=connection,
        table_name=table_name,
        batch_size=batch_size or _index_batch_size_from_env(),
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


# Drop semantic candidates below this score (cosine ~= 0.2). LanceDB returns
# top-K by L2-squared distance regardless of how loose those matches are; the
# real short-query noise filter lives in retrieval._hybrid_candidates.
SEMANTIC_MIN_SCORE = 0.6


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
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_id = row.get("row_id")
        if not isinstance(row_id, str):
            continue
        score = _row_to_semantic_score(row)
        if score < SEMANTIC_MIN_SCORE:
            continue
        try:
            document = document_from_row(row)
        except Exception:
            continue
        candidates.append(
            SemanticSearchCandidate(
                row_id=row_id,
                document=document,
                score=score,
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
    for row in rows:
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
                score=_row_to_semantic_score(row),
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


def _row_to_semantic_score(row: dict[str, Any]) -> float:
    distance = row.get("_distance")
    if isinstance(distance, (int, float)):
        return max(0.0, min(1.0, 1.0 - float(distance) / 2.0))
    raw = row.get("_relevance_score", row.get("_score"))
    if isinstance(raw, (int, float)):
        return max(0.0, min(1.0, float(raw)))
    return 0.0


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
    "delete_session_rows",
    "existing_row_ids",
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
