# Phase 2: Worker Skeleton, Backfill, and Rebuild Path - Context

**Gathered:** 2026-05-21
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase proves the search worker and initial backfill path without adding
semantic embeddings, LanceDB retrieval, live queue convergence, or the browser
search experience. It should create rebuildable search-owned state under
`CODEXBOT_DIR/search`, start a lightweight local worker process from backend
startup, backfill the currently open tmux-backed Codex and Claude sessions
through existing transcript parser APIs, and expose truthful status while the
index is missing, building, built-but-not-queryable, or failed.

The phase must keep FastAPI, WebSocket delivery, Telegram delivery, terminal
handling, and session monitoring usable while backfill runs. It must not import
embedding, LanceDB, torch, transformers, or other heavy indexing dependencies
on request paths.

</domain>

<decisions>
## Implementation Decisions

### Worker And Backfill Lifecycle

- **D-01:** Phase 2 should establish a lightweight local search worker CLI or
  equivalent process boundary now. This boundary exists even before embeddings
  and LanceDB retrieval are implemented, so future model/index work does not
  enter the FastAPI or event-delivery process.
- **D-02:** The backend should start the worker path automatically during normal
  backend lifecycle when search/web features are enabled. First-run backfill
  must not require the operator to run a second command.
- **D-03:** Phase 2 should record worker heartbeat, current task, and recent
  failure state, but it should not implement restart loops or backoff policy.
  Restart/backoff supervision belongs to operational hardening.
- **D-04:** Startup should schedule initial backfill when no active search
  generation exists. An explicit local rebuild command/path should create a
  fresh generation rather than mutating an existing active generation in place.

### Open-Session Corpus

- **D-05:** Backfill scope is the current open tmux-backed session set. Enumerate
  current window/session state and resolve Codex or Claude transcript files
  through existing runtime/session helpers. Do not glob all historical
  transcripts as v1 search corpus.
- **D-06:** Backfill should consume a reusable backend stream of parsed
  transcript entries plus transcript source/provenance. It should reuse
  `TranscriptParser` and avoid coupling indexing to the Web UI
  `HistorySnapshot` payload shape.
- **D-07:** The corpus should favor broad recall: every parsed text-bearing
  entry should be eligible for indexing, including user messages, assistant
  messages, tool use/result text, local command output, thinking text, and any
  other textual `ParsedEntry` emitted by the shared parser. Binary/image-only
  payloads cannot become text documents unless the parser already exposes text.
- **D-08:** Phase 2 should build chunk documents from parsed entries and
  preserve `chunk_index` in `SearchRowIdentity`. This avoids a later corpus
  rewrite for long assistant/tool/output messages.

### Rebuild And State Ownership

- **D-09:** Search generations should be built atomically. A rebuild writes a
  new inactive generation directory/manifest and only marks it active when
  backfill completes successfully.
- **D-10:** The explicit rebuild interface in this phase should be local
  worker/CLI driven. Web UI controls and authenticated rebuild APIs are later
  product surface work.
- **D-11:** Worker status, backfill manifests, generation metadata, counters,
  recent errors, and any future control data must live under
  `CODEXBOT_DIR/search`. Search must not write to `monitor_state.json`,
  `state.json`, or source-controlled repo files for runtime progress.
- **D-12:** If the process stops during initial backfill or rebuild, incomplete
  generations are treated as inactive. The next startup or rebuild command
  should create a fresh generation and rerun backfill idempotently. Fine-grained
  resumable watermarks belong to the live queue/convergence phase.

### Visible Readiness

- **D-13:** `/api/search/status` should report `state="building"` with
  `available=false` while Phase 2 backfill is running. This distinguishes
  first-run work from a missing search index.
- **D-14:** Phase 2 should populate backfill-oriented counters: open sessions,
  indexed sessions, indexed chunks, failed items, and generation metadata.
  Live queue lag and queued item counters may remain absent or zero until
  Phase 3 owns the durable queue.
- **D-15:** After Phase 2 backfill succeeds but before query retrieval exists,
  status should include the active generation and counters but remain
  `available=false` with an `unavailable` state/reason for the missing query
  backend. Do not report a false `ready` search state before search queries can
  return real results.
- **D-16:** Worker/backfill errors should be visible through search status
  reason/counters and logs without turning normal status/search requests into
  transport failures. Existing Codi features must continue to work.

### the agent's Discretion

No business-level decisions were delegated to the agent. Downstream agents may
choose exact module names, JSON file names, helper boundaries, chunk sizing, and
test factoring where the choice follows existing Codi patterns and preserves
the decisions above.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project And Scope

- `.planning/PROJECT.md` - Project value, local-first constraints, worker
  isolation decision, LanceDB/Qwen candidates, and open-session v1 scope.
- `.planning/REQUIREMENTS.md` - Phase 2 mapped requirements: `CORP-01`,
  `CORP-02`, `INDX-01`, `INDX-02`, `INDX-03`, and `INDX-08`.
- `.planning/ROADMAP.md` - Phase 2 goal, success criteria, dependencies, and
  phase ordering.
- `.planning/STATE.md` - Current project position and decisions inherited from
  Phase 1.

### Prior Phase And Research

- `.planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md` -
  Locked Phase 1 identity, status, request-path import, and search-state
  boundary decisions.
