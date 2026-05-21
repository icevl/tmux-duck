# Project Research Summary

**Project:** Codi Session Search
**Domain:** local-first hybrid search for active Codex/Claude Web UI sessions
**Researched:** 2026-05-21
**Confidence:** HIGH for roadmap direction; MEDIUM for final embedding/backend tuning

## Executive Summary

Codi session search is a local navigation and recall feature for a self-hosted tmux session bridge, not a knowledge-base product. The v1 product should help the Web UI user answer "which open session was that?" and "where in that active transcript did it happen?" Results should be ranked by session, include matching snippets, and route only through current tmux `window_id` values while preserving transcript JSONL and Codi session state as the source of truth.

The recommended implementation is a derived, rebuildable search index under `$CODEXBOT_DIR/search/`: SQLite for the durable queue/control plane, LanceDB OSS for local hybrid retrieval, and a separate Python worker process for backfill, embeddings, LanceDB writes, search, and maintenance. The main FastAPI process should only enqueue lightweight ingest work, expose authenticated search/status routes, and proxy queries to the worker with short timeouts. Start with `Qwen/Qwen3-Embedding-0.6B` via Sentence Transformers, but treat model, vector dimension, chunk sizing, and optimize cadence as validation topics on the target Mac mini.

The main risks are coupling search to the existing delivery hot path, getting transcript identity wrong, letting backfill and live indexing race, and presenting partial indexes as complete search. Mitigate these by defining stable transcript provenance before UI work, keeping search state separate from `monitor_state.json`, using a lease-based durable queue with idempotent upserts, surfacing index health from the first phase, and keeping the v1 corpus limited to currently open sessions.

## Key Findings

### Recommended Stack

Use LanceDB OSS as the persisted local hybrid index, SQLite WAL as the durable queue/status database, and a separate Python worker as the only owner of embedding/model runtime and LanceDB writes. This keeps Codi's FastAPI, WebSocket, Telegram delivery, terminal sockets, and transcript monitor responsive even when the search worker is loading a model, backfilling, optimizing indexes, or failing.

Qwen3-Embedding-0.6B is the right default candidate for v1 because it is local, Apache-2.0, instruction-aware, modern, and small enough to benchmark for a Mac mini deployment. It should not be locked in blindly: run implementation validation against real Codi transcript fixtures and keep a smaller ONNX-backed fallback such as `gte-modernbert-base` or FastEmbed-supported BGE small available if Qwen is too slow or memory-heavy.

**Core technologies:**
- LanceDB OSS 0.30.2: local vector, metadata, FTS/BM25, hybrid search, and RRF/reranking in one embedded store.
- SQLite WAL plus optional `aiosqlite`: durable queue, leases, retries, backfill status, high-water marks, index metadata, and inspectable recovery state.
- Separate Python search worker: isolates model load, embedding batches, LanceDB writes, backfill, optimize, and local search API from the main Codi event loop.
- Sentence Transformers plus PyTorch: default local embedding runtime for Qwen3, with normalized embeddings and optional dimensional truncation.
- Qwen/Qwen3-Embedding-0.6B: default semantic model candidate; requires local benchmark before finalizing memory, latency, chunk length, and vector dimension.

### Expected Features

The v1 feature should be a Web UI search entry integrated into the existing session workflow. It must return bounded ranked session groups, with nested hit snippets proving why each session matched. Every result should carry runtime, current `window_id`, session id when known, cwd, status, role/content labels, timestamps or transcript positions, and enough metadata for click-through.

**Must have (table stakes):**
- Search currently open sessions only - the v1 corpus is active tmux windows, not archived history.
- Cross-runtime indexing - Codex and Claude transcript records need equal treatment.
- Session metadata matching - runtime, cwd, name, tmux id, session id, status, pinned state, and activity should influence results.
- User/assistant/useful tool-output indexing - search should use normalized local transcript text, not Telegram-truncated text or terminal scrollback.
- Hybrid lexical plus semantic retrieval - exact paths/errors/commands and meaning-based queries both matter.
- Ranked session groups with snippets - top sessions with top 2-3 hits each, hit counts, match type, role/tool labels, and highlights.
- Click-through to session and hit - session selection by `window_id`; hit jump via transcript offsets/indexes where available.
- Index status and failure states - missing, building, partial, degraded, stale, ready, and unavailable must be visible enough to avoid false "no matches".

