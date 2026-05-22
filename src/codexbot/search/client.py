"""Dependency-light search provider for request-path status and stubs."""

from __future__ import annotations

from .contracts import (
    SearchCounters,
    SearchQueueSnapshot,
    SearchRequest,
    SearchResponse,
    SearchStatusResponse,
    SearchWorkerStatus,
)
from .state import (
    read_generation_manifest,
    read_generation_metadata,
    read_worker_status,
)


MISSING_INDEX_REASON = "search index has not been built"
QUERY_BACKEND_UNAVAILABLE_REASON = "search query backend is not available"


def _counters(
    open_session_count: int | None,
    existing: SearchCounters | None = None,
    queue_snapshot: SearchQueueSnapshot | None = None,
) -> SearchCounters | None:
    has_queue_values = (
        queue_snapshot is not None
        and (
            queue_snapshot.queued_items > 0
            or queue_snapshot.leased_items > 0
            or queue_snapshot.failed_items > 0
            or queue_snapshot.stale_sources > 0
            or queue_snapshot.recent_error is not None
        )
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


def get_status(open_session_count: int | None = None) -> SearchStatusResponse:
    """Return a typed status response without touching authoritative Codi state."""
    queue_snapshot = _safe_queue_snapshot()
    worker_status = read_worker_status()
    if worker_status is not None and worker_status.status == "running":
        return SearchStatusResponse(
            state="building",
            available=False,
            scope="open_sessions",
            reason=f"search worker running {_task_label(worker_status)}",
            counters=_counters(
                open_session_count,
                worker_status.counters,
                queue_snapshot,
            ),
            generation=None,
        )
    if worker_status is not None and worker_status.status == "failed":
        return SearchStatusResponse(
            state="unavailable",
            available=False,
            scope="open_sessions",
            reason=_failed_reason(worker_status),
            counters=_counters(
                open_session_count,
                worker_status.counters,
                queue_snapshot,
            ),
            generation=None,
        )

    generation = read_generation_metadata()
    queue_reason = _queue_issue_reason(queue_snapshot)
    counters = _counters(open_session_count, queue_snapshot=queue_snapshot)
    if generation is None:
        return SearchStatusResponse(
            state="degraded" if queue_reason is not None else "missing",
            available=False,
            scope="open_sessions",
            reason=(
                f"{MISSING_INDEX_REASON}; {queue_reason}"
                if queue_reason is not None
                else MISSING_INDEX_REASON
            ),
            counters=counters,
            generation=None,
        )

    manifest = read_generation_manifest(generation.generation_id)
    counters = _counters(
        open_session_count,
        manifest.counters if manifest is not None else None,
        queue_snapshot,
    )
    return SearchStatusResponse(
        state="degraded" if queue_reason is not None else "unavailable",
        available=False,
        scope="open_sessions",
        reason=queue_reason or QUERY_BACKEND_UNAVAILABLE_REASON,
        counters=counters,
        generation=generation,
    )


def search(
    req: SearchRequest, *, open_session_count: int | None = None
) -> SearchResponse:
    """Return a typed empty response until retrieval phases are implemented."""
    return SearchResponse(
        status=get_status(open_session_count=open_session_count),
        query=req.query,
        results=[],
        total_results=0,
        total_sessions=0,
        limit=req.limit,
        hits_per_session=req.hits_per_session,
        outcome="not_ready",
    )


__all__ = ["get_status", "search"]