- `.planning/research/SUMMARY.md` - Research rationale for worker isolation,
  derived search state, SQLite/LanceDB direction, and Phase 2 implications.

### Codebase Maps

- `.planning/codebase/STACK.md` - Backend/frontend stack, runtime dependencies,
  and verification commands.
- `.planning/codebase/ARCHITECTURE.md` - Session, transcript, event, search
  contract, and state architecture.
- `.planning/codebase/INTEGRATIONS.md` - Runtime transcript sources, local state
  files, Web UI auth, tmux, and deployment boundaries.

### Implementation Surfaces

- `src/codexbot/search/contracts.py` - Existing search DTOs, lifecycle states,
  generation metadata, counters, row identity, and provenance contracts.
- `src/codexbot/search/state.py` - Existing search-owned state namespace and
  active generation metadata reader.
- `src/codexbot/search/client.py` - Existing dependency-light status/search
  stub used by FastAPI request paths.
- `src/codexbot/session.py` - Window/session state, transcript resolution,
  history cache, and transcript entry reading helpers.
- `src/codexbot/session_monitor.py` - Existing live transcript polling,
  `NewMessage`, and listener patterns.
- `src/codexbot/transcript_parser.py` - Shared Codex/Claude transcript
  normalization and `ParsedEntry` structure.
- `src/codexbot/web/api.py` - Authenticated `/api/search/status` and
  `/api/search` routes and current open-session counter behavior.
- `tests/codexbot/test_search_contracts.py` - Contract-level regression tests
  for provenance, DTO bounds, and import boundaries.
- `tests/codexbot/test_search_state.py` - Search state namespace and
  missing/unavailable status regression tests.
- `tests/codexbot/test_web_api.py` - Web API search/status auth and response
  tests.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `SearchGenerationMetadata`, `SearchCounters`, `SearchStatusResponse`, and
  `SearchRowIdentity` already provide the contract vocabulary Phase 2 should
  populate rather than replacing.
- `search_dir()` reserves `codexbot_dir() / "search"` for derived search state.
  Extend this namespace instead of adding state to monitor/session files.
- `TranscriptParser.parse_entries()` returns `ParsedEntry` values with role,
  content type, tool identifiers, timestamp, transcript offset, and transcript
  index. This is the right normalization layer for backfill.
- `SessionManager.resolve_session_for_window()` and related transcript
  resolution helpers map open windows to transcript-backed sessions.
- `SessionManager._read_transcript_entries()` already stamps raw transcript
  lines with byte offsets before parsing. A public or search-owned helper can
  reuse this behavior without consuming Web UI history DTOs.
- `EventBus`, `SessionMonitor` listeners, and existing web server lifecycle
  code show the local pattern for background services that must not block the
  main event loop.

### Established Patterns

- Routing identity remains current tmux `window_id`; search row identity must
  stay transcript-provenance based and treat window metadata as mutable routing
  data.
- Transcript JSONL files are authoritative. Terminal viewport scrollback and
  Telegram-truncated text are not search corpus inputs.
- Runtime-specific behavior belongs in runtime/session/parser layers, not in
  web handlers or frontend code.
- Blocking or expensive work should be isolated from the asyncio hot path.
  Existing tmux calls use `asyncio.to_thread()`; search model/index work should
  go further and live behind a worker process boundary.
- Runtime state writes use search-owned files and existing atomic JSON patterns
  where possible.

### Integration Points

- Add worker/supervisor/client code under `src/codexbot/search/` or another
  focused backend package while keeping `src/codexbot/web/api.py` imports
  lightweight.
- Attach backend startup to worker launch in the web/server or process lifecycle
  path without making startup wait for full backfill.
- Extend status reads to include worker/backfill state under
  `CODEXBOT_DIR/search`.
- Add a backfill source that enumerates current open windows, resolves runtime
  transcript files, parses entries with provenance, and emits chunk documents.
- Keep tests focused on nonblocking startup/status, state placement,
  parser-backed corpus extraction, generation activation, and interrupted
  rebuild recovery.

</code_context>

<specifics>
## Specific Ideas

User-selected specifics from discussion:

- Establish the worker CLI/process boundary in Phase 2.
- Start the worker automatically with the backend.
- Record heartbeat/failure status now; defer restart/backoff policy.
- Trigger auto-backfill when the active generation is missing and support an
  explicit local rebuild command.
- Backfill only open tmux-backed sessions, not all historical transcript files.
- Consume `ParsedEntry` plus provenance rather than `HistorySnapshot` or raw
  JSONL.
- Index every parsed text-bearing entry for broad recall.
- Chunk long parsed entries and preserve `chunk_index`.
- Use atomic generation activation under `CODEXBOT_DIR/search`.
- Report `building` while backfill runs and `unavailable` with generation
  metadata after backfill succeeds but before retrieval exists.

</specifics>

<deferred>
## Deferred Ideas

- Worker restart loops and backoff supervision belong to operational hardening.
- Durable live queue, queue lag, per-item leases, retry/dead-letter behavior,
  and resumable watermarks belong to Phase 3.
- LanceDB, embeddings, semantic retrieval, lexical retrieval, and actual query
  ranking belong to Phase 4.
- Web UI search controls, rebuild buttons, result rendering, and hit navigation
  belong to later Web UI phases.

</deferred>

---

*Phase: 2-Worker Skeleton, Backfill, and Rebuild Path*
*Context gathered: 2026-05-21*
