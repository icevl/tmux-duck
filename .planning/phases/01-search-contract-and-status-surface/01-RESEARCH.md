# Phase 01: Search Contract and Status Surface - Research

**Researched:** 2026-05-21 [VERIFIED: system date]
**Domain:** FastAPI/Pydantic API contract, transcript provenance, and derived local search status [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md]
**Confidence:** HIGH for Phase 1 contract and boundaries; MEDIUM for later worker/index details that are intentionally non-goals here. [CITED: .planning/ROADMAP.md] [CITED: .planning/research/SUMMARY.md]

<user_constraints>
## User Constraints (from CONTEXT.md) [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md]

### Locked Decisions

## Implementation Decisions

### Search Item Identity

- **D-01:** The primary indexed unit is a chunk-level search row tied back to a
  stable transcript message. The contract must support multiple chunks for a
  long assistant/tool message while preserving message-level provenance.
- **D-02:** The contract should include both transcript source offset/cursor and
  parser index/sequence where available. Timestamps are useful display metadata,
  but not sufficient identity or dedupe keys.
- **D-03:** Current tmux `window_id`, window name, cwd, session status, and
  pinned/sort metadata are mutable routing/display metadata. They must not be
  part of indexed row identity.
- **D-04:** Indexed item taxonomy should be runtime-neutral and include runtime,
  role, `content_type`, optional `tool_name`, and source event kind. Do not leak
  raw Codex/Claude record shapes into shared Web API contracts.

### Status/API Shape

- **D-05:** Phase 1 should define both authenticated search status and search
  stub surfaces. The search stub should return structured missing/unavailable or
  empty responses until worker and retrieval phases exist.
- **D-06:** The index status vocabulary should include the full lifecycle enum:
  `missing`, `building`, `partial`, `ready`, `stale`, `degraded`, and
  `unavailable`. Queue/backfill counters may be nullable until later phases
  populate them.
- **D-07:** Normal first-run or not-yet-indexed states should be represented as
  typed `200` responses rather than generic `404` or `503` failures. Transport
  errors remain real errors, but "search exists and is not ready yet" is a
  normal state.
- **D-08:** FastAPI request handlers must maintain a hard boundary: they may
  import lightweight search contracts and client stubs, but must not import
  LanceDB, torch, transformers, sentence-transformers, or embedding/indexing
  implementation modules.

### Derived-State Boundary

- **D-09:** Search-owned runtime state is reserved under
  `$CODEXBOT_DIR/search/`. This namespace will hold derived search status,
  control metadata, queue state, and index files in later phases.
- **D-10:** Search must never write to `monitor_state.json`. Search may read
  transcript/session facts through existing services, but all search watermarks,
  leases, retries, generation metadata, and progress live in search-owned state.
- **D-11:** Rebuildable index generations must carry at least `schema_version`,
  `generation_id`, `created_at`, and an active/inactive marker. Optional model
  and index metadata should be included when available.
- **D-12:** Open-session filtering belongs at query/status time using current
  `SessionManager`/tmux window state. This prevents stale index rows from
  routing users to closed tmux windows.

### the agent's Discretion

No decisions were delegated to the agent. Use established Codi patterns for
Pydantic/FastAPI DTOs, typed frontend API interfaces when needed, and tests.

### Deferred Ideas (OUT OF SCOPE)

None - discussion stayed within Phase 1 scope.
</user_constraints>

<phase_requirements>
## Phase Requirements [CITED: .planning/REQUIREMENTS.md] [CITED: .planning/ROADMAP.md]

| ID | Description | Research Support |
|----|-------------|------------------|
| CORP-03 | Store stable provenance for every indexed item, including runtime, session ID when known, transcript source, transcript offset or index, role/content type, and optional tool identifier. [CITED: .planning/REQUIREMENTS.md] | Use a Pydantic `TranscriptProvenance` plus `SearchRowIdentity` contract sourced from `TranscriptParser` fields and `NewMessage` metadata. [VERIFIED: src/codexbot/transcript_parser.py:24-83] [VERIFIED: src/codexbot/session_monitor.py:47-67] |
| CORP-04 | Use transcript provenance as indexed row identity and current tmux `window_id` only as mutable routing metadata. [CITED: .planning/REQUIREMENTS.md] | Split identity DTOs from `SearchRoutingMetadata`, and test that row/chunk identity does not include `window_id`, cwd, display name, pinned, or sort fields. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md] [VERIFIED: src/codexbot/session.py:65-88] |
| CORP-06 | Treat the search index as derived and rebuildable from transcript/session state, not as a source of truth. [CITED: .planning/REQUIREMENTS.md] | Reserve `$CODEXBOT_DIR/search/` with a generation metadata contract and keep `monitor_state.json` untouched by Phase 1 status/search stubs. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md] [VERIFIED: src/codexbot/utils.py:20-45] |
| OPS-02 | Expose authenticated search and search-status API surfaces without importing embedding models in request handlers. [CITED: .planning/REQUIREMENTS.md] | Add `GET /api/search/status` and `POST /api/search` to `src/codexbot/web/api.py` using `Depends(require_auth)` and lightweight search modules only. [VERIFIED: src/codexbot/web/api.py:391-467] [VERIFIED: src/codexbot/web/api.py:568-603] |
</phase_requirements>

## Summary

Phase 1 should create the stable local contract that later indexing, retrieval, and UI phases consume; it should not create the search worker, LanceDB tables, embedding runtime, backfill, live queue draining, or browser search UI. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md] [CITED: .planning/ROADMAP.md]

