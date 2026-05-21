# Requirements: Codi Session Search

**Defined:** 2026-05-21
**Core Value:** Users can quickly locate active sessions by meaning and exact
terms, even when many windows contain long histories. New messages become
searchable soon after turns complete, while the Web UI remains responsive
during startup, backfill, and ongoing indexing.

## v1 Requirements

### Search Scope

- [ ] **SRCH-01**: User can start a session search from the existing Web UI
  session workflow without losing the currently selected session or draft input.
- [ ] **SRCH-02**: User can search across currently open tmux-backed Codex and
  Claude sessions only.
- [ ] **SRCH-03**: User can see that v1 search scope is limited to open sessions
  when index status or result context is displayed.
- [ ] **SRCH-04**: User can receive results grouped as ranked sessions with
  nested matching message snippets.
- [ ] **SRCH-05**: User can search session metadata such as runtime, session
  name, cwd/project path, tmux window ID, session ID when known, status, pinned
  state, and recent activity.
- [ ] **SRCH-06**: User can narrow search results by runtime, cwd/project,
  role/content type, session status, and recent time range.

### Corpus And Provenance

- [ ] **CORP-01**: Codi indexes normalized Codex and Claude transcript records
  through existing runtime transcript parsers rather than Telegram-truncated
  text or terminal viewport scrollback.
- [ ] **CORP-02**: Codi indexes useful user, assistant, and tool/output text
  from both Codex and Claude sessions.
- [ ] **CORP-03**: Codi stores stable provenance for every indexed item,
  including runtime, session ID when known, transcript source, transcript
  offset or index, role/content type, and optional tool identifier.
- [ ] **CORP-04**: Codi uses transcript provenance as indexed row identity and
  uses current tmux `window_id` only as mutable routing metadata.
- [ ] **CORP-05**: Codi removes, hides, or marks search results stale when their
  source session is no longer an open tmux session.
- [ ] **CORP-06**: Codi treats the search index as derived and rebuildable from
  transcript/session state, not as a source of truth.

### Index Lifecycle

- [ ] **INDX-01**: Codi creates the search storage under the configured Codi
  state directory when no existing search database is present.
- [ ] **INDX-02**: Codi starts initial open-session backfill asynchronously so
  FastAPI startup, WebSocket delivery, Telegram delivery, terminal handling,
  and the Web UI remain usable.
- [ ] **INDX-03**: Codi backfills all currently open sessions during initial
  indexing.
- [ ] **INDX-04**: Codi durably queues new transcript items while initial
  backfill is running so live messages are not lost.
- [ ] **INDX-05**: Codi drains live indexing work in batches when at least 32
  queued items are ready or 60 seconds have passed since the previous flush.
- [ ] **INDX-06**: Codi keeps live queue items idempotent so duplicate backfill
  and live events do not create duplicate search documents.
- [ ] **INDX-07**: Codi persists queue leases, retries, failed items, backfill
  watermarks, and worker status outside `monitor_state.json`.
- [ ] **INDX-08**: Codi can recover search indexing after process restart
  without requiring users to manually clear state.

### Retrieval And Ranking

- [ ] **RETR-01**: User can find exact technical terms such as file paths,
  commands, stack traces, symbols, ticket IDs, and quoted phrases through
  lexical search.
- [ ] **RETR-02**: User can find sessions from meaning-based queries through
  local semantic search.
- [ ] **RETR-03**: Codi combines lexical and semantic matches into hybrid ranked
  results rather than exposing two separate result lists.
- [ ] **RETR-04**: Codi uses a local embedding model suitable for Mac mini
  deployment, starting with Qwen3-Embedding-0.6B unless validation selects a
  better small local model.
- [ ] **RETR-05**: Codi does not send transcript text to cloud embedding or
  hosted search services.
- [ ] **RETR-06**: User can see top sessions with bounded top hits per session,
  hit counts, scores or relevance ordering, and match labels such as lexical,
  semantic, metadata, or hybrid.
