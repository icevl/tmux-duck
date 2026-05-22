---
phase: 03-live-queue-and-convergence
plan: 02
subsystem: search
tags: [live-indexing, transcript-parser, queue, watermarks]
requires:
  - phase: 03-live-queue-and-convergence
    provides: durable SQLite search queue from plan 03-01
provides:
  - nonblocking SessionMonitor listener for live search enqueue
  - shared backfill document builder for one parsed entry
  - open-session replay from search-owned transcript watermarks
affects: [search-worker, web-server-lifecycle, session-monitor]
tech-stack:
  added: []
  patterns: [monitor listener fanout, async to_thread queue persistence]
key-files:
  created:
    - src/codexbot/search/live.py
  modified:
    - src/codexbot/search/backfill.py
    - src/codexbot/search/queue.py
    - src/codexbot/web/server.py
    - tests/codexbot/test_search_live_queue.py
    - tests/codexbot/test_search_backfill.py
    - tests/codexbot/test_web_server.py
key-decisions:
  - "Live producer resolves monitor messages back to parser transcript source metadata before queueing."
  - "Replay advances watermarks only after enqueue succeeds for an entry."
  - "Web server owns the search live listener and replay task, removing/cancelling them during shutdown."
patterns-established:
  - "Live queue work is scheduled from monitor fanout and persisted via asyncio.to_thread."
  - "Backfill and live code share the same parsed-entry document builder and chunking constants."
requirements-completed: [INDX-04, INDX-06, INDX-07]
duration: 40min
completed: 2026-05-22
---

# Phase 03: Plan 02 Summary

**Live transcript producer and restart replay feed useful parsed transcript entries into the durable search queue without blocking message delivery**

## Performance

- **Duration:** 40 min
- **Started:** 2026-05-22T00:35:00Z
- **Completed:** 2026-05-22T01:15:00Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Exposed public backfill helpers for creating `SearchBackfillDocument` chunks from a single parsed entry.
- Added `LiveQueueProducer`, a nonblocking `SessionMonitor` listener that queues useful monitor messages and records sanitized producer failures.
- Added replay from search-owned transcript watermarks for current open sessions, keyed by transcript source and parser coordinates.
- Wired web server startup/shutdown to attach/remove the live queue listener and own the replay task.

## Task Commits

1. **Task 1 and 2: Live producer/replay tests and implementation** - `516bd99` (feat)

**Plan metadata:** this SUMMARY commit.

## Files Created/Modified

- `src/codexbot/search/live.py` - Live queue producer, monitor-message conversion, and watermark replay.
- `src/codexbot/search/backfill.py` - Public parsed-entry document builder helpers.
- `src/codexbot/search/queue.py` - Sanitization hardening used by live producer errors.
- `src/codexbot/web/server.py` - Search producer listener and replay lifecycle wiring.
- `tests/codexbot/test_search_live_queue.py` - Live producer and replay behavior tests.
- `tests/codexbot/test_search_backfill.py` - Shared document builder coverage.
- `tests/codexbot/test_web_server.py` - Web lifecycle listener ownership coverage.

## Decisions Made

The live producer resolves the active parsed transcript source from `session_id` before queueing so row provenance stays transcript-derived rather than Web UI history-derived.

Replay updates watermarks after each successfully enqueued parsed entry, so a queue write failure leaves the coordinate replayable on the next startup.

## Deviations from Plan

None - the implementation stayed limited to live enqueue/replay and web lifecycle ownership.

## Issues Encountered

The existing queue sanitizer masked secret variable names but not assigned values. Producer failure tests tightened that behavior so status errors no longer include secret values.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 03 can now drain a durable queue that is fed by live monitor events and conservative replay from search watermarks.

## Self-Check: PASSED

`uv run pytest tests/codexbot/test_search_live_queue.py tests/codexbot/test_search_backfill.py tests/codexbot/test_session_monitor.py tests/codexbot/test_web_server.py -q` passed with 38 tests.

---
*Phase: 03-live-queue-and-convergence*
*Completed: 2026-05-22*
