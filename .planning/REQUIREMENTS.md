# Requirements: Codi Session Search

**Defined:** 2026-05-21
**Core Value:** Users can quickly locate active sessions by meaning and exact
terms, even when many windows contain long histories. New messages become
searchable soon after turns complete, while the Web UI remains responsive
during startup, backfill, and ongoing indexing.

## v1 Requirements

### Search Scope

- [x] **SRCH-01**: User can start a session search from the existing Web UI
  session workflow without losing the currently selected session or draft input.
- [x] **SRCH-02**: User can search across currently open tmux-backed Codex and
  Claude sessions only.
- [x] **SRCH-03**: User can see that v1 search scope is limited to open sessions
  when index status or result context is displayed.
- [x] **SRCH-04**: User can receive results grouped as ranked sessions with
  nested matching message snippets.
- [x] **SRCH-05**: User can search session metadata such as runtime, session
  name, cwd/project path, tmux window ID, session ID when known, status, pinned
  state, and recent activity.
- [x] **SRCH-06**: User can narrow search results by runtime, cwd/project,
  role/content type, session status, and recent time range.

### Corpus And Provenance

- [x] **CORP-01**: Codi indexes normalized Codex and Claude transcript records
  through existing runtime transcript parsers rather than Telegram-truncated
  text or terminal viewport scrollback.
- [x] **CORP-02**: Codi indexes useful user, assistant, and tool/output text
  from both Codex and Claude sessions.
- [x] **CORP-03**: Codi stores stable provenance for every indexed item,
  including runtime, session ID when known, transcript source, transcript
  offset or index, role/content type, and optional tool identifier.
- [x] **CORP-04**: Codi uses transcript provenance as indexed row identity and
  uses current tmux `window_id` only as mutable routing metadata.
- [x] **CORP-05**: Codi removes, hides, or marks search results stale when their
  source session is no longer an open tmux session.
- [x] **CORP-06**: Codi treats the search index as derived and rebuildable from
  transcript/session state, not as a source of truth.

### Index Lifecycle

- [x] **INDX-01**: Codi creates the search storage under the configured Codi
  state directory when no existing search database is present.
- [x] **INDX-02**: Codi starts initial open-session backfill asynchronously so
  FastAPI startup, WebSocket delivery, Telegram delivery, terminal handling,
  and the Web UI remain usable.
- [x] **INDX-03**: Codi backfills all currently open sessions during initial
  indexing.
- [x] **INDX-04**: Codi durably queues new transcript items while initial
  backfill is running so live messages are not lost.
- [x] **INDX-05**: Codi drains live indexing work in batches when at least 32
  queued items are ready or 60 seconds have passed since the previous flush.
- [x] **INDX-06**: Codi keeps live queue items idempotent so duplicate backfill
  and live events do not create duplicate search documents.
- [x] **INDX-07**: Codi persists queue leases, retries, failed items, backfill
  watermarks, and worker status outside `monitor_state.json`.
- [x] **INDX-08**: Codi can recover search indexing after process restart
  without requiring users to manually clear state.

### Retrieval And Ranking

- [x] **RETR-01**: User can find exact technical terms such as file paths,
  commands, stack traces, symbols, ticket IDs, and quoted phrases through
  lexical search.
- [x] **RETR-02**: User can find sessions from meaning-based queries through
  local semantic search.
- [x] **RETR-03**: Codi combines lexical and semantic matches into hybrid ranked
  results rather than exposing two separate result lists.
- [x] **RETR-04**: Codi uses a local embedding model suitable for Mac mini
  deployment, starting with Qwen3-Embedding-0.6B unless validation selects a
  better small local model.
- [x] **RETR-05**: Codi does not send transcript text to cloud embedding or
  hosted search services.
- [x] **RETR-06**: User can see top sessions with bounded top hits per session,
  hit counts, scores or relevance ordering, and match labels such as lexical,
  semantic, metadata, or hybrid.
- [x] **RETR-07**: User can inspect concise snippets with role/tool labels,
  timestamps or transcript positions when available, and exact-match highlights
  where applicable.
- [x] **RETR-08**: Codi validates ranking with fixtures that cover exact terms,
  semantic paraphrases, repeated text, Codex records, Claude records, and
  session metadata matches.

### Web UI Experience

- [x] **WEB-01**: User can see search index status such as missing, building,
  partial, ready, stale, degraded, or unavailable.
- [x] **WEB-02**: User can distinguish "no matches" from "index is still
  building" and "search is unavailable" states.
- [x] **WEB-03**: User can open a result session by selecting its result header,
  with routing performed by current tmux `window_id`.
- [x] **WEB-04**: User can select a result hit and have the Web UI open the
  session and scroll to or highlight the matching transcript message when that
  position can be loaded.
- [x] **WEB-05**: User receives a safe fallback when hit-level navigation cannot
  load the exact transcript position, while still opening the owning session.
- [x] **WEB-06**: User can search without the browser loading or indexing full
  transcripts locally.
- [x] **WEB-07**: User search interactions are debounced and result payloads are
  capped so the Web UI stays responsive with long session histories.

### Operations

- [x] **OPS-01**: Codi runs embedding, indexing, LanceDB writes, backfill,
  search queries, and index maintenance outside the main FastAPI/event delivery
  hot path.
