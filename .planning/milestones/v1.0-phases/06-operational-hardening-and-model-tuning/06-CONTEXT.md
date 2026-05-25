# Phase 6: Operational Hardening and Model Tuning - Context

**Gathered:** 2026-05-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 6 hardens the already-built open-session search path so Codi remains locally reliable under worker failures, resource limits, model validation uncertainty, and degraded semantic availability. The phase should complete OPS-03 through OPS-06 by exposing useful search operational status, preserving non-search delivery during search failures, adding a local benchmark/verification path for the embedding/index stack, and documenting/implementing degraded behavior when semantic search is not ready.

This phase stays within the v1 scope: open tmux-backed Codex and Claude sessions only. It does not add closed-session search, Telegram search parity, advanced query syntax, or Web UI controls that mutate backend/model tuning state.

</domain>

<decisions>
## Implementation Decisions

### Status UI
- **D-01:** Expose Phase 6 worker heartbeat, queue lag, indexed/open counts, backfill progress, and recent indexing errors through the existing search panel rather than a separate ops panel.
- **D-02:** Keep the default search status UI compact. Show the existing chip/counts by default and provide expandable details for heartbeat, queue lag, progress, and recent errors.
- **D-03:** Refresh status with modest polling of `/api/search/status` plus immediate refreshes after relevant session/search events. This must not put embedding/indexing work on chat, session list, terminal, Telegram, or WebSocket delivery paths.
- **D-04:** Recovery guidance in the Web UI should be read-only. Show clear status and suggested local commands rather than adding Web UI buttons that retry or rebuild search state.

### Degraded Search
- **D-05:** When semantic retrieval is unavailable but indexed transcript documents exist, return lexical/metadata results with an explicit degraded status.
- **D-06:** Before the first searchable generation exists, show indexing/backfill status and no results. Do not add request-time transcript scans for old sessions.
- **D-07:** Degraded warnings should be visible but non-blocking: show inline degraded labels/status around result batches rather than a blocking notice.
- **D-08:** Embedding, LanceDB, or worker failures must degrade search only. Search work should be capped/timed out where needed while session lists, chat delivery, Telegram delivery, terminal panels, and existing WebSocket events continue normally.

### Benchmarks
- **D-09:** Add a local validation path using representative Codi transcript fixtures plus the existing smoke index path. It should cover embedding, LanceDB upsert/index creation, query latency, and degraded fallback behavior.
- **D-10:** Use configurable local thresholds/baselines for Mac-mini-class deployments. Record measured defaults and warn/fail against configuration rather than hard-coding one machine profile.
- **D-11:** Keep `Qwen/Qwen3-Embedding-0.6B` as the semantic default pending validation. If Qwen3 validation fails or the model is not locally available, preserve lexical-only degraded search and document the environment overrides instead of blocking the whole search UI.
- **D-12:** Make benchmark execution opt-in through a documented command or script. Normal unit/type/frontend checks should remain dependency-light and should not require loading large model/index dependencies.

### Queue Recovery
- **D-13:** A missing or stale worker heartbeat is a search degradation/staleness signal. Surface the last heartbeat/error in status, but do not treat it as a global service failure.
- **D-14:** Live indexing items that repeatedly fail should land in an inspectable failed/dead-letter state after bounded retries. Later items should continue processing.
- **D-15:** Once an initial generation exists, prioritize fresh active-session turns over perfect historical completeness under local resource pressure.
- **D-16:** Expensive embedding and index work should stay behind the search worker boundary where possible. Backend request paths should read status/results and degrade safely; they should not become model-loading or index-maintenance paths.

### the agent's Discretion
- Choose exact status polling intervals, stale-heartbeat thresholds, and expandable UI layout details, provided the defaults are modest, local-machine friendly, and documented.
- Choose the fixture shape and metric output format for the benchmark, provided it is deterministic enough for local regression checks and includes the metrics required by OPS-05.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Scope and Requirements
- `.planning/PROJECT.md` — Defines Codi Session Search value, v1 open-session scope, and deferred v2 boundaries.
- `.planning/REQUIREMENTS.md` — Source of OPS-03, OPS-04, OPS-05, and OPS-06.
- `.planning/ROADMAP.md` — Phase 6 goal, requirements, success criteria, and dependency on Phase 5.
- `.planning/STATE.md` — Current milestone state and known concern that Phase 6 must validate LanceDB APIs, Qwen3 performance, chunk sizing, vector dimensions, and degraded fallback selection.