The recommended implementation is a lightweight backend module under `src/codexbot/search/` containing Pydantic DTOs, enum/status vocabulary, pure identity helpers, a search-state directory helper, and a stub client/provider that returns typed `missing` or `unavailable` responses. [VERIFIED: codebase inspection] [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md]

The FastAPI integration should add authenticated status/search routes in `src/codexbot/web/api.py` using the existing `require_auth` dependency pattern, and tests should extend `tests/codexbot/test_web_api.py` plus new pure contract tests under `tests/codexbot/test_search_contracts.py`. [VERIFIED: src/codexbot/web/api.py:460-467] [VERIFIED: tests/codexbot/test_web_api.py:64-75]

**Primary recommendation:** Define `src/codexbot/search/contracts.py`, `src/codexbot/search/state.py`, and `src/codexbot/search/client.py`; wire `GET /api/search/status` and `POST /api/search` as authenticated typed stubs; add tests proving provenance identity, status semantics, state-dir isolation, and no heavy imports from request handlers. [VERIFIED: codebase inspection] [CITED: .planning/REQUIREMENTS.md]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Search contract DTOs and provenance identity | API / Backend | Frontend TypeScript types if needed | Phase 1 owns the shared backend API shape and identity semantics before later worker or UI phases consume it. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md] |
| Authenticated status and search stub endpoints | API / Backend | Browser client wrapper | Existing authenticated REST endpoints live in FastAPI and use signed web UI cookies. [VERIFIED: src/codexbot/web/api.py:391-467] [VERIFIED: src/codexbot/web/auth.py:61-141] |
| Mutable routing metadata | API / Backend | Browser / Client display | Current `SessionManager` and tmux window state own `window_id`, cwd, runtime, session ID, pinned, and sort metadata; search identity must not own those fields. [VERIFIED: src/codexbot/session.py:65-88] [VERIFIED: src/codexbot/web/api.py:568-603] |
| Derived search state namespace | Database / Storage | API / Backend helper | Search state is reserved under `$CODEXBOT_DIR/search/`, while `state.json` and `monitor_state.json` remain authoritative non-search stores. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md] [CITED: .planning/codebase/INTEGRATIONS.md] |
| Worker/index/model execution | Out of Phase 1 | Later worker/backend phases | Embedding, LanceDB writes, backfill, queue draining, retrieval, and maintenance are explicitly later-phase work. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md] [CITED: .planning/ROADMAP.md] |

## Project Constraints (from AGENTS.md)

- One Codi session maps to one tmux window, and both Telegram topic and browser window bind to that tmux window. [CITED: AGENTS.md]
- Routing must use tmux window IDs such as `@12`, not names. [CITED: AGENTS.md]
- Telegram has topic-only routing and no non-topic fallback logic. [CITED: AGENTS.md]
- Codex and Claude Code runtime behavior belongs under `src/codexbot/runtimes/`. [CITED: AGENTS.md]
- Message truncation belongs only at the Telegram send layer. [CITED: AGENTS.md]
- Session detection uses `/status` probing plus transcript indexing under `~/.codex/sessions` and `~/.claude/projects`. [CITED: AGENTS.md]
- Per-user message queues preserve Telegram ordering and merge updates safely. [CITED: AGENTS.md]
- The web channel uses FastAPI and a WebSocket event bus shared with Telegram delivery. [CITED: AGENTS.md]
- Default state directory is `~/.codexbot/`, override is `CODEXBOT_DIR`, and legacy `CODEXBOT_*` env names remain in use. [CITED: AGENTS.md]
- Planned session-search implementation should use GSD artifacts rather than bypassing planning. [CITED: AGENTS.md]
- Project-local skill directories `.codex/skills/` and `.agents/skills/` were absent during research. [VERIFIED: project skills discovery]

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.136.1 | Authenticated HTTP API and WebSocket app surface. [VERIFIED: uv.lock] [VERIFIED: PyPI JSON] | Existing routes are built in `src/codexbot/web/api.py`, and FastAPI supports Pydantic request bodies, dependencies, typed response models, and `HTTPException`. [VERIFIED: src/codexbot/web/api.py:43-58] [CITED: Context7 /fastapi/fastapi] |
| Pydantic | 2.13.4 | API DTO validation and JSON schema generation for contracts. [VERIFIED: uv.lock] [VERIFIED: PyPI JSON] | Existing request bodies already use `BaseModel` and `Field`, and Pydantic v2 supports type-hint validation, `Literal`, constrained fields, and `model_json_schema()`. [VERIFIED: src/codexbot/web/api.py:93-132] [CITED: Context7 /pydantic/pydantic] |
| Existing Codi session/transcript modules | current source tree | Provenance, routing metadata, and transcript order facts. [VERIFIED: codebase inspection] | `TranscriptParser` stamps transcript offset/index metadata, `NewMessage` carries normalized live message metadata, and `SessionManager` owns mutable window state. [VERIFIED: src/codexbot/transcript_parser.py:24-83] [VERIFIED: src/codexbot/session_monitor.py:47-67] [VERIFIED: src/codexbot/session.py:65-88] |

### Supporting

