"""Dependency-light search provider for request-path status and stubs."""

from __future__ import annotations

from .contracts import (
    SearchCounters,
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
) -> SearchCounters | None:
    if existing is None and open_session_count is None:
        return None
    values = existing.model_dump() if existing is not None else {}
    if open_session_count is not None:
        values["open_sessions"] = open_session_count
    return SearchCounters(**values)


def _task_label(worker_status: SearchWorkerStatus) -> str:
    return worker_status.current_task or "search worker task"


def _failed_reason(worker_status: SearchWorkerStatus) -> str:
    return f"search worker failed during {_task_label(worker_status)}"


def get_status(open_session_count: int | None = None) -> SearchStatusResponse:
    """Return a typed status response without touching authoritative Codi state."""
    worker_status = read_worker_status()
    if worker_status is not None and worker_status.status == "running":
        return SearchStatusResponse(
            state="building",
            available=False,
            scope="open_sessions",
            reason=f"search worker running {_task_label(worker_status)}",
            counters=_counters(open_session_count, worker_status.counters),
            generation=None,
        )
    if worker_status is not None and worker_status.status == "failed":
        return SearchStatusResponse(
            state="unavailable",
            available=False,
            scope="open_sessions",
            reason=_failed_reason(worker_status),
            counters=_counters(open_session_count, worker_status.counters),
            generation=None,
        )

    generation = read_generation_metadata()
    counters = _counters(open_session_count)
    if generation is None:
        return SearchStatusResponse(
            state="missing",
            available=False,
            scope="open_sessions",
            reason=MISSING_INDEX_REASON,
            counters=counters,
            generation=None,
        )

    manifest = read_generation_manifest(generation.generation_id)
    counters = _counters(
        open_session_count,
        manifest.counters if manifest is not None else None,
    )
    return SearchStatusResponse(
        state="unavailable",
        available=False,
        scope="open_sessions",
        reason=QUERY_BACKEND_UNAVAILABLE_REASON,
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
