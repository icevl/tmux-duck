"""Dependency-light search provider for request-path status and stubs."""

from __future__ import annotations

import os
from datetime import UTC, datetime

from .contracts import (
    SearchCounters,
    SearchBackfillProgress,
    SearchGenerationMetadata,
    SearchIndexMetadata,
    SearchIndexState,
    SearchOperationalStatus,
    SearchQueueSnapshot,
    SearchQueueHealth,
    SearchRequest,
    SearchResponse,
    SearchRecoveryCommand,
    SearchStatusResponse,
    SearchWorkerHealth,
    SearchWorkerStatus,
)
from .state import (
    read_generation_manifest,
    read_generation_metadata,
    read_index_metadata,
    read_worker_status,
)


MISSING_INDEX_REASON = "search index has not been built"
QUERY_BACKEND_UNAVAILABLE_REASON = "search query backend is not available"
LEXICAL_DEGRADED_STATUS_REASON = (
    "semantic index is unavailable; lexical search is available"
)
DEFAULT_WORKER_STALE_SECONDS = 120


def _worker_stale_seconds() -> int:
    raw = os.getenv(
        "CODEXBOT_SEARCH_WORKER_STALE_SECONDS",
        str(DEFAULT_WORKER_STALE_SECONDS),
    )
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_WORKER_STALE_SECONDS
    return max(1, value)


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _sanitize_error(value: str | BaseException | None) -> str | None:
    if value is None:
        return None
    try:
        from .queue import sanitize_error

        return sanitize_error(value)
    except Exception:
        return str(value).splitlines()[0][:500]


def _counters(
    open_session_count: int | None,
    existing: SearchCounters | None = None,
    queue_snapshot: SearchQueueSnapshot | None = None,
) -> SearchCounters | None:
    has_queue_values = queue_snapshot is not None and (
        queue_snapshot.queued_items > 0
        or queue_snapshot.leased_items > 0
        or queue_snapshot.failed_items > 0
        or queue_snapshot.stale_sources > 0
        or queue_snapshot.recent_error is not None
    )
    if existing is None and open_session_count is None and not has_queue_values:
        return None
    values = existing.model_dump() if existing is not None else {}
    if open_session_count is not None:
        values["open_sessions"] = open_session_count
    if queue_snapshot is not None and has_queue_values:
        existing_failed = int(values.get("failed_items", 0))
        values["queued_items"] = (
            queue_snapshot.queued_items + queue_snapshot.leased_items
        )
        values["failed_items"] = max(existing_failed, queue_snapshot.failed_items)
    return SearchCounters(**values)


def _task_label(worker_status: SearchWorkerStatus) -> str:
    return worker_status.current_task or "search worker task"


def _failed_reason(worker_status: SearchWorkerStatus) -> str:
    return f"search worker failed during {_task_label(worker_status)}"


def _stale_reason(worker_status: SearchWorkerStatus) -> str:
    return f"search worker heartbeat is stale during {_task_label(worker_status)}"


def _safe_queue_snapshot() -> SearchQueueSnapshot | None:
    try:
        from .queue import get_queue_snapshot

        return get_queue_snapshot()
    except Exception:
        return None


def _queue_issue_reason(snapshot: SearchQueueSnapshot | None) -> str | None:
    if snapshot is None:
        return None
    if snapshot.failed_items:
        reason = f"search queue has {snapshot.failed_items} failed item(s)"
        if snapshot.recent_error:
            reason = f"{reason}: {snapshot.recent_error}"
        return reason
    queued = snapshot.queued_items + snapshot.leased_items
    if queued:
        return f"search queue is behind by {queued} item(s)"
    if snapshot.recent_error:
        return f"search queue degraded: {snapshot.recent_error}"
    return None


def _worker_health(worker_status: SearchWorkerStatus | None) -> SearchWorkerHealth:
    stale_after = _worker_stale_seconds()
    heartbeat_at = worker_status.heartbeat_at if worker_status is not None else None
    heartbeat = _parse_iso(heartbeat_at)
    age = None
    if heartbeat is not None:
        age = max(0.0, (datetime.now(UTC) - heartbeat).total_seconds())
    stale = bool(
        worker_status is not None
        and worker_status.status == "running"
        and age is not None
        and age > stale_after
    )
    return SearchWorkerHealth(
        status=worker_status.status if worker_status is not None else None,
        current_task=worker_status.current_task if worker_status is not None else None,
        heartbeat_at=heartbeat_at,
        heartbeat_age_seconds=round(age, 3) if age is not None else None,
        stale=stale,
        stale_after_seconds=stale_after,
        recent_error=_sanitize_error(worker_status.recent_error)
        if worker_status is not None
        else None,
    )


