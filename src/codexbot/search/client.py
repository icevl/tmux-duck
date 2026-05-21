"""Dependency-light search provider for request-path status and stubs."""

from __future__ import annotations

from .contracts import (
    SearchCounters,
    SearchRequest,
    SearchResponse,
    SearchStatusResponse,
)
from .state import read_generation_metadata


MISSING_INDEX_REASON = "search index has not been built"
QUERY_BACKEND_UNAVAILABLE_REASON = "search query backend is not available"


def _counters(open_session_count: int | None) -> SearchCounters | None:
    if open_session_count is None:
        return None
    return SearchCounters(open_sessions=open_session_count)


def get_status(open_session_count: int | None = None) -> SearchStatusResponse:
    """Return a typed status response without touching authoritative Codi state."""
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
