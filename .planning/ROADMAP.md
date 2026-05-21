# Roadmap: Codi Session Search

## Overview

Codi session search will move from a stable local contract to a working open-session search experience in vertical MVP slices. The roadmap first makes search status, provenance, and API boundaries explicit; then proves asynchronous open-session backfill and live queue convergence; then adds local LanceDB hybrid retrieval; then ships the Web UI search and navigation workflow; and finally tunes the worker, model, and degraded modes for reliable local Mac mini operation.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Search Contract and Status Surface** - Establish the local search API, status semantics, provenance, and derived-index boundary.
- [ ] **Phase 2: Worker Skeleton, Backfill, and Rebuild Path** - Create asynchronous open-session indexing that can build or rebuild search storage without blocking Codi.
- [ ] **Phase 3: Live Queue and Convergence** - Durably capture new transcript items and keep the derived index aligned with live open sessions.
- [ ] **Phase 4: LanceDB Hybrid Retrieval and Ranking** - Deliver local lexical plus semantic search with ranked session groups and matching snippets.
- [ ] **Phase 5: Web UI Search Experience and Navigation** - Add the browser search workflow, status states, filters, snippets, and result navigation.
- [ ] **Phase 6: Operational Hardening and Model Tuning** - Validate local performance, worker failure behavior, metrics, and degraded search modes.

## Phase Details

### Phase 1: Search Contract and Status Surface

**Goal:** Codi exposes a stable local search contract and honest status semantics before indexing work begins.
**Mode:** mvp
**Depends on**: Nothing (first phase)
**Requirements**: CORP-03, CORP-04, CORP-06, OPS-02
**Success Criteria** (what must be TRUE):

  1. User can call authenticated search/status surfaces that return structured missing or unavailable responses without importing embedding models in FastAPI handlers.
  2. Every planned indexed item has stable provenance for runtime, session ID when known, transcript source, transcript offset or index, role/content type, and optional tool identifier.
  3. Current tmux `window_id` is represented only as mutable routing metadata, while transcript provenance is the row identity for indexed content.
  4. Codi treats search state as a derived cache that can be rebuilt from transcript/session state and does not write search progress into `monitor_state.json`.

**Plans**: 3 plans
Plans:
**Wave 1**

- [ ] 01-01-PLAN.md — Define runtime-neutral search provenance, identity, request, and status contracts.

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 01-02-PLAN.md — Reserve search-owned derived state and typed missing-index provider behavior.

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 01-03-PLAN.md — Wire authenticated search/status API routes and import-boundary verification.

### Phase 2: Worker Skeleton, Backfill, and Rebuild Path

**Goal:** Codi can create or rebuild a search index for open Codex and Claude sessions asynchronously while existing frontends keep working.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: CORP-01, CORP-02, INDX-01, INDX-02, INDX-03, INDX-08
**Success Criteria** (what must be TRUE):

  1. User can start Codi with no search database and continue using Web UI, Telegram, terminal, WebSocket delivery, and session monitoring while initial indexing starts in the background.
  2. Search storage is created under the configured Codi state directory and can be rebuilt from transcript/session state without manual state clearing.
  3. Initial backfill covers every currently open tmux-backed Codex and Claude session.
  4. Backfill reads normalized Codex and Claude transcript records through the existing runtime transcript parsers and includes useful user, assistant, and tool/output text.

**Plans**: TBD

### Phase 3: Live Queue and Convergence

**Goal:** New transcript activity stays durable and eventually converges into the derived index while users continue working.
**Mode:** mvp
**Depends on**: Phase 2
**Requirements**: CORP-05, INDX-04, INDX-05, INDX-06, INDX-07
**Success Criteria** (what must be TRUE):

  1. New user, assistant, and useful tool/output transcript items are durably queued while initial backfill is still running.
  2. Live indexing work flushes in batches when 32 queued items are ready or 60 seconds have passed since the previous flush.
  3. Duplicate backfill and live events do not create duplicate search documents because queue items and index writes are idempotent.
  4. Queue leases, retries, failed items, backfill watermarks, and worker status persist outside `monitor_state.json` and recover after process restart.
  5. Results for sessions that are no longer open are hidden, removed, or marked stale instead of routing to a dead tmux window.

**Plans**: TBD