def _queue_health(snapshot: SearchQueueSnapshot | None) -> SearchQueueHealth:
    if snapshot is None:
        return SearchQueueHealth()
    queued = snapshot.queued_items + snapshot.leased_items
    lagging = bool(
        queued > 0
        or snapshot.failed_items > 0
        or snapshot.stale_sources > 0
        or snapshot.recent_error
    )
    return SearchQueueHealth(
        queued_items=snapshot.queued_items,
        leased_items=snapshot.leased_items,
        failed_items=snapshot.failed_items,
        stale_sources=snapshot.stale_sources,
        oldest_queued_at=snapshot.oldest_queued_at,
        oldest_queued_age_seconds=snapshot.oldest_queued_age_seconds,
        lagging=lagging,
        recent_error=_sanitize_error(snapshot.recent_error),
    )


def _progress(
    counters: SearchCounters | None,
    generation_id: str | None,
    index_metadata: SearchIndexMetadata | None,
) -> SearchBackfillProgress:
    model_id = None
    vector_dimension = None
    table_name = None
    if index_metadata is not None:
        model_id = getattr(index_metadata, "model_id", None)
        vector_dimension = getattr(index_metadata, "vector_dimension", None)
        table_name = getattr(index_metadata, "table_name", None)
    return SearchBackfillProgress(
        open_sessions=counters.open_sessions if counters is not None else 0,
        indexed_sessions=counters.indexed_sessions if counters is not None else 0,
        indexed_chunks=counters.indexed_chunks if counters is not None else 0,
        queued_items=counters.queued_items if counters is not None else 0,
        failed_items=counters.failed_items if counters is not None else 0,
        generation_id=generation_id,
        model_id=model_id,
        vector_dimension=vector_dimension,
        table_name=table_name,
    )


def _recent_errors(
    worker_health: SearchWorkerHealth,
    queue_health: SearchQueueHealth,
    index_error: str | None,
    manifest_errors: list[str] | None,
) -> list[str]:
    seen: set[str] = set()
    values = [
        worker_health.recent_error,
        queue_health.recent_error,
        _sanitize_error(index_error),
        *[_sanitize_error(error) for error in (manifest_errors or [])],
    ]
    errors: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        errors.append(value)
        if len(errors) >= 5:
            break
    return errors


def _recovery_commands() -> list[SearchRecoveryCommand]:
    return [
        SearchRecoveryCommand(
            label="Rebuild index",
            command="codexbot-search-worker rebuild",
            description="Rebuild the local open-session search index.",
        ),
        SearchRecoveryCommand(
            label="Run benchmark",
            command="codexbot-search-benchmark --provider fake",
            description="Validate local search scoring without loading the model.",
        ),
    ]


def _operations(
    *,
    worker_status: SearchWorkerStatus | None,
    queue_snapshot: SearchQueueSnapshot | None,
    counters: SearchCounters | None,
    generation_id: str | None,
    index_metadata: SearchIndexMetadata | None,
    index_error: str | None = None,
    manifest_errors: list[str] | None = None,
) -> SearchOperationalStatus:
    worker_health = _worker_health(worker_status)
    queue_health = _queue_health(queue_snapshot)
    return SearchOperationalStatus(
        worker=worker_health,
        queue=queue_health,
        progress=_progress(counters, generation_id, index_metadata),
        recent_errors=_recent_errors(
            worker_health,
            queue_health,
            index_error,
            manifest_errors,
        ),
        recovery_commands=_recovery_commands(),
        benchmark=None,
    )


def _status(
    *,
    state: SearchIndexState,
    available: bool,
    reason: str | None,
    counters: SearchCounters | None,
    generation: SearchGenerationMetadata | None,
    index: SearchIndexMetadata | None = None,
    worker_status: SearchWorkerStatus | None,
    queue_snapshot: SearchQueueSnapshot | None,
    index_error: str | None = None,
    manifest_errors: list[str] | None = None,
) -> SearchStatusResponse:
    generation_id = getattr(generation, "generation_id", None)
    return SearchStatusResponse(
        state=state,
        available=available,
        scope="open_sessions",
        reason=reason,
        counters=counters,
        generation=generation,
        index=index,
        operations=_operations(
            worker_status=worker_status,
            queue_snapshot=queue_snapshot,
            counters=counters,
            generation_id=generation_id,
            index_metadata=index,
            index_error=index_error,
            manifest_errors=manifest_errors,
        ),
    )