| Library/Tool | Version | Purpose | When to Use |
|--------------|---------|---------|-------------|
| pytest | 9.0.3 | Backend unit and API contract tests. [VERIFIED: uv.lock] [VERIFIED: PyPI JSON] | Use for pure identity/status tests and FastAPI `TestClient` route tests. [VERIFIED: pyproject.toml:51-56] [VERIFIED: tests/codexbot/test_web_api.py:64-75] |
| pytest-asyncio | 1.3.0 | Async test support. [VERIFIED: uv.lock] [VERIFIED: PyPI JSON] | Use when testing async provider/client behavior or monitor-derived helpers. [VERIFIED: pyproject.toml:51-56] |
| Ruff | 0.15.13 | Python lint and format check. [VERIFIED: uv.lock] [VERIFIED: PyPI JSON] | Run for all Phase 1 source and tests. [CITED: AGENTS.md] [CITED: .planning/codebase/STACK.md] |
| Pyright | 1.1.409 | Python type checking. [VERIFIED: uv.lock] [VERIFIED: PyPI JSON] | Run after adding Pydantic contracts and route signatures. [CITED: AGENTS.md] [CITED: .planning/codebase/STACK.md] |
| TypeScript API types | 5.9.3 in frontend stack | Optional Web UI client contract typing. [CITED: .planning/codebase/STACK.md] | Add only if Phase 1 updates `web-ui/src/api.ts`; do not build UI rendering in Phase 1. [VERIFIED: web-ui/src/api.ts:1-39] [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Existing FastAPI route module plus lightweight search module | New FastAPI router module mounted from `web/api.py` | A router split would reduce `api.py` growth, but Phase 1 can stay minimal by importing a lightweight router only if the planner wants to avoid adding more handlers to a large file. [CITED: .planning/codebase/CONCERNS.md] [VERIFIED: src/codexbot/web/api.py:391-417] |
| Pydantic DTOs | Plain dataclasses plus manual dicts | Dataclasses avoid FastAPI coupling but lose the existing request-body style, JSON schema support, and validation consistency. [VERIFIED: src/codexbot/web/api.py:93-132] [CITED: Context7 /pydantic/pydantic] |
| Implement real lexical/vector retrieval now | Stub response with typed status | Real retrieval belongs to Phase 4, while Phase 1 only needs honest API status and contract shape. [CITED: .planning/ROADMAP.md] |

**Installation:** No new external package installation is recommended for Phase 1. [VERIFIED: pyproject.toml] [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md]

```bash
# No install command for Phase 1.
```

**Version verification:** Existing versions were checked from `uv.lock`, `uv pip list`, and PyPI JSON for FastAPI 0.136.1, Pydantic 2.13.4, pytest 9.0.3, pytest-asyncio 1.3.0, Ruff 0.15.13, Pyright 1.1.409, and Uvicorn 0.47.0. [VERIFIED: uv.lock] [VERIFIED: env probe] [VERIFIED: PyPI JSON]

## Package Legitimacy Audit

No external package is recommended for installation in Phase 1, so the package legitimacy gate is not required for this phase. [VERIFIED: pyproject.toml] [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md]

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| none | none | n/a | n/a | n/a | n/a | No package install in Phase 1. [VERIFIED: codebase inspection] |

**Packages removed due to slopcheck [SLOP] verdict:** none. [VERIFIED: no new packages recommended]
**Packages flagged as suspicious [SUS]:** none. [VERIFIED: no new packages recommended]

## Architecture Patterns

### System Architecture Diagram

```text
Browser/API caller
  |
  v
FastAPI /api/search/status and /api/search
  | authenticates with existing require_auth
  v
Lightweight search client/provider
  | reads only lightweight contracts and state-dir metadata
  v
Search contracts and status models
  | define row identity, provenance, routing metadata, status lifecycle
  v
$CODEXBOT_DIR/search/ namespace
  | reserved for derived metadata in later phases
  v
Typed response: missing/building/partial/ready/stale/degraded/unavailable

Current SessionManager/tmux state
  |
  +--> request-time open-session routing metadata only

TranscriptParser/NewMessage fields
  |
  +--> provenance contract only, no raw runtime record leak

Non-goals in this phase:
  LanceDB, embeddings, worker process, backfill, queue drain, retrieval, ranking,
  snippets, browser search UI
```

This data flow keeps FastAPI handlers on lightweight contracts and current session metadata while preserving future worker/index ownership for later phases. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md] [VERIFIED: src/codexbot/web/api.py:43-66]

### Recommended Project Structure

```text
src/codexbot/
├── search/
│   ├── __init__.py          # public lightweight exports only
│   ├── contracts.py         # Pydantic DTOs, enums, identity helpers
│   ├── state.py             # search_dir(), generation metadata contract helpers
│   └── client.py            # stub provider returning typed status/search responses
└── web/
    └── api.py               # authenticated /api/search/status and /api/search wiring

tests/codexbot/
├── test_search_contracts.py # pure provenance, identity, enum/schema tests
├── test_search_state.py     # CODEXBOT_DIR/search namespace and monitor isolation tests
└── test_web_api.py          # authenticated route and 200 not-ready response tests
```

This structure matches the Phase 1 constraint that request handlers may import lightweight contracts/stubs but not worker, LanceDB, or embedding modules. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md] [VERIFIED: src/codexbot/web/api.py:43-66]

### Pattern 1: Contract DTOs Are Runtime-Neutral

**What:** Define shared Pydantic DTOs that describe normalized transcript provenance and API results without leaking raw Codex or Claude JSONL record shapes. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md] [VERIFIED: src/codexbot/transcript_parser.py:24-83]

**When to use:** Use this for every API-visible search request, status response, hit, session result, generation, and provenance structure. [CITED: Context7 /fastapi/fastapi] [CITED: Context7 /pydantic/pydantic]

