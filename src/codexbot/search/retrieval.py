"""Dependency-light search retrieval providers."""

from __future__ import annotations

import logging
import os
import re
from time import perf_counter

from .contracts import (
    SearchBackfillDocument,
    SearchGenerationMetadata,
    SearchRequest,
    SearchResponse,
    SearchStatusResponse,
)
from .index import (
    full_text_candidates_for_query,
    row_id_for_identity,
    semantic_candidates_for_query,
)
from .live import read_generation_documents
from .queue import list_stale_sources, sanitize_error
from .ranking import (
    RankedCandidate,
    lexical_candidates,
    score_document,
    session_results_from_candidates,
)


LEXICAL_DEGRADED_REASON = "semantic index is unavailable; using lexical retrieval"
SEMANTIC_MIN_CANDIDATES = 100
SEMANTIC_MAX_CANDIDATES = 500
LEXICAL_MIN_CANDIDATES = 200
LEXICAL_MAX_CANDIDATES = 500
SLOW_SEARCH_LOG_SECONDS = float(os.getenv("CODEXBOT_SEARCH_SLOW_LOG_SECONDS", "1.0"))

logger = logging.getLogger(__name__)


def _candidate_limit(
    req: SearchRequest,
    *,
    multiplier: int,
    minimum: int,
    maximum: int,
) -> int:
    requested = req.limit * req.hits_per_session * multiplier
    return min(maximum, max(minimum, requested))


def _active_documents(generation_id: str) -> list[SearchBackfillDocument]:
    stale_sources = list_stale_sources()
    documents = read_generation_documents(generation_id)
    if not stale_sources:
        return documents
    return [
        document
        for document in documents
        if document.provenance.transcript_source not in stale_sources
    ]


def _keep_better_candidate(
    existing: RankedCandidate | None,
    incoming: RankedCandidate,
) -> RankedCandidate:
    if existing is None:
        return incoming
    if incoming.score > existing.score:
        return incoming
    if (
        incoming.score == existing.score
        and incoming.lexical_score > existing.lexical_score
    ):
        return incoming
    return existing


def _log_timing(
    *,
    mode: str,
    req: SearchRequest,
    generation: SearchGenerationMetadata,
    timings: dict[str, float],
    document_count: int,
    candidate_count: int,
) -> None:
    total = timings.get("total", 0.0)
    if total < SLOW_SEARCH_LOG_SECONDS and not logger.isEnabledFor(logging.DEBUG):
        return
    log = logger.info if total >= SLOW_SEARCH_LOG_SECONDS else logger.debug
    log(
        "search %s query completed in %.3fs generation=%s query_length=%s "
        "documents=%s candidates=%s timings=%s",
        mode,
        total,
        generation.generation_id,
        len(req.query),
        document_count,
        candidate_count,
        {key: round(value, 3) for key, value in timings.items()},
    )


# Single-word queries against a multilingual embedding model surface
# "topic-adjacent" docs (a query like "фикс" pulls in every code-editing
# message because they all cluster together in vector space). For <=2-token
# queries the lexical path is more accurate; semantic activates only once
# the query has enough words to disambiguate intent.
_TOKEN_GATE_RE = re.compile(r"[\w./:@+#-]+")
_MIN_TOKENS_FOR_SEMANTIC = 3


def search_generation_lexical(
    req: SearchRequest,
    *,
    generation: SearchGenerationMetadata,
    status: SearchStatusResponse,
) -> SearchResponse:
    """Return bounded lexical results over active generation documents."""
    started = perf_counter()
    documents_started = perf_counter()
    documents = _active_documents(generation.generation_id)
    timings = {"documents": perf_counter() - documents_started}
    degraded_status = status.model_copy(
        update={
            "state": "degraded",
            "available": True,
            "reason": status.reason or LEXICAL_DEGRADED_REASON,
            "generation": generation,
        }
    )
    lexical_started = perf_counter()
    candidates = lexical_candidates(
        documents,
        req,
        limit=_candidate_limit(
            req,
            multiplier=12,
            minimum=LEXICAL_MIN_CANDIDATES,
            maximum=LEXICAL_MAX_CANDIDATES,
        ),
    )
    timings["lexical"] = perf_counter() - lexical_started
    rank_started = perf_counter()
    response = session_results_from_candidates(
        req,
        candidates,
        status=degraded_status,
    )
    timings["rank_group"] = perf_counter() - rank_started
    timings["total"] = perf_counter() - started
    _log_timing(
        mode="lexical",
        req=req,
        generation=generation,
        timings=timings,
        document_count=len(documents),
        candidate_count=len(candidates),
    )
    return response


