# Phase 1: Search Contract and Status Surface - Context

**Gathered:** 2026-05-21
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase establishes the local search contract before indexing, worker,
retrieval, or Web UI search work begins. It should define stable provenance and
row identity for future indexed items, authenticated search/status API DTOs, and
the boundary between search-owned derived state and existing authoritative Codi
state.

This phase should not implement LanceDB retrieval, embedding, live queue
draining, backfill, or the browser search experience. Those are later phases.

</domain>

<decisions>
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

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project And Scope

- `.planning/PROJECT.md` - Project goal, constraints, key decisions, and v1
  boundaries for open-session local hybrid search.
- `.planning/REQUIREMENTS.md` - Phase 1 mapped requirements: `CORP-03`,
  `CORP-04`, `CORP-06`, and `OPS-02`.
- `.planning/ROADMAP.md` - Phase 1 goal, success criteria, dependencies, and
  phase ordering.
- `.planning/STATE.md` - Current project position and known validation concerns.

### Research

- `.planning/research/SUMMARY.md` - Search stack, phase implications, pitfalls,
  and roadmap rationale for the local worker/index architecture.

### Codebase Maps

- `.planning/codebase/STACK.md` - Existing backend/frontend/tooling stack and
  verification commands.
- `.planning/codebase/ARCHITECTURE.md` - Existing session, transcript, event,
  state, and Web API architecture.
- `.planning/codebase/INTEGRATIONS.md` - Runtime transcript sources, local state
  files, Web UI auth, and external integration boundaries.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `src/codexbot/web/api.py`: Existing authenticated FastAPI route patterns,
  Pydantic request/response models, `HTTPException` usage, and app factory.
- `src/codexbot/web/auth.py`: Existing web auth and WebSocket origin checks.
  Search/status routes should reuse the same authenticated Web UI surface.
- `src/codexbot/session.py`: `SessionManager` and `WindowState` are the source
  for current tmux window routing metadata, cwd, runtime, pinned state, and
  session IDs.
- `src/codexbot/session_monitor.py`: Existing transcript monitor emits normalized
  message events and persists delivery offsets outside search.
- `src/codexbot/transcript_parser.py`: Shared runtime transcript normalization
  layer. Search contracts should align with this parser rather than introduce
  independent raw JSONL parsing.
- `src/codexbot/utils.py`: Existing state-dir helpers and atomic JSON patterns
  are relevant for reserving `$CODEXBOT_DIR/search/` and future metadata files.

### Established Patterns

- Routing identity is tmux `window_id`; display names, cwd, runtime session IDs,
  and topic labels are metadata.
- Transcript JSONL files are authoritative for user/assistant/tool history.
  History and live updates must share parser behavior.
- Backend modules are async-first, and blocking tmux work is isolated with
  `asyncio.to_thread()`.
- Web and Telegram share session/tmux/runtime state; new search state must not
  become a web-only source of truth.
- Message truncation belongs only in the Telegram send layer, not in local
  transcript/search ingestion.

### Integration Points

- Add lightweight search contract code under a focused backend module such as
  `src/codexbot/search/` or equivalent, keeping heavy worker dependencies out
  of web route imports.
- Wire authenticated status/search-stub routes into `src/codexbot/web/api.py`
  through lightweight DTO/client abstractions only.
- Use `SessionManager` at request time to derive current open-session metadata
  and filter or mark stale search results.
- Reserve search state under `$CODEXBOT_DIR/search/`; do not write search
  progress into `state.json` or `monitor_state.json`.

</code_context>

<specifics>
## Specific Ideas

No external examples were introduced during discussion. The specific locked
shape is: chunk rows backed by transcript message provenance, full lifecycle
status enum, typed non-error first-run responses, hard model-import boundary in
FastAPI, and search-owned state under `$CODEXBOT_DIR/search/`.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within Phase 1 scope.

</deferred>

---

*Phase: 1-Search Contract and Status Surface*
*Context gathered: 2026-05-21*
