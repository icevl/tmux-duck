# Phase 3: Live Queue and Convergence - Context

**Gathered:** 2026-05-22
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase adds durable live indexing and convergence for currently open
tmux-backed Codex and Claude sessions. New transcript activity should be
persisted into search-owned queue state, drained in bounded batches, and
converged into the derived search generation while users continue working.

The phase does not implement semantic retrieval, LanceDB/Faiss query ranking,
the browser search experience, or historical transcript search outside the
open-session v1 corpus. It also does not move search state into existing
session, monitor, Telegram, or Web UI state files.

</domain>

<decisions>
## Implementation Decisions

### Queue Capture Timing

- **D-01:** Live indexing should queue useful parsed transcript entries as the
  atomic work item. It should not wait for whole completed turns before
  capturing indexable text.
- **D-02:** Queue creation should attach to `SessionMonitor` transcript events
  and persist search queue rows from that listener path without making Web UI
  or Telegram message delivery depend on slow indexing work.
- **D-03:** If queue persistence or indexing is slow or temporarily failing,
  normal message delivery should continue. Search status should expose lag,
  failure, and recovery state so operators can see that search is catching up.
- **D-04:** The live queue should use the same broad useful-text boundary as
  Phase 2 backfill: user text, assistant text, and meaningful tool/output text.
  Binary/image-only payloads remain out of scope unless the parser already
  exposes useful text.

### Deduplication Identity

- **D-05:** Queue item identity and search document identity are separate.
  Queue rows need their own lifecycle identity for leases, retries, attempts,
  and failures; index writes remain keyed by stable transcript-derived row
  identity.
- **D-06:** The idempotent search row identity should be based on
  `TranscriptProvenance`/`SearchRowIdentity`: runtime, transcript source,
  transcript offset or index, role, content type, optional tool id, and
  deterministic chunk index. Mutable tmux window metadata must not participate
  in row identity.
- **D-07:** Live indexing should use the same deterministic chunking policy as
  parser-backed backfill so live processing and rebuilds produce the same chunk
  identities for long assistant/tool/output entries.
- **D-08:** Duplicate live/backfill rows should be handled with idempotent
  upserts by stable row identity. Retries and backfill/live overlap must not
  append duplicate search documents.

### Backfill And Live Convergence

- **D-09:** Backfill/live ownership should be tracked with transcript-level
  watermarks plus idempotent upserts. Watermarks make the boundary explicit;
  upserts make restart and boundary overlap safe.
- **D-10:** Watermarks should be tracked per transcript source using stable
  transcript coordinates, such as byte offset and/or parser entry index. They
  should not be keyed by tmux window id.
- **D-11:** While the initial backfill generation is building, live batches
  should converge into the same writable generation as backfill. A separate
  live overlay index is out of scope for this phase.
- **D-12:** If a stored watermark is stale or uncertain after restart, recovery
  should replay from the last safe transcript coordinate and rely on idempotent
  upserts to absorb duplicates. Skipping ahead and missing messages is not
  acceptable.
- **D-13:** Live indexing batches should honor the project-level batching rule:
  drain when at least 32 queue items are ready or 60 seconds have elapsed since
  the previous flush.

### Failure And Stale-Session Behavior

- **D-14:** Queue processing should use bounded retries with persisted attempt
  counts, leases, lease expiry, last error, and final failed/dead-letter state.
  Failed rows stay inspectable and recoverable.
- **D-15:** Queue lag and failed items should degrade search status rather than
  disabling the local app. Status should include queued item count, failed item
  count, lag or oldest queued age when available, and a recent error summary.
- **D-16:** Search documents for sessions whose tmux window is no longer open
  should be marked stale and hidden from normal v1 results. Normal result clicks
  must not route users to dead tmux windows.
- **D-17:** Failed/dead-letter rows should recover through rebuild or explicit
  retry controls, using the same idempotent path as normal live processing.
  Automatically replaying every failed row on each restart is too noisy for
  permanent parser or index bugs.

### the agent's Discretion

No business-level decisions were delegated to the agent. Downstream agents may
choose exact file names, SQLite/table layout or JSONL structure, lease timeout,
retry count, batch scheduler implementation, and status field factoring where
those choices preserve the decisions above and follow existing Codi patterns.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project And Scope

- `.planning/PROJECT.md` - Project value, local-first constraints, open-session
  v1 boundary, and model/index direction.
- `.planning/REQUIREMENTS.md` - Phase 3 mapped requirements: `CORP-05`,
  `INDX-04`, `INDX-05`, `INDX-06`, and `INDX-07`.
- `.planning/ROADMAP.md` - Phase 3 goal, success criteria, dependency on Phase
  2, and phase ordering.
- `.planning/STATE.md` - Current project position and prior phase completion.

### Prior Phase Context