def _hybrid_candidates(
    req: SearchRequest,
    *,
    generation: SearchGenerationMetadata,
    timings: dict[str, float],
) -> list[RankedCandidate]:
    semantic_limit = _candidate_limit(
        req,
        multiplier=10,
        minimum=SEMANTIC_MIN_CANDIDATES,
        maximum=SEMANTIC_MAX_CANDIDATES,
    )
    lexical_limit = _candidate_limit(
        req,
        multiplier=12,
        minimum=LEXICAL_MIN_CANDIDATES,
        maximum=LEXICAL_MAX_CANDIDATES,
    )

    stale_sources = list_stale_sources()
    semantic_started = perf_counter()
    token_count = len(_TOKEN_GATE_RE.findall(req.query))
    if token_count >= _MIN_TOKENS_FOR_SEMANTIC:
        semantic_candidates = semantic_candidates_for_query(
            generation.generation_id,
            query=req.query,
            limit=semantic_limit,
        )
    else:
        semantic_candidates = []
    timings["semantic"] = perf_counter() - semantic_started
    candidates_by_row_id: dict[str, RankedCandidate] = {}
    semantic_scores: dict[str, float] = {}
    for semantic_candidate in semantic_candidates:
        document = semantic_candidate.document
        if document.provenance.transcript_source in stale_sources:
            continue
        semantic_scores[semantic_candidate.row_id] = semantic_candidate.score
        candidate = score_document(
            document,
            req,
            semantic_score=semantic_candidate.score,
        )
        if candidate is None:
            continue
        candidates_by_row_id[semantic_candidate.row_id] = _keep_better_candidate(
            candidates_by_row_id.get(semantic_candidate.row_id),
            candidate,
        )

    lexical_started = perf_counter()
    document_count = 0
    try:
        lexical_index_candidates = full_text_candidates_for_query(
            generation.generation_id,
            query=req.query,
            limit=lexical_limit,
        )
    except Exception as exc:
        logger.debug("search FTS candidate retrieval degraded: %s", sanitize_error(exc))
        documents_started = perf_counter()
        documents = read_generation_documents(generation.generation_id)
        if stale_sources:
            documents = [
                document
                for document in documents
                if document.provenance.transcript_source not in stale_sources
            ]
        timings["documents"] = perf_counter() - documents_started
        document_count = len(documents)
        lexical = lexical_candidates(documents, req, limit=lexical_limit)
    else:
        lexical = []
        document_count = len(lexical_index_candidates)
        for lexical_index_candidate in lexical_index_candidates:
            document = lexical_index_candidate.document
            if document.provenance.transcript_source in stale_sources:
                continue
            candidate = score_document(
                document,
                req,
                semantic_score=semantic_scores.get(
                    lexical_index_candidate.row_id,
                    0.0,
                ),
            )
            if candidate is not None:
                lexical.append(candidate)
    timings["lexical"] = perf_counter() - lexical_started
    for lexical_candidate in lexical:
        row_id = row_id_for_identity(lexical_candidate.document.identity)
        semantic_score = semantic_scores.get(row_id, 0.0)
        candidate = (
            score_document(
                lexical_candidate.document,
                req,
                semantic_score=semantic_score,
            )
            if semantic_score > 0
            else lexical_candidate
        )
        if candidate is None:
            continue
        candidates_by_row_id[row_id] = _keep_better_candidate(
            candidates_by_row_id.get(row_id),
            candidate,
        )
    timings["document_count"] = float(document_count)
    candidates = list(candidates_by_row_id.values())

    # When any candidate has an exact lexical hit, drop pure-semantic ones.
    # Otherwise topic-adjacent noise (tool-call summaries, unrelated code
    # reads) outranks the literal phrase the user typed because the embed
    # model groups them by surrounding conversation context, not by the
    # snippet text itself. "I remember seeing this phrase" queries should
    # return that phrase, not its neighbors.
    if any(c.lexical_score > 0 for c in candidates):
        candidates = [c for c in candidates if c.lexical_score > 0]
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

    started = perf_counter()
    timings: dict[str, float] = {}
    try:
        candidates = _hybrid_candidates(req, generation=generation, timings=timings)
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

    rank_started = perf_counter()
    response = session_results_from_candidates(req, candidates, status=status)
    timings["rank_group"] = perf_counter() - rank_started
    timings["total"] = perf_counter() - started
    _log_timing(
        mode="hybrid",
        req=req,
        generation=generation,
        timings=timings,
        document_count=int(timings.pop("document_count", 0.0)),
        candidate_count=len(candidates),
    )
    return response


__all__ = ["LEXICAL_DEGRADED_REASON", "search_generation", "search_generation_lexical"]
