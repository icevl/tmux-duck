# Phase 4: LanceDB Hybrid Retrieval and Ranking - Context

**Gathered:** 2026-05-22
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase turns the existing open-session search generation and live queue into
a local retrieval backend. It should build local lexical plus semantic search
over currently open tmux-backed Codex and Claude sessions, rank results as
routeable session groups, return explainable bounded hits, and keep embedding,
LanceDB writes, search queries, and maintenance outside FastAPI, WebSocket,
Telegram, terminal, and monitor hot paths.

This phase does not implement the browser search UI, closed-session search,
Telegram search, advanced query syntax, or current-session find mode. Those are
later or explicitly out-of-scope surfaces.

</domain>

<decisions>
## Implementation Decisions

### Hybrid Ranking

- **D-01:** Ranking should protect exact technical matches. Lexical exact
  matches for paths, commands, stack traces, symbols, quoted phrases, ticket
  IDs, and similar terms get priority; semantic retrieval fills gaps and can
  reorder close ties but should not bury strong exact matches.
- **D-02:** Metadata has two roles: explicit metadata filters hard-constrain the
  result set, while free-text metadata matches add only a bounded score boost.
  Metadata should not dominate a result without useful transcript evidence.
- **D-03:** Session-level ranking should use the strongest matching hit as the
  anchor, then add capped boosts for distinct supporting hits. This prevents
  repeated noisy text from outranking a more directly relevant session.
- **D-04:** The lexical side should use BM25-style retrieval for recall plus
  exact-match boosts for quoted phrases, paths, commands, symbols, and stack
  text. Plain substring-only search is too narrow for Phase 4.

### Result Payload

- **D-05:** Results should be grouped by current open tmux window ID. This keeps
  every result directly routeable to the Web UI session model and preserves the
  existing "1 session = 1 tmux window" contract.
- **D-06:** Each nested hit should be explainable: concise snippet, role/tool
  label, timestamp or transcript position when available, source order, and
  exact-match highlight spans where applicable.
- **D-07:** Phase 4 should implement the full backend filter contract: runtime,
  cwd/project path, role, content type, status, recent activity, tmux window ID,
  runtime session ID when known, and pinned state. The later Web UI phase should
  consume this contract rather than own filtering semantics.
- **D-08:** API responses should expose normalized relevance scores plus match
  labels such as `lexical`, `semantic`, `metadata`, and `hybrid` for both
  session groups and nested hits. Raw backend scores remain internal unless
  needed for debug logs or tests.

### Model And Index Operations

- **D-09:** Phase 4 should plan around one chunk-level LanceDB table containing
  stable row identity, text, embedding vector, filterable metadata columns, and
  lexical/vector indexes. Split lexical/vector stores or JSONL-primary query
  storage are not preferred for the MVP.
- **D-10:** If semantic embedding or vector search is unavailable or too slow,
  search should return lexical plus metadata results with a `degraded` status
  and a clear reason. Local search should not become entirely unavailable just
  because semantic retrieval is unhealthy.
- **D-11:** The existing live queue batching contract carries forward: when the
  worker flushes at 32 ready items or after 60 seconds, it should also embed and
  upsert the corresponding LanceDB rows. A separate live overlay index is out
  of scope for this phase.
- **D-12:** Phase 4 readiness should be gated by both ranking fixtures and local
  model/index smoke validation. Correct API shape alone is not enough; the
  selected local model and LanceDB path must prove they can run within safe
  local resource limits.

### the agent's Discretion

Downstream agents may choose exact LanceDB APIs, table/index file names, column
names, normalized score formulas, BM25/exact boost constants, embedding batch
sizes, timeout values, and fixture organization where those choices preserve
the decisions above and follow existing Codi search-worker boundaries.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project And Scope

- `.planning/PROJECT.md` - Project value, open-session v1 scope, worker
  isolation, LanceDB/Qwen starting choices, and local-only search constraints.
- `.planning/REQUIREMENTS.md` - Phase 4 mapped requirements: `SRCH-02`,
  `SRCH-04`, `SRCH-05`, `SRCH-06`, `RETR-01` through `RETR-08`, and `OPS-01`.
- `.planning/ROADMAP.md` - Phase 4 goal, success criteria, dependencies, and
  boundary before Phase 5 Web UI search.
- `.planning/STATE.md` - Current milestone position and validation concerns for
  LanceDB APIs, Qwen3 performance, chunk sizing, vector dimensions, and
  degraded fallback behavior.

### Prior Phase Context

- `.planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md` -
  Stable search identity, status vocabulary, request-path import boundary, and
  search-owned state namespace.
- `.planning/phases/02-worker-skeleton-backfill-and-rebuild-path/02-CONTEXT.md`
  - Worker lifecycle, parser-backed open-session corpus, generation activation,
  and visible readiness decisions.
- `.planning/phases/03-live-queue-and-convergence/03-CONTEXT.md` - Live queue
  capture timing, idempotent row identity, watermarks, stale-source hiding,
  retry/dead-letter state, and 32/60 batching.

### Codebase Maps

- `.planning/codebase/STACK.md` - Backend/frontend stack, Python/TypeScript
  tooling, runtime dependencies, and verification commands.