### Prior Phase Context
- `.planning/phases/03-incremental-indexing-queue/03-CONTEXT.md` — Queue capture, watermarks, idempotent live enqueue, 32 item / 60 second batching, and non-search delivery isolation decisions.
- `.planning/phases/04-hybrid-retrieval-ranking/04-CONTEXT.md` — Exact-first hybrid ranking, lexical degraded fallback, LanceDB table direction, and readiness gate expectations.
- `.planning/phases/05-search-ui-navigation/05-CONTEXT.md` — Search sidebar UX, status/filter decisions, open-session-only scope, and search result navigation behavior.

### Codebase Maps
- `.planning/codebase/STACK.md` — Runtime, dependency, and validation command expectations for backend and Web UI.
- `.planning/codebase/ARCHITECTURE.md` — Search contract/state/provider layer and delivery isolation boundaries.
- `.planning/codebase/INTEGRATIONS.md` — Local state, transcript sources, search derived state, and authenticated browser transport details.
- `.planning/codebase/CONCERNS.md` — Current search-related performance bottlenecks, event-bus risk, and worker/model validation concerns.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/codexbot/search/contracts.py`: Already defines `SearchStatusResponse`, `SearchCounters`, `SearchQueueSnapshot`, `SearchWorkerStatus`, and index/degraded states that Phase 6 should extend rather than replace.
- `src/codexbot/search/client.py`: Current request-path status provider reads worker, queue, generation, and index metadata without importing the embedding stack.
- `src/codexbot/search/retrieval.py`: Already returns lexical degraded results when semantic retrieval is unavailable or fails.
- `src/codexbot/search/worker.py`: Provides `smoke-search-index`, `initial-backfill`, `rebuild`, and live queue drain commands; live batching defaults are 32 items or 60 seconds.
- `src/codexbot/search/queue.py`: Owns queue snapshots, failed-item accounting, sanitized errors, retry/failure helpers, and transcript coordinates.
- `web-ui/src/components/SessionSearch.tsx`: Existing compact status chip, indexed/open counts, filters, result groups, and degraded/unavailable panels are the right UI anchor.
- `src/codexbot/web/api.py`: `/api/search/status` and `/api/search` are authenticated and already pass open tmux session counts without exposing tmux errors.

### Established Patterns
- Search derived state lives under `$CODEXBOT_DIR/search` and is rebuildable; it must not write to `state.json` or `monitor_state.json`.
- Backend request paths should import lightweight contracts/providers only. Model loading, embedding, LanceDB writes, and index maintenance belong outside hot-path route handlers.
- Open-session search routes by tmux `window_id`; results should remain routeable only to currently open sessions.
- Web UI status should reuse the existing search sidebar and auth/event/polling patterns instead of adding a new global admin surface.

### Integration Points
- Extend `SearchStatusResponse` and `/api/search/status` with heartbeat freshness, queue lag, failed/dead-letter counts, backfill progress, recent safe errors, and benchmark/model metadata as needed.
- Extend `SessionSearch` with an expandable status details area and inline degraded labels while preserving the compact default sidebar layout.
- Harden `search/supervisor.py` and `search/worker.py` so stale heartbeats, failed queue items, and worker/model exceptions surface as search status degradation.
- Add an opt-in benchmark command or script that uses fixture transcripts and the existing smoke-index path to measure embedding throughput, memory, batch size, chunk size, upsert/query latency, and fallback behavior.

</code_context>

<specifics>
## Specific Ideas

- Status should be available from the Web UI search panel and the authenticated API, with the UI details hidden behind expansion by default.
- Degraded lexical results should remain usable and clearly labeled; degraded status should not block the user from opening matching sessions.
- If no first generation exists yet, the search UI should show progress/status rather than scanning large transcript histories on demand.
- Recovery information should be actionable but read-only: provide suggested local commands instead of Web UI retry/rebuild buttons.
- Benchmarks should validate Qwen3 against real Codi transcript fixtures but keep normal test/check runs light.

</specifics>

<deferred>
## Deferred Ideas

- Web UI backend/model tuning mutation controls remain deferred to v2 or a separate admin-controls phase.
- Closed or resumable historical session search remains deferred to v2.
- Telegram search parity remains deferred to v2.
- Advanced boolean, regex, and query-qualifier syntax remain deferred to v2.

</deferred>

---

*Phase: 6-Operational Hardening and Model Tuning*
*Context gathered: 2026-05-25*
