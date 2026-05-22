"""Dependency-light search retrieval providers."""

from __future__ import annotations

from .contracts import (
    SearchGenerationMetadata,
    SearchRequest,
    SearchResponse,
    SearchStatusResponse,
)
from .index import row_id_for_identity, semantic_scores_for_query
from .live import filter_stale_documents, read_generation_documents
from .queue import sanitize_error
from .ranking import (
    RankedCandidate,
    lexical_candidates,
    score_document,
    session_results_from_candidates,
)


LEXICAL_DEGRADED_REASON = "semantic index is unavailable; using lexical retrieval"


def search_generation_lexical(
    req: SearchRequest,
    *,
    generation: SearchGenerationMetadata,
    status: SearchStatusResponse,
) -> SearchResponse:
    """Return bounded lexical results over active generation documents."""
    documents = filter_stale_documents(
        read_generation_documents(generation.generation_id)
    )
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


def _hybrid_candidates(
    req: SearchRequest,
    *,
    generation: SearchGenerationMetadata,
) -> list[RankedCandidate]:
    documents = filter_stale_documents(
        read_generation_documents(generation.generation_id)
    )
    semantic_scores = semantic_scores_for_query(
        generation.generation_id,
        query=req.query,
        limit=max(req.limit * req.hits_per_session * 2, 10),
    )
    candidates = []
    for document in documents:
        row_id = row_id_for_identity(document.identity)
        candidate = score_document(
            document,
            req,
            semantic_score=semantic_scores.get(row_id, 0.0),
        )
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def search_generation(
    req: SearchRequest,
    *,
    generation: SearchGenerationMetadata,
    status: SearchStatusResponse,
) -> SearchResponse:
    """Return hybrid results when index metadata is ready, else lexical degraded."""
    if status.index is None:
        return search_generation_lexical(req, generation=generation, status=status)

    try:
        candidates = _hybrid_candidates(req, generation=generation)
    except Exception as exc:
        fallback_status = status.model_copy(
            update={
                "state": "degraded",
                "available": True,
                "reason": f"semantic retrieval degraded: {sanitize_error(exc)}",
            }
        )
        return search_generation_lexical(
            req,
            generation=generation,
            status=fallback_status,
        )

    return session_results_from_candidates(req, candidates, status=status)


__all__ = ["LEXICAL_DEGRADED_REASON", "search_generation", "search_generation_lexical"]