- `.planning/codebase/ARCHITECTURE.md` - Session, transcript, event, search,
  worker, and Web API architecture.
- `.planning/codebase/INTEGRATIONS.md` - Runtime transcript sources, local
  state files, tmux, Web UI auth, and search state storage.
- `.planning/codebase/CONCERNS.md` - Relevant performance and fragility notes:
  request-path import boundaries, history/cache pressure, event delivery, and
  search worker isolation.

### Implementation Surfaces

- `src/codexbot/search/contracts.py` - Current search DTOs, request/response
  models, row identity, routing metadata, hit/result contracts, and lifecycle
  status vocabulary.
- `src/codexbot/search/state.py` - Search-owned state namespace and active
  generation/manifest paths.
- `src/codexbot/search/backfill.py` - Parser-backed document materialization
  and deterministic chunking policy.
- `src/codexbot/search/live.py` - Live queue producer, generation document
  upserts, stale-source filtering, and convergence helpers.
- `src/codexbot/search/queue.py` - Durable SQLite queue, leases, retries,
  watermarks, queue snapshot, and stale-source records.
- `src/codexbot/search/worker.py` - Local worker CLI, initial backfill/rebuild,
  live drain loop, and 32/60 batching constants.
- `src/codexbot/search/client.py` - Dependency-light request-path status/search
  provider that Phase 4 should extend without importing heavy dependencies into
  FastAPI.
- `src/codexbot/web/api.py` - Authenticated `/api/search/status` and
  `/api/search` route surface that must remain lightweight.
- `src/codexbot/session.py` - Open window state, history/transcript helpers,
  runtime routing metadata, and current-session filtering source.
- `src/codexbot/transcript_parser.py` - Runtime-neutral parsed transcript
  entries and content classification.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `SearchBackfillDocument` already provides the chunk-level document shape with
  stable identity, provenance, routing metadata, text, timestamp, source order,
  and chunk indexes.
- `SearchRequest`, `SearchResponse`, `SearchSessionResult`, and `SearchHit`
  already define a grouped response surface. Phase 4 should extend them for
  missing filters, highlight spans, labels, and normalized scoring as needed.
- `SearchRoutingMetadata` already carries window ID, cwd, runtime, session ID,
  pinned state, and sort order. It can support metadata filters and boosts.
- `SearchQueueSnapshot`, `SearchStatusResponse`, and the lifecycle enum already
  support degraded status semantics.
- `DEFAULT_CHUNK_MAX_CHARS` and `DEFAULT_CHUNK_OVERLAP_CHARS` define the current
  deterministic chunking baseline that index rows should preserve.

### Established Patterns

- FastAPI routes should depend on lightweight contracts/client modules only.
  Heavy LanceDB, torch, transformers, sentence-transformers, or model imports
  belong in worker/provider modules under `src/codexbot/search/`.
- Transcript JSONL parsed through `TranscriptParser` is the corpus. Web history
  snapshots, terminal scrollback, and Telegram-truncated messages are not
  search inputs.
- Current tmux `window_id` is the routing key and result grouping key; runtime
  session IDs and transcript sources remain provenance/metadata, not primary
  UI routing.
- Search state is derived and rebuildable under `CODEXBOT_DIR/search`. It must
  not write search progress, indexes, watermarks, or runtime state into
  `state.json` or `monitor_state.json`.
- Live queue rows already use stable transcript-derived identities and are
  flushed in bounded worker batches. Retrieval index writes should attach to
  that worker path.

### Integration Points

- Add retrieval/index provider modules under `src/codexbot/search/` for local
  LanceDB table management, embedding, lexical/vector querying, and hybrid
  ranking.
- Extend the worker so initial backfill/rebuild materializes LanceDB index data
  from generation documents, and live flushes embed/upsert new rows into the
  same active index.
- Extend the dependency-light client/search path to call the retrieval backend
  without making FastAPI import model/index libraries directly.
- Extend contracts and tests for full filters, grouping by open window, bounded
  hits, highlight spans, normalized scores, and match labels.
- Filter results against current open-session state and stale-source records so
  closed windows do not appear in normal v1 results.

</code_context>

<specifics>
## Specific Ideas

User-selected specifics from discussion:

- Use exact-first hybrid ranking.
- Treat metadata as explicit filters plus capped ranking boosts.
- Aggregate session scores by strongest hit plus capped diversity support.
- Use BM25-style lexical recall plus exact boosts for technical text.
- Group results by open tmux window ID.
- Return explainable nested hits with labels, positions/timestamps, source
  order, and exact highlight spans.
- Implement the full backend filter contract in Phase 4.
- Return normalized scores plus match labels rather than raw backend scores.
- Use a single chunk-level LanceDB table with text, vector, identity, and
  metadata columns.
- Degrade to lexical plus metadata search when semantic retrieval is unhealthy.
- Embed/upsert LanceDB rows during the existing live worker flush.
- Gate readiness on ranking fixtures and local model/index smoke validation.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within Phase 4 scope.

</deferred>

---

*Phase: 4-LanceDB Hybrid Retrieval and Ranking*
*Context gathered: 2026-05-22*