**Example:**
```python
# Source: Context7 /pydantic/pydantic and local API style in src/codexbot/web/api.py
from typing import Literal

from pydantic import BaseModel, Field


SearchIndexState = Literal[
    "missing",
    "building",
    "partial",
    "ready",
    "stale",
    "degraded",
    "unavailable",
]


class TranscriptProvenance(BaseModel):
    runtime: Literal["codex", "claude"] | str
    session_id: str | None = None
    transcript_source: str
    transcript_offset: int | None = Field(default=None, ge=0)
    transcript_index: int | None = Field(default=None, ge=0)
    role: str
    content_type: str
    tool_name: str | None = None
    tool_use_id: str | None = None
    source_event_kind: str
```

### Pattern 2: Identity and Routing Are Separate Models

**What:** Model transcript-derived row/chunk identity separately from current tmux routing metadata. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md] [VERIFIED: src/codexbot/session.py:65-88]

**When to use:** Use identity DTOs for index rows and dedupe, and use routing DTOs only for result opening/display at query time. [CITED: .planning/REQUIREMENTS.md] [VERIFIED: src/codexbot/web/api.py:568-603]

**Example:**
```python
# Source: local requirements and existing WindowState fields
class SearchRowIdentity(BaseModel):
    runtime: str
    transcript_source: str
    transcript_offset: int | None = Field(default=None, ge=0)
    transcript_index: int | None = Field(default=None, ge=0)
    content_type: str
    tool_use_id: str | None = None
    chunk_index: int = Field(default=0, ge=0)


class SearchRoutingMetadata(BaseModel):
    window_id: str
    name: str
    cwd: str
    runtime: str
    session_id: str | None = None
    status: str | None = None
    pinned: bool = False
    sort_order: int | None = None
```

### Pattern 3: Stub API Returns Typed Not-Ready Responses

**What:** Return HTTP 200 with structured status when search exists as a feature but the index/worker/retrieval implementation is absent or not ready. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md]

**When to use:** Use this for first-run missing index, worker not implemented, later building/partial status, and empty stub responses before Phase 4 retrieval. [CITED: .planning/ROADMAP.md]

**Example:**
```python
# Source: FastAPI dependency/response pattern and Phase 1 status decision
@app.get("/api/search/status")
async def search_status(_user: str = Depends(require_auth)) -> dict[str, Any]:
    return search_client.get_status().model_dump(mode="json")


@app.post("/api/search")
async def search(req: SearchRequest, _user: str = Depends(require_auth)) -> dict[str, Any]:
    return search_client.search(req).model_dump(mode="json")
```

### Anti-Patterns to Avoid

- **Putting `window_id` in row identity:** `window_id` is mutable routing metadata and must not become the index dedupe key. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md] [VERIFIED: src/codexbot/session.py:278-310]
- **Importing model/index libraries in `web/api.py`:** Request handlers must not import LanceDB, torch, transformers, sentence-transformers, or worker modules. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md] [VERIFIED: src/codexbot/web/api.py:43-80]
- **Writing search progress to `monitor_state.json`:** Monitor offsets are owned by `MonitorState` and transcript monitoring, not search. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md] [CITED: .planning/codebase/INTEGRATIONS.md]
- **Returning 404/503 for normal missing-index state:** First-run missing or not-yet-ready search status is a typed normal response, not a transport failure. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md]
- **Designing browser search UI in Phase 1:** The Web UI experience and navigation workflow belongs to Phase 5. [CITED: .planning/ROADMAP.md]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| API schema validation | Manual dict validation and ad hoc enum checks | Pydantic `BaseModel`, `Field`, `Literal`/enum fields | Existing Codi routes already use Pydantic, and Pydantic provides validation, serialization, and schema generation. [VERIFIED: src/codexbot/web/api.py:93-132] [CITED: Context7 /pydantic/pydantic] |
| Authentication for search endpoints | New search-specific auth or token scheme | Existing `require_auth` dependency and `Authenticator` | Web UI auth already uses signed cookies, optional TOTP, and route dependencies. [VERIFIED: src/codexbot/web/api.py:404-467] [VERIFIED: src/codexbot/web/auth.py:61-141] |
| Transcript parsing | Raw JSONL parsing inside search API routes | Existing `TranscriptParser` and monitor/session metadata | `TranscriptParser` is shared by live monitor and history paths and already stamps transcript offset/index metadata. [VERIFIED: src/codexbot/transcript_parser.py:1-10] [VERIFIED: src/codexbot/session_monitor.py:311-318] |
| State directory writes | Manual writes to home or `monitor_state.json` | `codexbot_dir() / "search"` plus `atomic_write_json()` when needed | `codexbot_dir()` centralizes `CODEXBOT_DIR`, and atomic JSON writes are the local persistence pattern. [VERIFIED: src/codexbot/utils.py:20-45] |
| API route tests | Real tmux, Telegram, or agent CLI calls | FastAPI `TestClient` with monkeypatched module singletons | Existing Web API tests authenticate once and patch `session_manager`/`tmux_manager` seams. [VERIFIED: tests/codexbot/test_web_api.py:64-75] [CITED: .planning/codebase/TESTING.md] |

**Key insight:** Phase 1 is contract work, so custom infrastructure is riskier than using the repo's existing Pydantic, FastAPI, state-dir, parser, and test patterns. [VERIFIED: codebase inspection] [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md]

## Common Pitfalls

