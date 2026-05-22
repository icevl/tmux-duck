---
phase: 03-live-queue-and-convergence
plan: 03
subsystem: search
tags: [queue-worker, jsonl-upsert, stale-sessions, retry]
requires:
  - phase: 03-live-queue-and-convergence
    provides: queue state and live producer from plans 03-01 and 03-02
provides:
  - live queue drain loop with 32-row and 60-second flush behavior
  - atomic generation document upsert by SearchRowIdentity
  - retry/dead-letter handling and explicit failed-row requeue helper
  - stale-source marking and filtering for closed tmux sessions
affects: [search-worker, search-status, web-server-lifecycle]
tech-stack:
  added: []
  patterns: [atomic jsonl upsert, bounded worker drain, stale-source registry]
key-files:
  created: []
  modified:
    - src/codexbot/search/live.py
    - src/codexbot/search/worker.py
    - src/codexbot/search/supervisor.py
    - src/codexbot/search/queue.py
    - src/codexbot/web/server.py
    - tests/codexbot/test_search_worker.py
    - tests/codexbot/test_search_live_queue.py
    - tests/codexbot/test_web_server.py
key-decisions:
  - "Live drain waits for an active generation and keeps queued rows durable until one exists."
  - "Small live batches flush after 60 seconds since the previous flush; 32 ready rows flush immediately."
  - "Failed rows require explicit requeue/rebuild controls rather than automatic retry on every restart."
patterns-established:
  - "Worker drains queue rows through leases and completes rows only after generation JSONL upsert succeeds."
  - "Stale transcript sources are recorded in queue state and filtered before normal v1 routing."
requirements-completed: [CORP-05, INDX-04, INDX-05, INDX-06, INDX-07]
duration: 45min
completed: 2026-05-22
---

# Phase 03: Plan 03 Summary

**Live queue worker converges queued transcript documents into generation JSONL with batching, retries, idempotent upsert, and stale-session filtering**

## Performance

- **Duration:** 45 min
- **Started:** 2026-05-22T01:15:00Z
- **Completed:** 2026-05-22T02:00:00Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments

- Added live queue drain behavior that flushes at 32 ready rows or after the 60-second timer.
- Added atomic generation `documents.jsonl` upsert keyed by stable `SearchRowIdentity`, with manifest counters updated after successful writes.
- Added bounded retry/dead-letter flow and explicit failed-row requeue helper coverage.
- Added stale-source helpers that compare generation document sources against currently open tmux/session sources and hide closed-session documents from normal routing.
- Started the live drain loop from web server lifecycle and cancelled it cleanly on shutdown.

## Task Commits

1. **Task 1 and 2: Drain/upsert/stale tests and implementation** - `e6336a3` (feat)

**Plan metadata:** this SUMMARY commit.

## Files Created/Modified

- `src/codexbot/search/worker.py` - Live drain loop, batching, retry/dead-letter handling, and CLI commands.
- `src/codexbot/search/live.py` - Atomic generation document upsert and stale-source helpers.
- `src/codexbot/search/supervisor.py` - Async live drain loop for backend lifecycle.
- `src/codexbot/search/queue.py` - Explicit failed-row requeue and stale-source state primitives.
- `src/codexbot/web/server.py` - Owned live worker task startup/shutdown.
- `tests/codexbot/test_search_worker.py` - Drain, upsert, retry, requeue, and supervisor coverage.
- `tests/codexbot/test_search_live_queue.py` - Stale-source filtering coverage.
- `tests/codexbot/test_web_server.py` - Live worker lifecycle coverage.

## Decisions Made

Live draining waits for an active generation instead of creating retrieval artifacts on the request path. Queued rows remain durable and converge after initial backfill activates a generation.

The upsert helper rewrites `documents.jsonl` atomically after merging by serialized row identity. This keeps the Phase 2 JSONL generation format intact while removing duplicate live/backfill rows.

## Deviations from Plan

The implementation keeps retrieval unavailable, as planned, and exposes stale filtering as helper behavior for the future retrieval phase rather than adding search result routing now.

## Issues Encountered

Pyright caught the startup replay task type as `Task[int]`; the web server handle now types replay separately from `Task[None]` lifecycle tasks.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

The derived search corpus now converges live transcript work into active generation documents. Phase 4 can build retrieval over current JSONL documents with queue lag/failure and stale-source state already available.

## Self-Check: PASSED

- `uv run pytest tests/codexbot/test_search_live_queue.py tests/codexbot/test_search_worker.py tests/codexbot/test_search_state.py tests/codexbot/test_web_api.py tests/codexbot/test_web_server.py -q` passed with 80 tests.
- `uv run pytest tests/codexbot/test_search_backfill.py tests/codexbot/test_session_monitor.py tests/codexbot/test_search_contracts.py -q` passed with 36 tests.
- `uv run ruff check src/ tests/`, `uv run ruff format --check src/ tests/`, and `uv run pyright src/codexbot/` passed.

---
*Phase: 03-live-queue-and-convergence*
*Completed: 2026-05-22*