### Phase 4: LanceDB Hybrid Retrieval and Ranking

**Goal:** Users can retrieve the right open sessions through local hybrid search with ranked session groups and explainable hits.
**Mode:** mvp
**Depends on**: Phase 3
**Requirements**: SRCH-02, SRCH-04, SRCH-05, SRCH-06, RETR-01, RETR-02, RETR-03, RETR-04, RETR-05, RETR-06, RETR-07, RETR-08, OPS-01
**Success Criteria** (what must be TRUE):

  1. User can search only currently open tmux-backed Codex and Claude sessions and receive ranked session groups with bounded nested hits.
  2. Exact technical terms such as paths, commands, stack traces, symbols, ticket IDs, and quoted phrases are found through lexical search.
  3. Meaning-based queries retrieve relevant sessions through local semantic search, and Codi combines lexical and semantic matches into one hybrid ranked result list.
  4. Results can match and narrow by metadata such as runtime, cwd/project path, role/content type, status, recent activity, tmux window ID, session ID when known, and pinned state.
  5. User can inspect concise snippets with role/tool labels, timestamps or transcript positions when available, exact-match highlights where applicable, hit counts, relevance ordering, and match labels.
  6. Embedding, indexing, LanceDB writes, search queries, and maintenance run outside the main FastAPI, WebSocket, Telegram, terminal, and monitor hot paths, and transcript text is never sent to cloud embedding or hosted search services.
  7. Ranking fixtures cover exact terms, semantic paraphrases, repeated text, Codex records, Claude records, and session metadata matches.

**Plans**: TBD

### Phase 5: Web UI Search Experience and Navigation

**Goal:** Users can search from the browser session workflow, understand index state, inspect snippets, and navigate safely to matching open sessions.
**Mode:** mvp
**Depends on**: Phase 4
**Requirements**: SRCH-01, SRCH-03, WEB-01, WEB-02, WEB-03, WEB-04, WEB-05, WEB-06, WEB-07
**Success Criteria** (what must be TRUE):

  1. User can start a session search from the existing Web UI workflow without losing the currently selected session or draft input.
  2. User can see search index states such as missing, building, partial, ready, stale, degraded, or unavailable, and can distinguish no matches from building or unavailable search.
  3. User can see that v1 search is limited to open sessions when index status or result context is displayed.
  4. User can use debounced search interactions, capped result payloads, grouped session results, nested snippets, match labels, and filters without the browser loading or indexing full transcripts locally.
  5. User can open a result by current tmux `window_id`, select a hit to scroll or highlight the matching transcript message when loadable, and receive a safe fallback that still opens the owning session when hit-level navigation is unavailable.

**Plans**: TBD
**UI hint**: yes

### Phase 6: Operational Hardening and Model Tuning

**Goal:** Search remains locally reliable under worker failures, resource limits, model validation, and degraded semantic availability.
**Mode:** mvp
**Depends on**: Phase 5
**Requirements**: OPS-03, OPS-04, OPS-05, OPS-06
**Success Criteria** (what must be TRUE):

  1. User can see worker heartbeat, queue lag, indexed/open session counts, backfill progress, and recent indexing errors through the Web UI or authenticated status surface.
  2. Search worker failures degrade search only and do not block session list updates, chat delivery, Telegram delivery, terminal panels, or existing WebSocket events.
  3. Codi has a local benchmark or verification path for Mac-mini-appropriate embedding throughput, memory use, batch size, chunk size, and query latency.
  4. Codi records the chosen embedding defaults or fallback model decision after validating Qwen3-Embedding-0.6B against real Codi transcript fixtures.
  5. User receives clear unavailable status or lexical-only degraded behavior when semantic embedding is not ready.

**Plans**: TBD
**UI hint**: yes

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Search Contract and Status Surface | 0/TBD | Not started | - |
| 2. Worker Skeleton, Backfill, and Rebuild Path | 0/TBD | Not started | - |
| 3. Live Queue and Convergence | 0/TBD | Not started | - |
| 4. LanceDB Hybrid Retrieval and Ranking | 0/TBD | Not started | - |
| 5. Web UI Search Experience and Navigation | 0/TBD | Not started | - |
| 6. Operational Hardening and Model Tuning | 0/TBD | Not started | - |