**Should have after validation (v1.x):**
- Expand more hits within a session result.
- Manual rebuild and compact index diagnostics.
- Recent query history stored in the browser only.
- Query chips and exact phrase support beyond simple filters.
- Current-session scoped find mode.
- Ranking/reranker tuning based on real misses.

**Defer (v2+):**
- Closed/resumable historical session search.
- Advanced boolean or regex query language.
- Search across commands, skills, GSD choices, and settings.
- Decision/blocker/task extraction over search results.
- Telegram search command.
- Configurable embedding/backend selection in the Web UI.
- Multi-user hosted authorization semantics.

### Architecture Approach

Treat the search index as a derived cache. Transcript JSONL files, tmux windows, `WindowState`, and Codi's monitor/session state remain authoritative. The main process owns session auth, window filtering, event delivery, and lightweight enqueue/status. The worker owns queue draining, transcript backfill through the shared parser, embedding, LanceDB table/schema, hybrid query, snippets, generation rebuilds, and maintenance.

**Major components:**
1. Search contract/models - result DTOs, status DTOs, document schema, stable row identity, index metadata, and ingestion policy.
2. Search queue/control DB - SQLite queue items, leases, retries, dead letters, session index state, model/schema metadata, and worker heartbeat.
3. Nonblocking ingest listener - `SessionMonitor` listener that only offers normalized message intents and returns immediately.
4. Queue writer - main-process background task that durably persists live intents without waiting for the embedding batch window.
5. Worker supervisor/client - starts/restarts the local worker and proxies status/search with timeouts.
6. Search worker - single writer for LanceDB, owner of embedding model, backfill, live-priority batching, query embedding, hybrid search, and optimize.
7. LanceDB index store - chunk rows with vectors, text, provenance, metadata filters, active generation, and merge-upsert by stable `chunk_id`.
8. Web API routes - authenticated `/api/search` and `/api/search/status`, live-window filtering, no model imports.
9. React search UI - debounced search, grouped session results, snippets, filters, status states, and window/hit navigation.

### Critical Pitfalls

1. **Unstable transcript identity** - define row keys from runtime, session id, transcript source/path, offset/index, content type, and optional tool id; keep `window_id` as mutable routing metadata.
2. **Backfill/live race** - record per-transcript watermarks, always queue live events during backfill, and use idempotent upserts so duplicate work is harmless.
3. **Search mutates monitor state** - never write search progress into `monitor_state.json`; keep search-owned backfill/index offsets under `$CODEXBOT_DIR/search/`.
4. **Embedding in the main backend** - keep model imports and LanceDB writes out of FastAPI routes, monitor callbacks, app startup, and WebSocket/Telegram paths.
5. **Non-durable or non-idempotent live queue** - use SQLite leases/retries/dead letters and enforce the requested 32-item or 60-second worker flush behavior.
6. **LanceDB freshness and maintenance ignored** - explicitly schedule FTS/vector optimize/reindex work and surface queue/index lag instead of assuming new rows are always fully indexed.
7. **Hybrid ranking misses exact technical terms** - test paths, commands, stack traces, ticket ids, and quoted phrases alongside semantic paraphrases.
8. **Partial backfill presented as complete search** - status API and UI states are correctness requirements, not polish.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Search Contract and Status Surface

**Rationale:** Stable identity, ingestion policy, result DTOs, filters, and status states are dependencies for every later phase. Building UI or worker code before this will bake in brittle routing and incomplete status semantics.

**Delivers:** Search document schema, chunk identity, allowed text policy, index metadata model, search/status response contracts, basic `/api/search/status`, and tests for provenance, repeated messages, and monitor-state isolation.

**Addresses:** Open-session scope, session metadata matching, index status, local-only boundary, result identity, basic filters.

**Avoids:** Unstable transcript identity, wrong text source, mutating `monitor_state.json`, partial-index confusion.

### Phase 2: Worker Skeleton, Backfill, and Rebuild Path

**Rationale:** The worker/process boundary must exist before embeddings or LanceDB tuning. Initial startup with no DB is a core requirement, so open-session backfill and rebuildability should be proven before live indexing gets complex.

**Delivers:** `src/codexbot/search/` structure, SQLite queue/control schema, worker supervisor/client, local-only worker status API, open-session backfill jobs through the shared transcript parser, generation metadata, and nonblocking startup behavior.

**Uses:** SQLite WAL, worker process, shared transcript parser, `$CODEXBOT_DIR/search/` layout.

