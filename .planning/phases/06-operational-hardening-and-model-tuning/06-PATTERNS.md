---
phase: 06
slug: operational-hardening-and-model-tuning
status: complete
created: 2026-05-25
---

# Phase 06 - Pattern Map

## Purpose

Map Phase 6 operational hardening files to existing Codi search and Web UI
patterns so execution extends the current request-safe search stack instead of
adding a second operations surface or moving model work into hot paths.

## Source Artifacts

- `.planning/phases/06-operational-hardening-and-model-tuning/06-CONTEXT.md`
- `.planning/phases/06-operational-hardening-and-model-tuning/06-UI-SPEC.md`
- `.planning/phases/06-operational-hardening-and-model-tuning/06-AI-SPEC.md`
- `.planning/phases/06-operational-hardening-and-model-tuning/06-RESEARCH.md`
- `.planning/phases/06-operational-hardening-and-model-tuning/06-VALIDATION.md`
- `AGENTS.md`

## Implementation File Map

| File | Role | Closest analogs | Concrete patterns to reuse |
| --- | --- | --- | --- |
| `src/codexbot/search/contracts.py` | DTO contract | Existing `SearchStatusResponse`, `SearchQueueSnapshot`, `SearchWorkerStatus`, `SearchIndexMetadata` | Extend typed Pydantic models. Keep response fields bounded and status-safe. |
| `src/codexbot/search/client.py` | Request-safe status/search facade | Existing `get_status()` queue/worker/generation merge | Keep dependency-light imports. Compute status from state/queue metadata only. Do not import LanceDB, torch, transformers, or sentence-transformers here. |
| `src/codexbot/search/state.py` | Search-owned derived state | Existing generation, index metadata, and worker status paths | Add benchmark/model-decision state under `CODEXBOT_DIR/search`, not `state.json` or `monitor_state.json`. |
| `src/codexbot/search/queue.py` | Queue/dead-letter summaries | Existing `get_queue_snapshot()`, `sanitize_error()`, `requeue_failed_items()` | Reuse sanitized errors and queue counts for UI status. Do not expose document payloads. |
| `src/codexbot/search/worker.py` | Worker CLI and status writer | Existing `initial-backfill`, `rebuild`, `live-loop`, `live-drain-once`, `smoke-search-index` | Add benchmark command or delegate to `benchmark.py`. Update worker status around long work without blocking service routes. |
| `src/codexbot/search/supervisor.py` | Backend startup isolation | Existing subprocess initial-backfill and `asyncio.to_thread(drain_live_queue_once)` | Keep failures logged/degraded. Do not await model/index work in FastAPI startup. |
| `src/codexbot/search/retrieval.py` | Degraded retrieval behavior | Existing semantic exception fallback to lexical | Preserve lexical degraded results and sanitized semantic error reasons. |
| `src/codexbot/search/benchmark.py` | New benchmark CLI/helper | `worker.py` smoke command, `index.py` fake provider tests, `ranking.py` fixture scoring | Keep opt-in, structured JSON output, fake-provider tests, optional real model invocation. |
| `src/codexbot/web/api.py` | Authenticated status route | Existing `/api/search/status` and `/api/search` wrapper | Continue using `search_client`; route should not know about worker internals or model packages. |
| `web-ui/src/api.ts` | Frontend DTOs | Existing snake_case search DTOs | Mirror backend optional fields exactly. Keep `request<T>()` cookie/auth behavior. |
| `web-ui/src/components/SessionSearch.tsx` | Status/details UI | Existing search status chips, filters, panels, grouped results | Add accessible details toggle within this component. Do not add a dashboard/modal/admin panel. |
| `web-ui/src/styles.css` | Compact operational styling | Existing `.session-search`, `.search-status`, `.search-state-panel`, mobile rules | Use current tokens, 6-8px radius, wrapping text, no horizontal mobile overflow. |
| `tests/codexbot/test_search_contracts.py` | DTO/import-boundary tests | Existing search contract and heavy-import checks | Add operational DTO shape and request-path import assertions. |
| `tests/codexbot/test_search_worker.py` | Worker/status tests | Existing worker status, smoke, and live drain tests | Add stale heartbeat, status freshness, benchmark command, and safe error checks. |
| `tests/codexbot/test_search_live_queue.py` | Live queue isolation tests | Existing live producer and drain behavior | Add/extend tests for failure recording and nonblocking listener behavior if needed. |
| `tests/codexbot/test_search_retrieval.py` | Degraded/fallback tests | Existing lexical degraded and semantic failure fixtures | Add assertions for Phase 6 fallback labels/reasons if status contract changes. |
| `tests/codexbot/test_web_api.py` | API tests | Existing `/api/search/status` and `/api/search` tests | Assert richer status JSON while preserving authenticated 200 typed responses. |
| `tests/codexbot/test_web_ui_search_contract.py` | Frontend static contract tests | Existing SessionSearch/status/mobile checks | Assert details toggle, aria-expanded, required copy, recovery command text, and no browser-side transcript search. |
| `tests/codexbot/test_search_benchmark.py` | New benchmark tests | `test_search_worker.py` smoke JSON assertions | Use fake provider/fixtures to validate benchmark schema without loading Qwen. |

## Data Flow

1. Search worker and queue code write derived status under `CODEXBOT_DIR/search`.
2. `search.client.get_status()` reads worker, queue, generation, index, and
   benchmark/model metadata without importing heavy model/index packages.
3. `/api/search/status` returns the typed status object with current open-session
   count from tmux.
4. `web-ui/src/api.ts` mirrors the backend DTO and passes it to
   `SessionSearch`.
5. `SessionSearch` shows compact status by default and expanded details on
   demand.
6. Search responses can carry degraded lexical status while grouped results
   remain clickable by `routing.window_id`.
7. Benchmark command writes structured search-owned metadata; status surfaces a
   summary but not full raw transcript/eval payloads.

## Important Existing Constraints

- Routing remains keyed by tmux `window_id`, not names.
- Web UI search remains open-session-only for v1.
- Status and recovery guidance are read-only in the browser.
- Heavy model/index dependencies stay out of FastAPI request imports.
- Normal validation must not load or download Qwen.
- Search status errors are sanitized and bounded.
- Web UI text must wrap within the existing sidebar/mobile drawer.
- `pnpm --dir web-ui build` is the reliable frontend validation command.

## Landmines

- Do not add request-time transcript scans when no first generation exists.
- Do not add Web UI rebuild/retry buttons in Phase 6.
- Do not show raw local paths, stack traces, transcript text, or secret-bearing
  errors in status details.
- Do not treat worker heartbeat staleness as a global service failure.
- Do not mark queue rows done before both generation JSONL and index upsert
  succeed.
- Do not make normal pytest depend on real Qwen weights or network access.
- Do not run `uv run pytest -q` concurrently with frontend asset rebuilds if
  the suite is observing `web-ui/dist`.

## Pattern Map Complete

This map is sufficient for Phase 6 planning and execution.