- [x] **OPS-02**: Codi exposes authenticated search and search-status API
  surfaces without importing embedding models in request handlers.
- [x] **OPS-03**: Codi reports worker heartbeat, queue lag, indexed/open session
  counts, backfill progress, and recent indexing errors to the Web UI.
- [x] **OPS-04**: Search worker failures degrade search only and do not block
  session list updates, chat delivery, Telegram delivery, terminal panels, or
  existing WebSocket events.
- [x] **OPS-05**: Codi includes a local benchmark or verification path for
  Mac-mini-appropriate embedding throughput, memory use, batch size, chunk size,
  and query latency.
- [x] **OPS-06**: Codi has a documented fallback/degraded mode that preserves
  lexical search or clear unavailable status when semantic embedding is not
  ready.

## v2 Requirements

Deferred to future releases. These are tracked but not part of the initial
roadmap unless explicitly promoted.

### Search Expansion

- **V2-01**: User can search closed or resumable historical Codex and Claude
  sessions.
- **V2-02**: User can use advanced boolean, regex, and query-qualifier syntax.
- **V2-03**: User can run a current-session-only transcript find mode.
- **V2-04**: User can expand many more hits within a session result.
- **V2-05**: User can search commands, skills, GSD choices, and settings as
  separate non-transcript result sections.

### Operations And Product Extensions

- **V2-06**: User can manually rebuild, compact, and diagnose search indexes
  from an admin/status surface.
- **V2-07**: User can choose or tune the embedding/index backend from Web UI
  configuration.
- **V2-08**: User can search through Telegram topic-safe commands.
- **V2-09**: Codi can extract decisions, blockers, and tasks from search results
  after retrieval quality is proven.
- **V2-10**: Codi can enforce multi-user or shared-host authorization semantics
  for search results if Codi moves beyond local admin deployment.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Closed or archived session search in v1 | Expands corpus, ranking, runtime-history parity, and privacy scope before active-session search is proven. |
| Cloud embeddings or hosted search | Violates the local-first self-hosted deployment and can expose raw coding transcripts or secrets. |
| Synchronous per-message embedding/index writes | Embedding and index writes on the hot path can stall FastAPI, WebSocket, Telegram, terminal, and monitor flows. |
| Browser-side full transcript indexing | Consumes browser memory, duplicates backend ranking logic, and exposes too much transcript text to the client. |
| Terminal scrollback as canonical search input | Pane text is transient and lossy; normalized transcript records are the source of truth. |
| Name-keyed result routing | Names can change and collide; Codi routing is keyed by tmux `window_id`. |
| Search-triggered session mutation | Search result clicks should not create, kill, resume, reorder, or otherwise mutate sessions. |
| Telegram search parity in v1 | Telegram rendering, topics, and truncation are separate product constraints; v1 is Web UI search. |
| Multi-user hosted ACL model | Codi remains a local/self-hosted admin-style deployment for this project. |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SRCH-01 | Phase 5 | Complete |
| SRCH-02 | Phase 4 | Complete |
| SRCH-03 | Phase 5 | Complete |
| SRCH-04 | Phase 4 | Complete |
| SRCH-05 | Phase 4 | Complete |
| SRCH-06 | Phase 4 | Complete |
| CORP-01 | Phase 2 | Complete |
| CORP-02 | Phase 2 | Complete |
| CORP-03 | Phase 1 | Complete |
| CORP-04 | Phase 1 | Complete |
| CORP-05 | Phase 3 | Complete |
| CORP-06 | Phase 1 | Complete |
| INDX-01 | Phase 2 | Complete |
| INDX-02 | Phase 2 | Complete |
| INDX-03 | Phase 2 | Complete |
| INDX-04 | Phase 3 | Complete |
| INDX-05 | Phase 3 | Complete |
| INDX-06 | Phase 3 | Complete |
| INDX-07 | Phase 3 | Complete |
| INDX-08 | Phase 2 | Complete |
| RETR-01 | Phase 4 | Complete |
| RETR-02 | Phase 4 | Complete |
| RETR-03 | Phase 4 | Complete |
| RETR-04 | Phase 4 | Complete |
| RETR-05 | Phase 4 | Complete |
| RETR-06 | Phase 4 | Complete |
| RETR-07 | Phase 4 | Complete |
| RETR-08 | Phase 4 | Complete |
| WEB-01 | Phase 5 | Complete |
| WEB-02 | Phase 5 | Complete |
| WEB-03 | Phase 5 | Complete |
| WEB-04 | Phase 5 | Complete |
| WEB-05 | Phase 5 | Complete |
| WEB-06 | Phase 5 | Complete |
| WEB-07 | Phase 5 | Complete |
| OPS-01 | Phase 4 | Complete |
| OPS-02 | Phase 1 | Complete |
| OPS-03 | Phase 6 | Complete |
| OPS-04 | Phase 6 | Complete |
| OPS-05 | Phase 6 | Complete |
| OPS-06 | Phase 6 | Complete |

**Coverage:**
- v1 requirements: 41 total
- Mapped to phases: 41
- Unmapped: 0

---
*Requirements defined: 2026-05-21*
*Last updated: 2026-05-22 after Phase 3 verification*