**Implements:** Derived index pattern, generation-based rebuild, worker health/degraded status.

**Avoids:** embedding/model work in the main backend, full historical scans in v1, corrupt index blocking Codi startup.

### Phase 3: Live Queue and Convergence

**Rationale:** Search must converge while users continue working. Live message ingestion should be durable and idempotent before semantic indexing and ranking are trusted.

**Delivers:** Offer-only `SessionMonitor` listener, background queue writer, lease-based queue draining, live-priority scheduling, dedupe keys, retry/dead-letter behavior, session removal/rebinding jobs, and tests that append during paused backfill.

**Uses:** SQLite queue leases, high-water marks, stable transcript row identity.

**Implements:** Live indexing control plane and 32-item or 60-second flush trigger semantics at the worker batch layer.

**Avoids:** backfill/live races, in-memory lost work, duplicate rows, stale window results.

### Phase 4: LanceDB Hybrid Retrieval and Ranking

**Rationale:** Once the control plane is reliable, add the retrieval engine and model in a way that can be benchmarked and swapped without touching WebSocket/Telegram/session delivery paths.

**Delivers:** LanceDB schema/table creation, merge-upsert, FTS index, vector column, embedding wrapper, query/document embedding policy, hybrid vector+text search, metadata filters, snippets/highlights, match labels, and golden ranking tests.

**Uses:** LanceDB OSS, Sentence Transformers, Qwen3-Embedding-0.6B candidate, optional lower-memory fallback models.

**Implements:** Hybrid retrieval, exact technical query behavior, top sessions with nested hits.

**Avoids:** vector-only search, missing exact paths/errors, model dimension drift, stale LanceDB FTS/vector behavior.

### Phase 5: Web UI Search Experience and Navigation

**Rationale:** UI should use real status and retrieval behavior instead of placeholder ranking. Search is only useful if users can inspect snippets and move to the right active session safely.

**Delivers:** Sidebar or command-style search entry, debounced API calls, grouped session results, snippets, match labels, filters, empty/loading/degraded/partial states, click-to-open by `window_id`, and stale-result handling. Hit-level scroll/highlight should land here only if the backend history paging contract is ready.

**Addresses:** Web UI workflow integration, ranked session groups, snippets, status display, result limits, filters, click-through.

**Avoids:** partial backfill presented as final, wrong-window navigation, browser-side transcript indexing, search-triggered session mutation.

### Phase 6: Operational Hardening and Model Tuning

**Rationale:** The first working path will need local tuning. This phase converts implementation measurements into stable defaults and gives users recovery tools without expanding the v1 corpus.

**Delivers:** Mac mini benchmark results, chosen embedding dimension/chunk size/batch limits, LanceDB optimize cadence, rebuild/diagnostic controls, stale generation cleanup, worker resource limits, status metrics, and fallback/degraded lexical behavior.

**Uses:** Real transcript fixtures, optional FastEmbed/gte fallback, queue/index metrics, LanceDB maintenance APIs.

**Implements:** Operational recovery and performance budget for open-session search.

**Avoids:** over-provisioned embeddings, slow startup, unbounded queue growth, unoptimized FTS tail, silent semantic degradation.

### Phase Ordering Rationale

- Contract/status comes first because every later result, queue item, and UI state depends on stable transcript provenance and explicit async status.
- Worker/backfill precedes live convergence because missing-DB startup and rebuild are core requirements, and live work must reconcile against backfill watermarks.
- Live queue precedes retrieval quality because reliable exactly-once-ish ingestion is more foundational than ranking polish.
- LanceDB/model work waits until the queue and worker boundary are stable, so model failures cannot destabilize Codi's existing delivery paths.
- UI search waits for real result/status payloads, avoiding a frontend that hides partial indexes or assumes the wrong ranking model.
- Operational tuning comes last because model choice, vector dimension, chunk sizes, and optimize cadence need measurements from the implemented path.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 4:** Needs `$gsd-plan-phase --research-phase 4` or equivalent validation around pinned LanceDB APIs, Qwen3 prompt/embedding policy, chunk sizing, vector dimensions, FTS optimize behavior, and model fallback selection.
- **Phase 6:** Needs targeted implementation research/benchmarking on the target Mac mini for memory, latency, batch sizes, optimize cadence, and degraded/fallback modes.

