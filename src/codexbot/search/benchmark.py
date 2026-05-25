"""Opt-in local search benchmark for embedding/index/query validation."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import tempfile
import time
import tracemalloc
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from .contracts import (
    SearchBackfillDocument,
    SearchBenchmarkSummary,
    SearchRequest,
    SearchRoutingMetadata,
    SearchRowIdentity,
    TranscriptProvenance,
)
from .embedding import (
    DEFAULT_EMBEDDING_DIMENSION,
    DEFAULT_EMBEDDING_MODEL_ID,
    EmbeddingConfig,
    EmbeddingProvider,
    SentenceTransformerEmbeddingProvider,
    embedding_config_from_env,
)
from .index import (
    DEFAULT_TABLE_NAME,
    create_indexes,
    open_or_create_table,
    row_id_for_identity,
    rows_for_documents,
    upsert_rows,
)
from .ranking import score_document
from .state import SEARCH_SCHEMA_VERSION, write_benchmark_summary

BENCHMARK_GENERATION_ID = "benchmark"
FAKE_MODEL_ID = "fake/codi-search-benchmark"
FAKE_VECTOR_DIMENSION = 16


class FakeEmbeddingProvider:
    """Deterministic lightweight provider for tests and offline benchmark checks."""

    model_id = FAKE_MODEL_ID
    vector_dimension = FAKE_VECTOR_DIMENSION

    _features: tuple[tuple[str, ...], ...] = (
        ("shell", "terminal", "console", "attach", "pane"),
        ("persistent", "persisted", "alive", "survives", "reload"),
        ("callback", "webhook", "event"),
        ("failure", "error", "exception", "traceback"),
        ("path", "src/", "api.py", "file"),
        ("command", "pytest", "uv", "git", "tmux"),
        ("queue", "queued", "dead-letter", "worker"),
        ("mobile", "touch", "phone"),
        ("search", "semantic", "lexical", "index"),
        ("notification", "notify", "waiting"),
        ("session", "window", "runtime"),
        ("model", "qwen", "embedding"),
        ("benchmark", "latency", "memory"),
        ("status", "heartbeat", "stale"),
        ("drag", "reorder", "pinned"),
        ("choice", "input", "plan"),
    )

    def _vector(self, text: str) -> list[float]:
        lower = text.casefold()
        values: list[float] = []
        for terms in self._features:
            values.append(float(any(term in lower for term in terms)))
        digest = hashlib.sha256(lower.encode("utf-8")).digest()
        for index, value in enumerate(values):
            values[index] = value + (digest[index] / 2550.0)
        length = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / length for value in values]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _package_versions(provider: Literal["fake", "local"]) -> dict[str, str]:
    packages = ["lancedb"]
    if provider == "local":
        packages.extend(["sentence-transformers", "transformers"])
    versions: dict[str, str] = {}
    for package in packages:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not-installed"
    return versions


def _chunk_text(text: str, *, max_chars: int, overlap_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    step = max(1, max_chars - overlap_chars)
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunk = text[start : start + max_chars].strip()
        if chunk:
            chunks.append(chunk)
        start += step
    return chunks or [text[:max_chars]]


def _document_from_fixture(
    raw: dict[str, Any],
    *,
    source_order: int,
    chunk_index: int,
    chunk_count: int,
    text: str,
) -> SearchBackfillDocument:
    runtime = str(raw.get("runtime") or "codex")
    session_id = str(raw.get("session_id") or f"benchmark-session-{source_order}")
    transcript_source = str(raw.get("transcript_source") or f"benchmark://{session_id}")
    role = str(raw.get("role") or "assistant")
    content_type = str(raw.get("content_type") or "text")
    provenance = TranscriptProvenance(
        runtime=runtime,
        session_id=session_id,
        transcript_source=transcript_source,
        transcript_offset=raw.get("transcript_offset"),
        transcript_index=raw.get("transcript_index") or source_order,
        role=role,
        content_type=content_type,
        tool_name=raw.get("tool_name"),
        tool_use_id=raw.get("tool_use_id"),
        source_event_kind=str(raw.get("source_event_kind") or "benchmark_fixture"),
        timestamp=raw.get("timestamp"),
    )
    return SearchBackfillDocument(
        identity=SearchRowIdentity.from_provenance(
            provenance,
            chunk_index=chunk_index,
        ),
        provenance=provenance,
        routing=SearchRoutingMetadata(
            window_id=str(raw["window_id"]),
            name=raw.get("name"),
            cwd=str(raw.get("cwd") or "/repo/codi"),
            runtime=runtime,
            session_id=session_id,
            status=raw.get("status") or "active",
            pinned=bool(raw.get("pinned", False)),
            sort_order=raw.get("sort_order"),
        ),
        text=text,
        timestamp=raw.get("timestamp"),
        source_order=source_order,
        chunk_index=chunk_index,
        chunk_count=chunk_count,
    )


def _load_fixture_documents(
    raw_documents: list[dict[str, Any]],
    *,
    chunk_max_chars: int,
    chunk_overlap_chars: int,
) -> list[SearchBackfillDocument]:
    documents: list[SearchBackfillDocument] = []
    source_order = 0
    for raw in raw_documents:
        text = str(raw.get("text") or "").strip()
        if not text:
            continue
        chunks = _chunk_text(
            text,
            max_chars=chunk_max_chars,
            overlap_chars=chunk_overlap_chars,
        )
        for chunk_index, chunk in enumerate(chunks):
            documents.append(
                _document_from_fixture(
                    raw,
                    source_order=source_order,
                    chunk_index=chunk_index,
                    chunk_count=len(chunks),
                    text=chunk,
                )
            )
            source_order += 1
    return documents


def _load_fixtures(
    path: Path,
    *,
    chunk_max_chars: int,
    chunk_overlap_chars: int,
) -> tuple[list[SearchBackfillDocument], list[dict[str, Any]]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("benchmark fixture must be a JSON object")
    raw_documents = raw.get("documents")
    raw_queries = raw.get("queries")
    if not isinstance(raw_documents, list) or not isinstance(raw_queries, list):
        raise ValueError("benchmark fixture must contain documents and queries")
    documents = _load_fixture_documents(
        [item for item in raw_documents if isinstance(item, dict)],
        chunk_max_chars=chunk_max_chars,
        chunk_overlap_chars=chunk_overlap_chars,
    )
    queries = [item for item in raw_queries if isinstance(item, dict)]
    if not documents or not queries:
        raise ValueError("benchmark fixture must include documents and queries")
    return documents, queries


def _provider(
    provider: Literal["fake", "local"],
    *,
    model: str,
    batch_size: int,
) -> EmbeddingProvider:
    if provider == "fake":
        return FakeEmbeddingProvider()
    env_config = embedding_config_from_env()
    return SentenceTransformerEmbeddingProvider(
        EmbeddingConfig(
            model_id=model,
            vector_dimension=env_config.vector_dimension or DEFAULT_EMBEDDING_DIMENSION,
            batch_size=batch_size,
            local_files_only=env_config.local_files_only,
        )
    )


def _score_from_row(index: int, row: dict[str, Any]) -> float:
    raw_score = row.get("_relevance_score", row.get("_score"))
    if isinstance(raw_score, int | float):
        return max(0.0, min(1.0, float(raw_score)))
    return max(0.0, 1.0 - (index * 0.05))


def _semantic_scores(
    table: Any,
    provider: EmbeddingProvider,
    *,
    query: str,
    limit: int,
) -> dict[str, float]:
    rows = table.search(provider.embed_query(query)).limit(limit).to_list()
    scores: dict[str, float] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        row_id = row.get("row_id")
        if isinstance(row_id, str):
            scores[row_id] = _score_from_row(index, row)
    return scores


def _rank_windows(
    documents: list[SearchBackfillDocument],
    scores: dict[str, float],
    *,
    query: str,
) -> list[str]:
    candidates = []
    req = SearchRequest(query=query, limit=50, hits_per_session=10)
    for document in documents:
        candidate = score_document(
            document,
            req,
            semantic_score=scores.get(row_id_for_identity(document.identity), 0.0),
        )
        if candidate is not None:
            candidates.append(candidate)
    candidates.sort(
        key=lambda item: (
            -item.score,
            item.document.source_order,
            item.document.chunk_index,
        )
    )
    windows: list[str] = []
    for candidate in candidates:
        window_id = candidate.document.routing.window_id
        if window_id not in windows:
            windows.append(window_id)
    return windows


def _ratio(successes: int, total: int) -> float:
    if total <= 0:
        return 1.0
    return successes / total


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * percentile) - 1))
    return ordered[index]


def run_benchmark(
    *,
    fixtures: Path,
    provider_name: Literal["fake", "local"] = "fake",
    model: str = DEFAULT_EMBEDDING_MODEL_ID,
    batch_size: int = 16,
    chunk_max_chars: int = 1200,
    chunk_overlap_chars: int = 120,
    threshold_query_p95_ms: float | None = None,
    threshold_memory_mb: float | None = None,
    write_summary: bool = False,
) -> SearchBenchmarkSummary:
    """Run the benchmark and optionally persist the metrics-only summary."""
    documents, queries = _load_fixtures(
        fixtures,
        chunk_max_chars=chunk_max_chars,
        chunk_overlap_chars=chunk_overlap_chars,
    )
    provider = _provider(provider_name, model=model, batch_size=batch_size)
    tracemalloc.start()
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="codi-search-benchmark-") as tmpdir:
        rows, embedder = rows_for_documents(documents, provider=provider)
        embedded_at = time.perf_counter()
        import lancedb

        connection = lancedb.connect(tmpdir)
        table = open_or_create_table(
            connection,
            table_name=DEFAULT_TABLE_NAME,
            rows=rows,
        )
        upsert_rows(table, rows)
        create_indexes(table)
        indexed_at = time.perf_counter()

        exact_successes = 0
        exact_total = 0
        semantic_successes = 0
        semantic_total = 0
        fallback_successes = 0
        fallback_total = 0
        latencies_ms: list[float] = []
        for query_case in queries:
            query = str(query_case.get("query") or "").strip()
            expected_window_id = str(query_case.get("expected_window_id") or "")
            if not query or not expected_window_id:
                continue
            query_started = time.perf_counter()
            scores = _semantic_scores(
                table,
                embedder,
                query=query,
                limit=max(10, len(documents)),
            )
            windows = _rank_windows(documents, scores, query=query)
            latencies_ms.append((time.perf_counter() - query_started) * 1000.0)
            kind = str(query_case.get("kind") or "exact")
            if kind == "semantic":
                semantic_total += 1
                if expected_window_id in windows[:5]:
                    semantic_successes += 1
            else:
                exact_total += 1
                if expected_window_id in windows[:3]:
                    exact_successes += 1
            if bool(query_case.get("fallback")):
                fallback_total += 1
                lexical_windows = _rank_windows(documents, {}, query=query)
                if expected_window_id in lexical_windows[:5]:
                    fallback_successes += 1

    current, peak = tracemalloc.get_traced_memory()
    _ = current
    tracemalloc.stop()
    embedding_seconds = max(embedded_at - started, 0.000001)
    index_elapsed_ms = (indexed_at - started) * 1000.0
    peak_memory_mb = peak / (1024 * 1024)
    exact_top3 = _ratio(exact_successes, exact_total)
    semantic_top5 = _ratio(semantic_successes, semantic_total)
    fallback_ok = fallback_total == 0 or fallback_successes == fallback_total
    thresholds: dict[str, float] = {}
    failures: list[str] = []
    query_p95_ms = _percentile(latencies_ms, 0.95)
    if threshold_query_p95_ms is not None:
        thresholds["query_p95_ms"] = threshold_query_p95_ms
        if query_p95_ms > threshold_query_p95_ms:
            failures.append("query_p95_ms")
    if threshold_memory_mb is not None:
        thresholds["peak_memory_mb"] = threshold_memory_mb
        if peak_memory_mb > threshold_memory_mb:
            failures.append("peak_memory_mb")
    ok = not failures and fallback_ok
    summary = SearchBenchmarkSummary(
        schema_version=SEARCH_SCHEMA_VERSION,
        created_at=_now_iso(),
        ok=ok,
        provider=provider_name,
        model_id=provider.model_id,
        vector_dimension=provider.vector_dimension,
        batch_size=batch_size,
        chunk_max_chars=chunk_max_chars,
        chunk_overlap_chars=chunk_overlap_chars,
        document_count=len(documents),
        query_count=len(queries),
        index_elapsed_ms=round(index_elapsed_ms, 3),
        query_p50_ms=round(_percentile(latencies_ms, 0.5), 3),
        query_p95_ms=round(query_p95_ms, 3),
        peak_memory_mb=round(peak_memory_mb, 3),
        embedding_docs_per_second=round(len(documents) / embedding_seconds, 3),
        exact_top3=round(exact_top3, 6),
        semantic_top5=round(semantic_top5, 6),
        fallback_ok=fallback_ok,
        package_versions=_package_versions(provider_name),
        exact_top3_recall=round(exact_top3, 6),
        semantic_top5_recall=round(semantic_top5, 6),
        passed=ok,
        failures=failures,
        thresholds=thresholds,
    )
    if write_summary:
        write_benchmark_summary(summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="codexbot-search-benchmark")
    parser.add_argument("--fixtures", required=True, type=Path)
    parser.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL_ID)
    parser.add_argument("--provider", choices=("fake", "local"), default="fake")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--chunk-max-chars", type=int, default=1200)
    parser.add_argument("--chunk-overlap-chars", type=int, default=120)
    parser.add_argument("--threshold-query-p95-ms", type=float, default=None)
    parser.add_argument("--threshold-memory-mb", type=float, default=None)
    parser.add_argument("--write-summary", action="store_true")
    args = parser.parse_args(argv)

    try:
        summary = run_benchmark(
            fixtures=args.fixtures,
            provider_name=args.provider,
            model=args.model,
            batch_size=args.batch_size,
            chunk_max_chars=args.chunk_max_chars,
            chunk_overlap_chars=args.chunk_overlap_chars,
            threshold_query_p95_ms=args.threshold_query_p95_ms,
            threshold_memory_mb=args.threshold_memory_mb,
            write_summary=args.write_summary,
        )
    except Exception as exc:
        from .queue import sanitize_error

        print(json.dumps({"ok": False, "error": sanitize_error(exc)}))
        return 1

    print(json.dumps(summary.model_dump(mode="json"), sort_keys=True))
    return 0 if summary.ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["FakeEmbeddingProvider", "main", "run_benchmark"]