- [ ] **RETR-07**: User can inspect concise snippets with role/tool labels,
  timestamps or transcript positions when available, and exact-match highlights
  where applicable.
- [ ] **RETR-08**: Codi validates ranking with fixtures that cover exact terms,
  semantic paraphrases, repeated text, Codex records, Claude records, and
  session metadata matches.

### Web UI Experience

- [ ] **WEB-01**: User can see search index status such as missing, building,
  partial, ready, stale, degraded, or unavailable.
- [ ] **WEB-02**: User can distinguish "no matches" from "index is still
  building" and "search is unavailable" states.
- [ ] **WEB-03**: User can open a result session by selecting its result header,
  with routing performed by current tmux `window_id`.
- [ ] **WEB-04**: User can select a result hit and have the Web UI open the
  session and scroll to or highlight the matching transcript message when that
  position can be loaded.
- [ ] **WEB-05**: User receives a safe fallback when hit-level navigation cannot
  load the exact transcript position, while still opening the owning session.
- [ ] **WEB-06**: User can search without the browser loading or indexing full
  transcripts locally.
- [ ] **WEB-07**: User search interactions are debounced and result payloads are
  capped so the Web UI stays responsive with long session histories.

### Operations

- [ ] **OPS-01**: Codi runs embedding, indexing, LanceDB writes, backfill,
  search queries, and index maintenance outside the main FastAPI/event delivery
  hot path.
- [ ] **OPS-02**: Codi exposes authenticated search and search-status API
  surfaces without importing embedding models in request handlers.
- [ ] **OPS-03**: Codi reports worker heartbeat, queue lag, indexed/open session
  counts, backfill progress, and recent indexing errors to the Web UI.
- [ ] **OPS-04**: Search worker failures degrade search only and do not block
  session list updates, chat delivery, Telegram delivery, terminal panels, or
  existing WebSocket events.
- [ ] **OPS-05**: Codi includes a local benchmark or verification path for
  Mac-mini-appropriate embedding throughput, memory use, batch size, chunk size,
  and query latency.
- [ ] **OPS-06**: Codi has a documented fallback/degraded mode that preserves
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
| SRCH-01 | TBD | Pending |
| SRCH-02 | TBD | Pending |
| SRCH-03 | TBD | Pending |
| SRCH-04 | TBD | Pending |
| SRCH-05 | TBD | Pending |
| SRCH-06 | TBD | Pending |
| CORP-01 | TBD | Pending |
| CORP-02 | TBD | Pending |
| CORP-03 | TBD | Pending |
| CORP-04 | TBD | Pending |
| CORP-05 | TBD | Pending |
| CORP-06 | TBD | Pending |
| INDX-01 | TBD | Pending |
| INDX-02 | TBD | Pending |
| INDX-03 | TBD | Pending |
| INDX-04 | TBD | Pending |
| INDX-05 | TBD | Pending |
| INDX-06 | TBD | Pending |
| INDX-07 | TBD | Pending |
| INDX-08 | TBD | Pending |
| RETR-01 | TBD | Pending |
| RETR-02 | TBD | Pending |
| RETR-03 | TBD | Pending |
| RETR-04 | TBD | Pending |
| RETR-05 | TBD | Pending |
| RETR-06 | TBD | Pending |
| RETR-07 | TBD | Pending |
| RETR-08 | TBD | Pending |
| WEB-01 | TBD | Pending |
| WEB-02 | TBD | Pending |
| WEB-03 | TBD | Pending |
| WEB-04 | TBD | Pending |
| WEB-05 | TBD | Pending |
| WEB-06 | TBD | Pending |
| WEB-07 | TBD | Pending |
| OPS-01 | TBD | Pending |
| OPS-02 | TBD | Pending |
| OPS-03 | TBD | Pending |
| OPS-04 | TBD | Pending |
| OPS-05 | TBD | Pending |
| OPS-06 | TBD | Pending |

**Coverage:**
- v1 requirements: 41 total
- Mapped to phases: 0
- Unmapped: 41

---
*Requirements defined: 2026-05-21*
*Last updated: 2026-05-21 after research synthesis*