- `.planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md` -
  Locked search identity, lifecycle status, request-path import boundary, and
  search-owned state namespace.
- `.planning/phases/02-worker-skeleton-backfill-and-rebuild-path/02-CONTEXT.md`
  - Locked worker/backfill lifecycle, parser-backed corpus, generation
  activation, and visible readiness decisions.

### Codebase Maps

- `.planning/codebase/STACK.md` - Backend/frontend stack, dependencies, and
  verification commands.
- `.planning/codebase/ARCHITECTURE.md` - Session monitor, event bus,
  transcript, state, search contract, and worker architecture.
- `.planning/codebase/INTEGRATIONS.md` - Runtime transcript sources, tmux,
  local state files, Web UI auth, and deployment boundaries.

### Implementation Surfaces

- `src/codexbot/search/contracts.py` - Search provenance, row identity,
  routing metadata, generation metadata, counters, status, and backfill
  document contracts.
- `src/codexbot/search/backfill.py` - Existing parser-backed open-session
  backfill, deterministic chunking, and generation document materialization.
- `src/codexbot/search/state.py` - Search-owned state paths, generation
  manifests, active generation metadata, and worker status persistence.
- `src/codexbot/search/worker.py` - Local worker CLI boundary for initial
  backfill and rebuild tasks.
- `src/codexbot/search/supervisor.py` - Backend startup/supervisor boundary for
  search worker lifecycle.
- `src/codexbot/session_monitor.py` - Live transcript polling, `NewMessage`,
  transcript offsets/indexes, and listener integration point.
- `src/codexbot/session.py` - Open window/session state, runtime transcript
  resolution, and parsed transcript read helpers.
- `src/codexbot/transcript_parser.py` - Runtime-neutral parsed transcript
  entries and content classification.
- `src/codexbot/web/api.py` - Authenticated search status/search API routes and
  WebSocket/event integration constraints.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `SearchRowIdentity.from_provenance()` already encodes the desired stable
  row identity without mutable tmux routing metadata.
- `TranscriptProvenance` already contains the transcript source, offset, index,
  role, content type, tool metadata, and timestamp needed for live queue
  identity and watermarks.
- `SearchCounters` already has `queued_items` and `failed_items`; Phase 3 can
  populate these while preserving the Phase 1/2 status contract.
- `SearchBackfillDocument` is the shared document shape live processing should
  converge on before future retrieval/index phases.
- `DEFAULT_CHUNK_MAX_CHARS`, `DEFAULT_CHUNK_OVERLAP_CHARS`, and the backfill
  chunking helper define the deterministic chunk policy live indexing should
  reuse or extract.

### Established Patterns

- Search-owned runtime state belongs under `CODEXBOT_DIR/search`; do not write
  queue leases, retries, watermarks, or failures to `monitor_state.json` or
  `state.json`.
- FastAPI request handlers and WebSocket delivery must stay lightweight and
  avoid importing heavy embedding/indexing dependencies.
- Transcript JSONL and parsed transcript entries are the authoritative search
  corpus. Terminal scrollback, Web UI history snapshots, and Telegram-truncated
  messages are not corpus inputs.
- Current tmux `window_id` is routing/display metadata only. It can hide or
  route open-session results, but it must not define search identity.
- Worker and state writes should use existing atomic-file patterns unless the
  implementation introduces a more suitable local durable store under the same
  search state namespace.

### Integration Points

- Add live queue storage, leases, retry/dead-letter state, and watermarks under
  `src/codexbot/search/` and `CODEXBOT_DIR/search`.
- Attach a nonblocking queue producer to `SessionMonitor` listener events.
- Extend the worker path so it drains queued live items in batches of 32 or on
  the 60-second timer and writes/upserts documents into the current writable
  generation.
- Extend search status reads to include live queue lag, failed item count,
  recent error, and stale/degraded state without breaking existing typed status
  responses.
- Filter or mark stale search results against current `SessionManager`/tmux
  state at query/status time so closed windows do not receive result routing.

</code_context>

<specifics>
## Specific Ideas

User-selected specifics from discussion:

- Queue useful parsed transcript entries, not whole turns.
- Produce queue rows from `SessionMonitor` events.
- Keep Web UI and Telegram message delivery moving when search queue writes or
  drains are lagging.
- Use separate queue lifecycle IDs and transcript-derived row identities.
- Reuse backfill chunking for live items.
- Use per-transcript watermarks plus idempotent upserts for backfill/live
  overlap.
- Write live batches into the same writable generation rather than a separate
  overlay.
- Replay from a safe watermark after uncertain restarts.
- Use bounded retries and persisted dead-letter state.
- Hide stale closed-session documents from normal v1 results.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within Phase 3 scope.

</deferred>

---

*Phase: 3-Live Queue and Convergence*
*Context gathered: 2026-05-22*