Phases with standard patterns where additional research can usually be skipped:
- **Phase 1:** Schema/DTO/status contract work is driven by local requirements and existing Codi invariants.
- **Phase 2:** Worker skeleton, rebuild state, and local status API follow established process-boundary and durable-state patterns.
- **Phase 3:** Durable queue, leases, retries, idempotency, and high-water marks are well-known patterns; focus on tests rather than more research.
- **Phase 5:** Web UI search rendering and session navigation are standard frontend patterns, though a UI phase/spec is still useful for interaction details.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH overall, MEDIUM for final model | LanceDB, SQLite, and worker isolation are strongly supported by sources and architecture. Qwen3 remains a candidate until local throughput, memory, and relevance are measured. |
| Features | HIGH for v1, MEDIUM for v1.x | Open-session scope, session+snippet result shape, hybrid retrieval, status, and local-only constraints come directly from project choices. Differentiators need usage validation. |
| Architecture | HIGH for boundaries, MEDIUM for tuning | Process separation, derived index, durable queue, and shared parser usage are clear. LanceDB maintenance cadence and hit navigation paging need implementation validation. |
| Pitfalls | HIGH | Pitfalls align across project constraints, codebase concerns, LanceDB behavior, and local-first transcript-search requirements. |

**Overall confidence:** HIGH for roadmap and scope; MEDIUM for embedding/backend performance defaults until measured.

### Gaps to Address

- **Qwen3 performance and quality:** Benchmark real Codi transcript chunks on the target Mac mini for docs/sec, query p95, memory, and top-k relevance; compare 512 vs 1024 stored dimensions.
- **Chunking policy:** Define bounded chunks for long assistant/tool output with enough overlap and transcript provenance for snippets and navigation.
- **LanceDB maintenance cadence:** Validate FTS/vector freshness after append batches and define optimize/reindex thresholds.
- **Hit navigation API:** Decide whether v1 includes centered `around_offset`/`around_index` history fetch, or whether hit clicks initially open the session and highlight only when the message is already loaded.
- **Golden query corpus:** Build fixtures covering exact file paths, stack traces, commands, session metadata, broad semantic task descriptions, repeated identical text, Codex records, and Claude records.
- **Fallback model/backend:** Keep the abstraction thin enough to switch to a smaller ONNX-backed model if Qwen3 is too slow, without reworking API or UI contracts.
- **Packaging and supervision:** Decide how search worker dependencies are installed and how the worker is started/restarted in local deployments.

## Sources

### Primary (HIGH confidence)

- `.planning/PROJECT.md` - v1 scope, local-first constraints, worker decision, LanceDB-first choice, Qwen3 candidate, and 32-item/60-second batching.
- `.planning/research/STACK.md` - stack recommendation, package versions, model alternatives, operational defaults, and compatibility notes.
- `.planning/research/FEATURES.md` - table stakes, differentiators, anti-features, MVP definition, and v2 deferrals.
- `.planning/research/ARCHITECTURE.md` - component boundaries, data flow, worker/control-plane design, state management, and suggested build order.
- `.planning/research/PITFALLS.md` - critical pitfalls, phase mapping, integration gotchas, performance traps, security mistakes, and recovery strategies.
- Local codebase research files referenced by the researchers: `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/INTEGRATIONS.md`, `.planning/codebase/TESTING.md`, `.planning/codebase/CONCERNS.md`.
- LanceDB docs - hybrid search, full-text search, reranking, update/upsert, local connection, vector search, indexing, reindexing, and optimize behavior.
- Qwen/Qwen3-Embedding-0.6B model card and Qwen3 Embedding repository - model size, dimensions, context, instruction behavior, license, and dependency requirements.
- Sentence Transformers docs and package metadata - local embedding inference, normalized embeddings, ONNX/export paths, and `truncate_dim`.

### Secondary (MEDIUM confidence)

- PyTorch MPS docs - Apple Silicon backend support, still requiring local performance validation.
- FastEmbed docs and package metadata - plausible ONNX fallback path if Qwen3 is too heavy.
- SQLite FTS5 docs - lexical-only fallback semantics and BM25/snippet capabilities.
- PyPI package metadata for `lancedb`, `sentence-transformers`, `torch`, `transformers`, `fastembed`, and alternatives.

### Tertiary (LOW confidence)

- Competitor UX references from VS Code, Slack, GitHub Code Search, and JetBrains Search Everywhere - useful for result grouping/filter/navigation patterns, not decisive for Codi scope.

---
*Research completed: 2026-05-21*
*Ready for roadmap: yes*