### Pitfall 1: Row Identity Accidentally Depends on Mutable Window Metadata

**What goes wrong:** Results dedupe or route by `window_id`, display name, cwd, pinned, or sort order. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md]

**Why it happens:** Existing Web API session summaries naturally expose those fields together, which makes them easy to copy into identity models. [VERIFIED: src/codexbot/web/api.py:568-603]

**How to avoid:** Put identity fields in `SearchRowIdentity` and routing/display fields in `SearchRoutingMetadata`, then add a test that changing `window_id` does not change row identity. [CITED: .planning/REQUIREMENTS.md]

**Warning signs:** Identity helpers take a `WindowState`, `TmuxWindow`, display name, cwd, pinned value, or sort order as required input. [VERIFIED: src/codexbot/session.py:65-88]

### Pitfall 2: Stub Endpoint Looks Like "No Matches"

**What goes wrong:** The search stub returns `results: []` without an explicit missing/building/unavailable status, so the UI cannot distinguish no matches from not ready. [CITED: .planning/REQUIREMENTS.md]

**Why it happens:** Empty arrays are simple for API stubs but fail the status semantics required by Phase 1. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md]

**How to avoid:** Every `SearchResponse` should include `status`, `query`, and a typed `outcome` such as `not_ready`, `unavailable`, or later `ok`. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md]

**Warning signs:** Tests assert only `status_code == 200` and `results == []`, without checking `status.state`. [VERIFIED: tests/codexbot/test_web_api.py:309-319]

### Pitfall 3: FastAPI Imports Future Heavy Dependencies

**What goes wrong:** `src/codexbot/web/api.py` imports LanceDB, torch, transformers, sentence-transformers, or worker implementation modules. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md]

**Why it happens:** It is tempting to put the stub and future implementation behind the same client import. [ASSUMED]

**How to avoid:** Keep `contracts.py`, `state.py`, and `client.py` dependency-light, and add a static import-boundary test for forbidden module names under `src/codexbot/web/api.py` and `src/codexbot/search/client.py`. [VERIFIED: codebase inspection]

**Warning signs:** `rg -n "lancedb|torch|transformers|sentence_transformers|sentence-transformers" src/codexbot/web src/codexbot/search` finds request-handler imports after Phase 1. [VERIFIED: codebase inspection]

### Pitfall 4: Search State Pollutes Existing Authoritative State

**What goes wrong:** Search status or generation metadata gets written into `state.json` or `monitor_state.json`. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md]

**Why it happens:** `SessionManager` and `MonitorState` already persist nearby session/transcript metadata. [CITED: .planning/codebase/INTEGRATIONS.md]

**How to avoid:** Add a state helper that resolves only `codexbot_dir() / "search"` and add tests that calling status/search stubs does not create or modify `monitor_state.json`. [VERIFIED: src/codexbot/utils.py:20-45] [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md]

**Warning signs:** Phase 1 code imports `MonitorState` or writes to `config.monitor_state_file`. [VERIFIED: src/codexbot/session_monitor.py:106-107]

## Code Examples

Verified patterns from official and local sources:

### Authenticated FastAPI Route Pattern

```python
# Source: src/codexbot/web/api.py and Context7 /fastapi/fastapi
@app.get("/api/search/status")
async def search_status(_user: str = Depends(require_auth)) -> dict[str, Any]:
    status_response = search_client.get_status()
    return status_response.model_dump(mode="json")
```

The existing app defines `require_auth()` inside `create_app()` and applies it with `Depends(require_auth)` on authenticated routes. [VERIFIED: src/codexbot/web/api.py:460-467] [VERIFIED: src/codexbot/web/api.py:568-603]

### Pydantic Status Enum Pattern

```python
# Source: Context7 /pydantic/pydantic and Phase 1 locked status vocabulary
from typing import Literal

from pydantic import BaseModel


SearchIndexState = Literal[
    "missing",
    "building",
    "partial",
    "ready",
    "stale",
    "degraded",
    "unavailable",
]


class SearchStatusResponse(BaseModel):
    state: SearchIndexState
    available: bool
    scope: Literal["open_sessions"] = "open_sessions"
    reason: str | None = None
```

Pydantic validates `Literal` fields and can serialize models to JSON-compatible dicts with `model_dump(mode="json")`. [CITED: Context7 /pydantic/pydantic]

### Search State Directory Helper

```python
# Source: src/codexbot/utils.py
from pathlib import Path

from codexbot.utils import codexbot_dir


def search_dir() -> Path:
    return codexbot_dir() / "search"
```

`codexbot_dir()` resolves `CODEXBOT_DIR` or `~/.codexbot`, and `atomic_write_json()` creates parent directories before replacing JSON files. [VERIFIED: src/codexbot/utils.py:20-45]

## Concrete Files and Symbols for the Planner

