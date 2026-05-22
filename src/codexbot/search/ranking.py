"""Dependency-light exact-first search ranking helpers."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .contracts import (
    SearchBackfillDocument,
    SearchHighlight,
    SearchHit,
    SearchRequest,
    SearchResponse,
    SearchRoutingMetadata,
    SearchSessionResult,
    SearchStatusResponse,
)

_QUOTED_RE = re.compile(r'"([^"]+)"')
_TOKEN_RE = re.compile(r"[A-Za-z0-9_./:@+#-]+")
_PATH_RE = re.compile(r"(?:^|[\s`'\"])(?:[A-Za-z]:)?/?[\w.-]+(?:/[\w.@+-]+)+")
_STACK_RE = re.compile(r"\b(?:Traceback|File \"[^\"]+\", line \d+|Error:|Exception)\b")
_TICKET_RE = re.compile(r"\b[A-Z][A-Z0-9]+-\d+\b")
_SYMBOL_RE = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\b")


@dataclass(frozen=True)
class RankedCandidate:
    """Internal normalized row score before session grouping."""

    document: SearchBackfillDocument
    score: float
    lexical_score: float
    semantic_score: float
    metadata_score: float
    snippet: str
    labels: tuple[str, ...]
    highlights: tuple[SearchHighlight, ...]


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


def _query_parts(query: str) -> tuple[list[str], list[str]]:
    quoted = [part.strip() for part in _QUOTED_RE.findall(query) if part.strip()]
    without_quotes = _QUOTED_RE.sub(" ", query)
    tokens = [
        token.strip()
        for token in _TOKEN_RE.findall(without_quotes)
        if token.strip() and len(token.strip()) > 1
    ]
    return quoted, tokens


def _contains_casefold(text: str, needle: str) -> bool:
    return needle.casefold() in text.casefold()


def _metadata_text(routing: SearchRoutingMetadata) -> str:
    values = [
        routing.window_id,
        routing.name or "",
        routing.cwd,
        routing.runtime,
        routing.session_id or "",
        routing.status or "",
        "pinned" if routing.pinned else "",
    ]
    return " ".join(values)


def _recent_cutoff(req: SearchRequest, now: datetime | None) -> datetime | None:
    if req.recent_after:
        return _parse_iso(req.recent_after)
    if req.recent_seconds is not None:
        base = now or datetime.now(UTC)
        if base.tzinfo is None:
            base = base.replace(tzinfo=UTC)
        return base.astimezone(UTC) - timedelta(seconds=req.recent_seconds)
    return None


def document_matches_filters(
    document: SearchBackfillDocument,
    req: SearchRequest,
    *,
    now: datetime | None = None,
) -> bool:
    """Return whether a document satisfies explicit backend filters."""
    routing = document.routing
    provenance = document.provenance
    checks = (
        (req.runtime, routing.runtime),
        (req.cwd, routing.cwd),
        (req.role, provenance.role),
        (req.content_type, provenance.content_type),
        (req.status, routing.status),
        (req.window_id, routing.window_id),
        (req.session_id, routing.session_id or provenance.session_id),
    )
    for expected, actual in checks:
        if expected is not None and actual != expected:
            return False
    if req.pinned is not None and routing.pinned is not req.pinned:
        return False
    cutoff = _recent_cutoff(req, now)
    if cutoff is not None:
        timestamp = _parse_iso(document.timestamp or provenance.timestamp)
        if timestamp is None or timestamp < cutoff:
            return False
    return True


def _technical_labels(query: str, text: str, quoted: list[str], tokens: list[str]) -> set[str]:
    labels: set[str] = set()
    if any(_contains_casefold(text, phrase) for phrase in quoted):
        labels.add("quoted_phrase")
    if _PATH_RE.search(query) or any("/" in token for token in tokens):
        labels.add("path")
    if "$" in query or any(token in {"uv", "git", "pytest", "pnpm", "tmux"} for token in tokens):
        labels.add("command")
    if _STACK_RE.search(query) or _STACK_RE.search(text):
        labels.add("stack")
    if _TICKET_RE.search(query) or _TICKET_RE.search(text):
        labels.add("ticket")
    if _SYMBOL_RE.search(query) or any("." in token for token in tokens):
        labels.add("symbol")
    return labels


def _highlight_terms(
    text: str,
    terms: list[str],
    labels: set[str],
) -> tuple[str, tuple[SearchHighlight, ...]]:
    first: tuple[int, str] | None = None
    lower = text.casefold()
    for term in terms:
        if not term:
            continue
        pos = lower.find(term.casefold())
        if pos >= 0 and (first is None or pos < first[0]):
            first = (pos, term)

    if first is None:
        snippet = text[:500]
        return snippet, ()

    start = max(0, first[0] - 120)
    end = min(len(text), first[0] + len(first[1]) + 220)
    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet

    highlights: list[SearchHighlight] = []
    snippet_lower = snippet.casefold()
    for term in terms:
        if not term:
            continue
        search_from = 0
        while len(highlights) < 32:
            pos = snippet_lower.find(term.casefold(), search_from)
            if pos < 0:
                break
            label = next(iter(labels), "exact")
            highlights.append(
                SearchHighlight(start=pos, end=pos + len(term), label=label)
            )
            search_from = pos + max(1, len(term))

    return snippet[:500], tuple(highlights)


def score_document(
    document: SearchBackfillDocument,
    req: SearchRequest,
    *,
    semantic_score: float = 0.0,
    now: datetime | None = None,
) -> RankedCandidate | None:
    """Score one document with exact lexical protection and capped metadata boost."""
    if not document_matches_filters(document, req, now=now):
        return None

    quoted, tokens = _query_parts(req.query)
    terms = [*quoted, *tokens]
    if not terms:
        return None

    text = document.text
    text_lower = text.casefold()
    matched_terms = [term for term in terms if term.casefold() in text_lower]
    lexical_score = 0.0
    labels = _technical_labels(req.query, text, quoted, tokens)
    if matched_terms:
        unique_matches = {term.casefold() for term in matched_terms}
        lexical_score = min(1.0, len(unique_matches) / max(1, len(terms)))
        phrase_matches = sum(1 for phrase in quoted if _contains_casefold(text, phrase))
        exact_boost = 0.18 if labels else 0.08
        lexical_score = min(
            1.0,
            lexical_score + exact_boost + min(0.14, phrase_matches * 0.07),
        )

    metadata_score = 0.0
    metadata = _metadata_text(document.routing).casefold()
    metadata_matches = {
        term.casefold()
        for term in terms
        if term.casefold() in metadata and term.casefold() not in text_lower
    }
    if metadata_matches:
        metadata_score = min(0.12, 0.04 * len(metadata_matches))
        labels.add("metadata")

    semantic_score = max(0.0, min(1.0, semantic_score))
    if lexical_score <= 0 and semantic_score <= 0:
        return None

    combined = min(
        1.0,
        max(lexical_score, semantic_score * 0.88)
        + metadata_score
        + (0.05 if lexical_score > 0 and semantic_score > 0 else 0.0),
    )
    if lexical_score > 0:
        labels.add("lexical")
    if semantic_score > 0:
        labels.add("semantic")
    if lexical_score > 0 and semantic_score > 0:
        labels.add("hybrid")

    snippet, highlights = _highlight_terms(text, matched_terms, labels)
    return RankedCandidate(
        document=document,
        score=combined,
        lexical_score=lexical_score,
        semantic_score=semantic_score,
        metadata_score=metadata_score,
        snippet=snippet,
        labels=tuple(sorted(labels)),
        highlights=highlights,
    )


def session_results_from_candidates(
    req: SearchRequest,
    candidates: list[RankedCandidate],
    *,
    status: SearchStatusResponse,
) -> SearchResponse:
    """Group ranked candidates by current open window and apply response bounds."""
    grouped: dict[str, list[RankedCandidate]] = {}
    for candidate in sorted(
        candidates,
        key=lambda item: (-item.score, item.document.source_order, item.document.chunk_index),
    ):
        grouped.setdefault(candidate.document.routing.window_id, []).append(candidate)

    sessions: list[SearchSessionResult] = []
    for hits in grouped.values():
        limited = hits[: req.hits_per_session]
        if not limited:
            continue
        best = limited[0].score
        support = min(0.2, sum(hit.score for hit in limited[1:]) * 0.08)
        session_score = min(1.0, best + support)
        search_hits: list[SearchHit] = []
        for candidate in limited:
            outcomes = []
            if "hybrid" in candidate.labels:
                outcomes.append("hybrid")
            else:
                if "lexical" in candidate.labels:
                    outcomes.append("lexical")
                if "semantic" in candidate.labels:
                    outcomes.append("semantic")
            if "metadata" in candidate.labels:
                outcomes.append("metadata")
            search_hits.append(
                SearchHit(
                    identity=candidate.document.identity,
                    provenance=candidate.document.provenance,
                    snippet=candidate.snippet,
                    score=round(candidate.score, 6),
                    outcomes=outcomes,
                    source_order=candidate.document.source_order,
                    timestamp=candidate.document.timestamp
                    or candidate.document.provenance.timestamp,
                    highlights=list(candidate.highlights),
                    match_labels=list(candidate.labels),
                )
            )
        sessions.append(
            SearchSessionResult(
                routing=limited[0].document.routing,
                hits=search_hits,
                hit_count=len(hits),
                score=round(session_score, 6),
            )
        )

    sessions.sort(key=lambda item: (-(item.score or 0.0), item.routing.window_id))
    limited_sessions = sessions[: req.limit]
    total_hits = sum(len(session.hits) for session in limited_sessions)
    return SearchResponse(
        status=status,
        query=req.query,
        results=limited_sessions,
        total_results=total_hits,
        total_sessions=len(limited_sessions),
        limit=req.limit,
        hits_per_session=req.hits_per_session,
        outcome="ok",
    )


def lexical_candidates(
    documents: list[SearchBackfillDocument],
    req: SearchRequest,
    *,
    now: datetime | None = None,
) -> list[RankedCandidate]:
    """Return ranked lexical candidates over a small local document corpus."""
    scored = [
        candidate
        for document in documents
        if (candidate := score_document(document, req, now=now)) is not None
    ]
    if not scored:
        return []

    max_score = max(candidate.score for candidate in scored) or 1.0
    normalized: list[RankedCandidate] = []
    for candidate in scored:
        normalized.append(
            RankedCandidate(
                document=candidate.document,
                score=min(1.0, candidate.score / max_score),
                lexical_score=candidate.lexical_score,
                semantic_score=candidate.semantic_score,
                metadata_score=candidate.metadata_score,
                snippet=candidate.snippet,
                labels=candidate.labels,
                highlights=candidate.highlights,
            )
        )
    return normalized


def bm25_like_term_weight(term: str, *, frequency: int, document_count: int) -> float:
    """Small stdlib BM25-style helper used by tests and future FTS normalization."""
    if frequency <= 0:
        return 0.0
    idf = math.log(1 + (document_count + 1) / 2)
    return min(1.0, (frequency / (frequency + 1.2)) * idf)


__all__ = [
    "RankedCandidate",
    "bm25_like_term_weight",
    "document_matches_filters",
    "lexical_candidates",
    "score_document",
    "session_results_from_candidates",
]
