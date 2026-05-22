"""Dependency-light search retrieval providers."""

from __future__ import annotations

from .contracts import (
    SearchGenerationMetadata,
    SearchRequest,
    SearchResponse,
    SearchStatusResponse,
)
from .live import filter_stale_documents, read_generation_documents
from .ranking import lexical_candidates, session_results_from_candidates


LEXICAL_DEGRADED_REASON = "semantic index is unavailable; using lexical retrieval"


def search_generation_lexical(
    req: SearchRequest,
    *,
    generation: SearchGenerationMetadata,
    status: SearchStatusResponse,
) -> SearchResponse:
    """Return bounded lexical results over active generation documents."""
    documents = filter_stale_documents(read_generation_documents(generation.generation_id))
    degraded_status = status.model_copy(
        update={
            "state": "degraded",
            "available": True,
            "reason": status.reason or LEXICAL_DEGRADED_REASON,
            "generation": generation,
        }
    )
    candidates = lexical_candidates(documents, req)
    return session_results_from_candidates(
        req,
        candidates,
        status=degraded_status,
    )


__all__ = ["LEXICAL_DEGRADED_REASON", "search_generation_lexical"]