| Planner Should Read | Why |
|---------------------|-----|
| `src/codexbot/web/api.py` `create_app()`, `require_auth()`, existing Pydantic request models, and `/api/sessions` routes | Phase 1 search endpoints should follow this route/auth/DTO style. [VERIFIED: src/codexbot/web/api.py:93-132] [VERIFIED: src/codexbot/web/api.py:391-620] |
| `src/codexbot/web/auth.py` `Authenticator`, `AuthConfig`, cookie helpers | Search/status routes must reuse existing Web UI auth. [VERIFIED: src/codexbot/web/auth.py:61-141] |
| `src/codexbot/session.py` `WindowState`, `SessionManager`, `HistorySnapshot`, `get_history_snapshot()` | These are the source for mutable session metadata and transcript history access. [VERIFIED: src/codexbot/session.py:65-180] [VERIFIED: src/codexbot/web/api.py:759-818] |
| `src/codexbot/session_monitor.py` `NewMessage`, listener methods, transcript offset read path | Future live indexing will consume normalized monitor events, and Phase 1 provenance should align with these fields. [VERIFIED: src/codexbot/session_monitor.py:47-67] [VERIFIED: src/codexbot/session_monitor.py:223-240] |
| `src/codexbot/transcript_parser.py` `ParsedEntry`, `TranscriptParser.TRANSCRIPT_OFFSET_KEY`, `_stamp_transcript_order()` | Provenance contract should match parser output rather than raw runtime records. [VERIFIED: src/codexbot/transcript_parser.py:24-83] [VERIFIED: src/codexbot/transcript_parser.py:116-128] |
| `src/codexbot/utils.py` `codexbot_dir()`, `atomic_write_json()` | Search state namespace should use existing local state helpers. [VERIFIED: src/codexbot/utils.py:20-45] |
| `web-ui/src/api.ts` request wrapper and existing `SessionMessage`/`SessionSummary` interfaces | Add only client-side types/methods if Phase 1 chooses to expose typed frontend API functions without UI rendering. [VERIFIED: web-ui/src/api.ts:1-39] [VERIFIED: web-ui/src/api.ts:93-151] |
| `tests/codexbot/test_web_api.py` fixtures and authenticated endpoint tests | Search API tests should reuse `client`, `authed_client`, and monkeypatch patterns. [VERIFIED: tests/codexbot/test_web_api.py:58-75] |
| `tests/codexbot/test_session_monitor.py` offset-stamping tests | Add or reference fixture patterns for transcript offsets. [VERIFIED: tests/codexbot/test_session_monitor.py:61-82] |

## Non-Goals for Phase 1

- Do not implement LanceDB storage, FTS/BM25, vector search, reranking, query execution, snippet generation, or result ranking. [CITED: .planning/ROADMAP.md] [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md]
- Do not install or import torch, transformers, sentence-transformers, LanceDB, FastEmbed, or embedding model packages. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md]
- Do not implement worker process supervision, queue leases, live batching, backfill, retries, dead letters, or generation activation. [CITED: .planning/ROADMAP.md]
- Do not build browser search UI, result rendering, filters, navigation, scroll/highlight behavior, debouncing, or empty-state presentation beyond optional typed API client definitions. [CITED: .planning/ROADMAP.md]
- Do not expand v1 scope to closed/resumable historical sessions, Telegram search, hosted search, cloud embeddings, browser-side transcript indexing, or search-triggered session mutation. [CITED: .planning/REQUIREMENTS.md]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Ad hoc dict API contracts | Pydantic v2 DTOs with typed fields and JSON schema support | Existing project stack as of 2026-05-21 | Use Pydantic for search contracts to match current FastAPI patterns. [VERIFIED: src/codexbot/web/api.py:93-132] [CITED: Context7 /pydantic/pydantic] |
| Timestamp-only transcript positioning | Transcript offset plus parser index metadata | Existing parser/monitor behavior as of 2026-05-21 | Search provenance should include offset/index because timestamps are metadata, not identity. [VERIFIED: src/codexbot/transcript_parser.py:116-128] [VERIFIED: tests/codexbot/test_session_monitor.py:61-82] |
| Source-of-truth search index | Derived, rebuildable search cache | Project decision as of 2026-05-21 | Search state must be isolated under `$CODEXBOT_DIR/search/` and never own transcript/session truth. [CITED: .planning/PROJECT.md] [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md] |

**Deprecated/outdated:** Name-keyed result routing is out of scope and contradicts current Codi routing identity. [CITED: AGENTS.md] [CITED: .planning/REQUIREMENTS.md]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The most likely future accidental heavy-import path is a client module that mixes stubs with later implementation imports. [ASSUMED] | Common Pitfalls | If wrong, the planner may put the import-boundary test in a less useful file; the broader forbidden-import check still catches the requirement. |

## Open Questions (RESOLVED)

1. **Should Phase 1 add `web-ui/src/api.ts` search client methods now?** [VERIFIED: web-ui/src/api.ts:93-151]
   - What we know: Phase 1 must expose authenticated API surfaces, but the Web UI search experience is Phase 5. [CITED: .planning/ROADMAP.md]
   - RESOLVED: Phase 1 remains backend-only: do not add `web-ui/src/api.ts` typed client methods in Phase 1. [CITED: .planning/phases/01-search-contract-and-status-surface/01-03-PLAN.md]
   - Implementation consequence: Add backend API routes and tests only; do not change frontend API client code or require frontend build validation for Phase 1. [CITED: .planning/codebase/STACK.md]

2. **Should `SearchResponse` include an `outcome` field in addition to `status.state`?** [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md]
   - What we know: The contract must distinguish missing/building/unavailable from normal empty results. [CITED: .planning/REQUIREMENTS.md]
   - RESOLVED: `SearchResponse` includes an explicit `outcome` field in addition to `status.state`. [CITED: .planning/phases/01-search-contract-and-status-surface/01-01-PLAN.md] [CITED: .planning/phases/01-search-contract-and-status-surface/01-02-PLAN.md] [CITED: .planning/phases/01-search-contract-and-status-surface/01-03-PLAN.md]
   - Implementation consequence: Tests and provider/API contracts assert `outcome == "not_ready"` for missing-index search responses while `status.state` remains the lifecycle state. [CITED: .planning/phases/01-search-contract-and-status-surface/01-02-PLAN.md] [CITED: .planning/phases/01-search-contract-and-status-surface/01-03-PLAN.md]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python | Backend source/tests | yes | 3.13.12 in repo venv | Project supports Python 3.12+, so this is acceptable for local tests. [VERIFIED: env probe] [VERIFIED: pyproject.toml:1-7] |
