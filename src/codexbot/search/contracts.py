"""Lightweight search contract DTOs shared by API and future worker code."""

from __future__ import annotations

from typing import Literal, TypeAlias

from pydantic import BaseModel, Field


SEARCH_INDEX_STATES = (
    "missing",
    "building",
    "partial",
    "ready",
    "stale",
    "degraded",
    "unavailable",
)

SearchIndexState: TypeAlias = Literal[
    "missing",
    "building",
    "partial",
    "ready",
    "stale",
    "degraded",
    "unavailable",
]
SearchOutcome: TypeAlias = Literal["lexical", "semantic", "metadata", "hybrid"]
SearchResponseOutcome: TypeAlias = Literal["ok", "not_ready", "unavailable"]
SearchWorkerStatusState: TypeAlias = Literal[
    "idle",
    "running",
    "completed",
    "failed",
]


class TranscriptProvenance(BaseModel):
    """Runtime-neutral transcript coordinates for an indexed source message."""

    runtime: str = Field(min_length=1, max_length=64)
    session_id: str | None = Field(default=None, min_length=1, max_length=255)
    transcript_source: str = Field(min_length=1, max_length=4096)
    transcript_offset: int | None = Field(default=None, ge=0)
    transcript_index: int | None = Field(default=None, ge=0)
    role: str = Field(min_length=1, max_length=64)
    content_type: str = Field(min_length=1, max_length=64)
    tool_name: str | None = Field(default=None, min_length=1, max_length=255)
    tool_use_id: str | None = Field(default=None, min_length=1, max_length=255)
    source_event_kind: str = Field(min_length=1, max_length=128)
    timestamp: str | None = Field(default=None, min_length=1, max_length=128)


class SearchRowIdentity(BaseModel):
    """Stable chunk-row identity derived from transcript provenance."""

    runtime: str = Field(min_length=1, max_length=64)
    transcript_source: str = Field(min_length=1, max_length=4096)
    transcript_offset: int | None = Field(default=None, ge=0)
    transcript_index: int | None = Field(default=None, ge=0)
    role: str = Field(min_length=1, max_length=64)
    content_type: str = Field(min_length=1, max_length=64)
    tool_use_id: str | None = Field(default=None, min_length=1, max_length=255)
    chunk_index: int = Field(ge=0)

    @classmethod
    def from_provenance(
        cls, provenance: TranscriptProvenance, *, chunk_index: int
    ) -> "SearchRowIdentity":
        """Build a chunk identity without mutable tmux routing metadata."""
        return cls(
            runtime=provenance.runtime,
            transcript_source=provenance.transcript_source,
            transcript_offset=provenance.transcript_offset,
            transcript_index=provenance.transcript_index,
            role=provenance.role,
            content_type=provenance.content_type,
            tool_use_id=provenance.tool_use_id,
            chunk_index=chunk_index,
        )


class SearchRoutingMetadata(BaseModel):
    """Mutable request-time routing and display metadata for an open session."""

    window_id: str = Field(min_length=1, max_length=64)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    cwd: str = Field(min_length=1, max_length=4096)
    runtime: str = Field(min_length=1, max_length=64)
    session_id: str | None = Field(default=None, min_length=1, max_length=255)
    status: str | None = Field(default=None, min_length=1, max_length=64)
    pinned: bool = False
    sort_order: int | None = Field(default=None, ge=0)


class SearchGenerationMetadata(BaseModel):
    """Rebuildable search index generation metadata."""

    schema_version: int = Field(ge=1)
    generation_id: str = Field(min_length=1, max_length=255)
    created_at: str = Field(min_length=1, max_length=128)
    active: bool


class SearchCounters(BaseModel):
    """Nullable lifecycle counters populated by later state/worker phases."""

    open_sessions: int = Field(default=0, ge=0)
    indexed_sessions: int = Field(default=0, ge=0)
    indexed_chunks: int = Field(default=0, ge=0)
    queued_items: int = Field(default=0, ge=0)
    failed_items: int = Field(default=0, ge=0)