def get_status(open_session_count: int | None = None) -> SearchStatusResponse:
    """Return a typed status response without touching authoritative Codi state."""
    queue_snapshot = _safe_queue_snapshot()
    worker_status = read_worker_status()
    worker_health = _worker_health(worker_status)
    generation = read_generation_metadata()

    if (
        worker_status is not None
        and worker_status.status == "running"
        and not worker_health.stale
        and generation is None
    ):
        return _status(
            state="building",
            available=False,
            reason=f"search worker running {_task_label(worker_status)}",
            counters=_counters(
                open_session_count,
                worker_status.counters,
                queue_snapshot,
            ),
            generation=None,
            worker_status=worker_status,
            queue_snapshot=queue_snapshot,
        )

    if (
        worker_status is not None
        and worker_status.status == "failed"
        and generation is None
    ):
        return _status(
            state="unavailable",
            available=False,
            reason=_failed_reason(worker_status),
            counters=_counters(
                open_session_count,
                worker_status.counters,
                queue_snapshot,
            ),
            generation=None,
            worker_status=worker_status,
            queue_snapshot=queue_snapshot,
        )

    queue_reason = _queue_issue_reason(queue_snapshot)
    counters = _counters(open_session_count, queue_snapshot=queue_snapshot)
    if generation is None:
        stale_reason = (
            _stale_reason(worker_status)
            if worker_status is not None and worker_health.stale
            else None
        )
        reason_parts = [
            part
            for part in (MISSING_INDEX_REASON, stale_reason, queue_reason)
            if part is not None
        ]
        return _status(
            state="unavailable"
            if stale_reason
            else "degraded"
            if queue_reason is not None
            else "missing",
            available=False,
            reason="; ".join(reason_parts),
            counters=counters,
            generation=None,
            worker_status=worker_status,
            queue_snapshot=queue_snapshot,
        )

    manifest = read_generation_manifest(generation.generation_id)
    counters = _counters(
        open_session_count,
        manifest.counters if manifest is not None else None,
        queue_snapshot,
    )
    if manifest is not None:
        index_metadata = read_index_metadata(generation.generation_id)
        degraded_reasons = [
            reason
            for reason in (
                queue_reason,
                _stale_reason(worker_status)
                if worker_status is not None and worker_health.stale
                else None,
                _failed_reason(worker_status)
                if worker_status is not None and worker_status.status == "failed"
                else None,
            )
            if reason is not None
        ]
        if index_metadata is not None:
            return _status(
                state="degraded" if degraded_reasons else "ready",
                available=True,
                reason="; ".join(degraded_reasons) if degraded_reasons else None,
                counters=counters,
                generation=generation,
                index=index_metadata,
                worker_status=worker_status,
                queue_snapshot=queue_snapshot,
                index_error=index_metadata.recent_error,
                manifest_errors=manifest.errors,
            )
        reason = "; ".join(degraded_reasons) if degraded_reasons else None
        reason = reason or LEXICAL_DEGRADED_STATUS_REASON
        return _status(
            state="degraded",
            available=True,
            reason=reason,
            counters=counters,
            generation=generation,
            index=None,
            worker_status=worker_status,
            queue_snapshot=queue_snapshot,
            manifest_errors=manifest.errors,
        )

    return _status(
        state="unavailable",
        available=False,
        reason=QUERY_BACKEND_UNAVAILABLE_REASON,
        counters=counters,
        generation=generation,
        index=None,
        worker_status=worker_status,
        queue_snapshot=queue_snapshot,
    )


def search(
    req: SearchRequest, *, open_session_count: int | None = None
) -> SearchResponse:
    """Return a typed search response through the lightweight request boundary."""
    status = get_status(open_session_count=open_session_count)
    if status.generation is not None and status.available:
        from .retrieval import search_generation

        return search_generation(
            req,
            generation=status.generation,
            status=status,
        )

    return SearchResponse(
        status=status,
        query=req.query,
        results=[],
        total_results=0,
        total_sessions=0,
        limit=req.limit,
        hits_per_session=req.hits_per_session,
        outcome="not_ready",
    )


__all__ = ["get_status", "search"]