| uv | Python environment and checks | yes | 0.10.8 | No fallback needed. [VERIFIED: env probe] [CITED: .planning/codebase/STACK.md] |
| Node.js | Frontend type/build if `web-ui/src/api.ts` changes | yes | 22.17.0 | Skip frontend build if Phase 1 is backend-only. [VERIFIED: env probe] [CITED: .planning/codebase/STACK.md] |
| pnpm | Frontend build if API client types change | yes | 9.15.9 local command; repo pins pnpm 10.25.0 in package metadata | Use installed pnpm unless the planner adds a package-manager alignment task. [VERIFIED: env probe] [CITED: .planning/codebase/STACK.md] |
| tmux | Runtime architecture context only | yes | 3.0a | Phase 1 tests should mock tmux and not require live tmux. [VERIFIED: env probe] [CITED: .planning/codebase/TESTING.md] |

**Missing dependencies with no fallback:** none for Phase 1 contract/API work. [VERIFIED: env probe]

**Missing dependencies with fallback:** none blocking; frontend pnpm version differs from the pinned package-manager metadata, but Phase 1 can be backend-only or use the installed pnpm for build validation. [VERIFIED: env probe] [CITED: .planning/codebase/STACK.md]

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3 with pytest-asyncio 1.3.0. [VERIFIED: uv.lock] [VERIFIED: PyPI JSON] |
| Config file | `pyproject.toml` with `testpaths = ["tests"]` and `asyncio_mode = "auto"`. [VERIFIED: pyproject.toml:51-56] |
| Quick run command | `uv run pytest tests/codexbot/test_search_contracts.py tests/codexbot/test_search_state.py tests/codexbot/test_web_api.py -q` [CITED: .planning/codebase/TESTING.md] |
| Full suite command | `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run pyright src/codexbot/ && uv run pytest -q` [CITED: AGENTS.md] [CITED: .planning/codebase/STACK.md] |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| CORP-03 | Provenance DTO accepts runtime, session ID, transcript source, offset/index, role/content type, and optional tool fields. [CITED: .planning/REQUIREMENTS.md] | unit | `uv run pytest tests/codexbot/test_search_contracts.py::test_provenance_contract_contains_required_fields -q` | no - Wave 0 |
| CORP-04 | Row identity excludes `window_id` and mutable display/routing metadata while routing metadata remains available separately. [CITED: .planning/REQUIREMENTS.md] | unit | `uv run pytest tests/codexbot/test_search_contracts.py::test_row_identity_excludes_mutable_window_metadata -q` | no - Wave 0 |
| CORP-06 | Search state helper resolves `$CODEXBOT_DIR/search/` and status/search stubs do not touch `monitor_state.json`. [CITED: .planning/REQUIREMENTS.md] | unit | `uv run pytest tests/codexbot/test_search_state.py::test_search_state_does_not_modify_monitor_state -q` | no - Wave 0 |
| OPS-02 | Authenticated search/status endpoints return typed 200 missing/unavailable responses and request handlers do not import heavy model/index packages. [CITED: .planning/REQUIREMENTS.md] | API + static import test | `uv run pytest tests/codexbot/test_web_api.py::test_search_status_requires_auth tests/codexbot/test_web_api.py::test_search_stub_returns_typed_not_ready tests/codexbot/test_search_contracts.py::test_web_search_boundary_has_no_heavy_imports -q` | partial - add tests |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/codexbot/test_search_contracts.py tests/codexbot/test_search_state.py tests/codexbot/test_web_api.py -q` [CITED: .planning/codebase/TESTING.md]
- **Per wave merge:** `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run pyright src/codexbot/ && uv run pytest -q` [CITED: AGENTS.md]
- **Phase gate:** Full suite green plus `pnpm --dir web-ui build` if `web-ui/src/api.ts` changes. [CITED: AGENTS.md] [CITED: .planning/codebase/STACK.md]

### Wave 0 Gaps

- [ ] `tests/codexbot/test_search_contracts.py` - covers CORP-03, CORP-04, and OPS-02 import boundary. [VERIFIED: tests directory inspection]
- [ ] `tests/codexbot/test_search_state.py` - covers CORP-06 state namespace and monitor-state isolation. [VERIFIED: tests directory inspection]
- [ ] `tests/codexbot/test_web_api.py` additions - cover authenticated `/api/search/status` and `/api/search` stubs. [VERIFIED: tests/codexbot/test_web_api.py:58-75]
- [ ] Optional `web-ui/src/api.ts` type validation - only if frontend API client methods are added. [VERIFIED: web-ui/src/api.ts:93-151]

## Security Domain

Security enforcement is enabled because `.planning/config.json` does not set `security_enforcement` to `false`. [VERIFIED: .planning/config.json]

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | yes | Reuse existing Web UI password/TOTP cookie auth and require `Depends(require_auth)` on search routes. [VERIFIED: src/codexbot/web/api.py:404-467] [CITED: OWASP ASVS Developer Guide] |
| V3 Session Management | yes | Reuse signed cookie verification and do not introduce search-specific sessions. [VERIFIED: src/codexbot/web/auth.py:61-141] [CITED: OWASP ASVS Developer Guide] |
| V4 Access Control | yes | Keep search behind the same authenticated local admin Web UI surface; do not expose unauthenticated transcript metadata. [CITED: .planning/codebase/CONCERNS.md] [CITED: OWASP ASVS Developer Guide] |
| V5 Input Validation | yes | Use Pydantic request models with length/limit constraints for query, filters, and pagination. [CITED: Context7 /pydantic/pydantic] [CITED: OWASP ASVS Developer Guide] |
| V6 Stored Cryptography | no new cryptography | Do not add cryptographic primitives for Phase 1; reuse existing signed-cookie auth. [VERIFIED: src/codexbot/web/auth.py:61-141] [CITED: OWASP ASVS Developer Guide] |

### Known Threat Patterns for Phase 1 Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Unauthenticated transcript/status discovery | Information Disclosure | Apply `Depends(require_auth)` to both search endpoints and test 401 without cookie. [VERIFIED: src/codexbot/web/api.py:460-467] [VERIFIED: tests/codexbot/test_web_api.py:102-104] |
| Oversized search query or filter payload | Denial of Service | Add Pydantic `Field` limits for query length and result limits. [CITED: Context7 /pydantic/pydantic] |
| Status response leaking local secrets or raw transcript paths unnecessarily | Information Disclosure | Return scope/status/reason/counters, but avoid secret env values and avoid exposing full local paths unless a future UI requirement needs them. [CITED: .planning/codebase/CONCERNS.md] [ASSUMED] |
| Search feature mutating authoritative session/monitor state | Tampering | Restrict Phase 1 writes to `$CODEXBOT_DIR/search/` and test `monitor_state.json` remains unchanged. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md] |
| Heavy model imports in request handlers | Denial of Service | Static import-boundary test against LanceDB/torch/transformers/sentence-transformers imports in web request modules. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md] |

## Sources

### Primary (HIGH confidence)

- `.planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md` - locked Phase 1 decisions, boundaries, status vocabulary, identity rules, and code context. [CITED]
- `.planning/REQUIREMENTS.md` - Phase requirements CORP-03, CORP-04, CORP-06, OPS-02 and non-goals. [CITED]
- `.planning/ROADMAP.md` - Phase 1 goal, success criteria, and later-phase boundaries. [CITED]
- `.planning/PROJECT.md` - project scope, local-first constraints, and key search decisions. [CITED]
- `AGENTS.md` - project commands, routing constraints, runtime constraints, and state/env rules. [CITED]
- `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STACK.md`, `.planning/codebase/INTEGRATIONS.md`, `.planning/codebase/TESTING.md`, `.planning/codebase/CONCERNS.md` - existing architecture, stack, integrations, validation patterns, and risks. [CITED]
- Local code inspection of `src/codexbot/web/api.py`, `src/codexbot/web/auth.py`, `src/codexbot/session.py`, `src/codexbot/session_monitor.py`, `src/codexbot/transcript_parser.py`, `src/codexbot/utils.py`, `web-ui/src/api.ts`, and tests. [VERIFIED: codebase inspection]
- Context7 `/fastapi/fastapi` - FastAPI request body, dependency, response model, and `HTTPException` patterns. [CITED: https://github.com/fastapi/fastapi/blob/master/docs/en/docs/index.md]
- Context7 `/pydantic/pydantic` - Pydantic v2 `BaseModel`, `Field`, `Literal`, `model_dump()`, and `model_json_schema()` patterns. [CITED: https://github.com/pydantic/pydantic/blob/main/docs/why.md]
- PyPI JSON registry checks for FastAPI, Pydantic, pytest, pytest-asyncio, Ruff, Pyright, and Uvicorn versions and upload times. [VERIFIED: PyPI JSON]
- OWASP Developer Guide ASVS page for V2 Authentication, V3 Session Management, V4 Access Control, V5 Validation/Sanitization/Encoding, and V6 Stored Cryptography category mapping. [CITED: https://devguide.owasp.org/en/06-verification/01-guides/03-asvs/]

### Secondary (MEDIUM confidence)

- `.planning/research/SUMMARY.md` - roadmap-level stack and pitfall synthesis; Phase 1 uses only contract/status implications from this summary. [CITED]

### Tertiary (LOW confidence)

- Assumption A1 about likely future heavy-import mixing risk. [ASSUMED]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - Phase 1 uses existing FastAPI/Pydantic/pytest stack verified in source, lockfile, Context7, and PyPI. [VERIFIED: codebase inspection] [VERIFIED: PyPI JSON] [CITED: Context7 /fastapi/fastapi] [CITED: Context7 /pydantic/pydantic]
- Architecture: HIGH - Phase boundaries and ownership are locked by CONTEXT.md, ROADMAP.md, AGENTS.md, and existing code seams. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md] [CITED: .planning/ROADMAP.md] [CITED: AGENTS.md]
- Pitfalls: HIGH for identity/status/import/state pitfalls because they directly map to locked decisions; MEDIUM for assumed future import-mixing risk. [CITED: .planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md] [ASSUMED]

**Research date:** 2026-05-21 [VERIFIED: system date]
**Valid until:** 2026-06-20 for Phase 1 contract patterns; re-check PyPI/Context7 if package or FastAPI/Pydantic APIs are changed before implementation. [ASSUMED]