class SearchWorkerStatus(BaseModel):
    """Search worker heartbeat and current task state."""

    status: SearchWorkerStatusState
    current_task: str | None = Field(default=None, min_length=1, max_length=128)
    heartbeat_at: str = Field(min_length=1, max_length=128)
    recent_error: str | None = Field(default=None, max_length=2000)
    counters: SearchCounters | None = None


class SearchBackfillDocument(BaseModel):
    """One parser-backed chunk document produced by open-session backfill."""

    identity: SearchRowIdentity
    provenance: TranscriptProvenance
    routing: SearchRoutingMetadata
    text: str = Field(min_length=1, max_length=50000)
    timestamp: str | None = Field(default=None, min_length=1, max_length=128)
    source_order: int = Field(ge=0)
    chunk_index: int = Field(ge=0)
    chunk_count: int = Field(ge=1)


class SearchBackfillManifest(BaseModel):
    """Inactive generation manifest written beside derived backfill documents."""

    schema_version: int = Field(default=1, ge=1)
    generation: SearchGenerationMetadata
    counters: SearchCounters
    document_count: int = Field(ge=0)
    errors: list[str] = Field(default_factory=list, max_length=1000)


class SearchStatusResponse(BaseModel):
    """Search readiness response safe for request-path status surfaces."""

    state: SearchIndexState
    available: bool
    scope: Literal["open_sessions"] = "open_sessions"
    reason: str | None = Field(default=None, max_length=500)
    counters: SearchCounters | None = None
    generation: SearchGenerationMetadata | None = None


class SearchHit(BaseModel):
    """One matching indexed chunk within a session result."""

    identity: SearchRowIdentity
    provenance: TranscriptProvenance
    snippet: str = Field(max_length=2000)
    score: float | None = None
    outcomes: list[SearchOutcome] = Field(default_factory=list, max_length=8)


class SearchSessionResult(BaseModel):
    """Search hits grouped under the current routeable open session."""

    routing: SearchRoutingMetadata
    hits: list[SearchHit] = Field(default_factory=list, max_length=10)
    hit_count: int = Field(default=0, ge=0)
    score: float | None = None


class SearchRequest(BaseModel):
    """Bounded user search request."""

    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=10, ge=1, le=50)
    hits_per_session: int = Field(default=3, ge=1, le=10)
    runtime: str | None = Field(default=None, min_length=1, max_length=64)
    cwd: str | None = Field(default=None, min_length=1, max_length=4096)
    role: str | None = Field(default=None, min_length=1, max_length=64)
    content_type: str | None = Field(default=None, min_length=1, max_length=64)
    status: str | None = Field(default=None, min_length=1, max_length=64)


class SearchResponse(BaseModel):
    """Grouped search response with explicit status semantics."""

    status: SearchStatusResponse
    query: str = Field(min_length=1, max_length=500)
    results: list[SearchSessionResult] = Field(default_factory=list, max_length=50)
    total_results: int = Field(default=0, ge=0)
    total_sessions: int = Field(default=0, ge=0)
    limit: int = Field(ge=1, le=50)
    hits_per_session: int = Field(ge=1, le=10)
    outcome: SearchResponseOutcome


__all__ = [
    "SEARCH_INDEX_STATES",
    "SearchBackfillDocument",
    "SearchBackfillManifest",
    "SearchCounters",
    "SearchGenerationMetadata",
    "SearchHit",
    "SearchIndexState",
    "SearchOutcome",
    "SearchRequest",
    "SearchResponse",
    "SearchResponseOutcome",
    "SearchRoutingMetadata",
    "SearchRowIdentity",
    "SearchSessionResult",
    "SearchStatusResponse",
    "SearchWorkerStatus",
    "SearchWorkerStatusState",
    "TranscriptProvenance",
]
