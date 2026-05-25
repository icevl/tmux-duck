---
phase: 03-live-queue-and-convergence
plan: 01
subsystem: search
tags: [sqlite, queue, status, watermarks]
requires:
  - phase: 02-open-session-backfill-scaffold
    provides: parser-backed search document DTOs and status scaffolding
provides:
  - durable SQLite live queue under CODEXBOT_DIR/search
  - transcript-source watermarks for restart recovery
  - queue-aware search status counters and degraded reasons
affects: [search-live-producer, search-worker, web-api-status]
tech-stack:
  added: []
  patterns: [stdlib sqlite queue, search-owned derived state]
key-files:
  created:
    - src/codexbot/search/queue.py
    - tests/codexbot/test_search_live_queue.py
  modified:
    - src/codexbot/search/contracts.py
    - src/codexbot/search/state.py
    - src/codexbot/search/client.py
    - tests/codexbot/test_search_state.py
    - tests/codexbot/test_search_contracts.py
key-decisions:
  - "Queue ids are deterministic hashes of SearchRowIdentity, separate from queue lifecycle state."
  - "Queue rows update document payloads idempotently but do not automatically requeue done or failed work."
  - "Search status reads queue summaries through the search client, while web/api.py avoids direct queue imports."
patterns-established:
  - "Search queue state lives exclusively under CODEXBOT_DIR/search/queue.sqlite."
  - "Request-path status exposes counts and sanitized queue errors, not transcript payloads."
requirements-completed: [INDX-04, INDX-06, INDX-07]
duration: 35min
completed: 2026-05-22
---

# Phase 03: Plan 01 Summary

**SQLite-backed live search queue with idempotent transcript row identity, leases, retries, watermarks, and safe status counters**

## Performance

- **Duration:** 35 min
- **Started:** 2026-05-22T00:00:00Z
- **Completed:** 2026-05-22T00:35:00Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments

- Added `queue.sqlite` under the search state directory with queue rows, lease state, queue errors, transcript watermarks, and stale-source markers.
- Added deterministic queue ids derived from stable `SearchRowIdentity`, so mutable routing metadata does not change row identity.
- Merged queue lag/failure counters into search status and kept `/api/search/status` behind the lightweight search client boundary.
- Added tests for queue ownership, duplicate enqueue, leasing, expired leases, bounded dead-letter behavior, watermarks, and safe status degradation.

## Task Commits

1. **Task 1 and 2: Durable queue tests and implementation** - `ceeaa1f` (feat)

**Plan metadata:** this SUMMARY commit.

## Files Created/Modified

- `src/codexbot/search/queue.py` - SQLite queue, lease, retry, watermark, and stale-source primitives.
- `src/codexbot/search/contracts.py` - Queue snapshot/status typing.
- `src/codexbot/search/state.py` - `queue_db_path()` helper.
- `src/codexbot/search/client.py` - Queue-aware search status construction.
- `tests/codexbot/test_search_live_queue.py` - Queue behavior coverage.
- `tests/codexbot/test_search_state.py` - Search-owned queue path coverage.
- `tests/codexbot/test_search_contracts.py` - Request-path import boundary coverage.

## Decisions Made

Queue rows use deterministic ids derived from `SearchRowIdentity` rather than tmux window metadata, because window id/name/cwd can change while the transcript-derived row must remain stable.

Failed rows are not automatically requeued by duplicate enqueue. They remain inspectable until explicit retry/rebuild controls requeue them, which avoids noisy poison-row loops.

## Deviations from Plan

None - plan scope stayed inside queue state, status counters, and import-boundary tests.

## Issues Encountered

Initial fake-clock lease tests exposed that queued rows should not depend on an absolute `available_at` timestamp. New rows and retry releases now use immediate availability.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 02 can now attach live monitor/replay producers to a durable queue with stable dedupe, bounded retry state, and status-visible lag/failure.

## Self-Check: PASSED

`uv run pytest tests/codexbot/test_search_live_queue.py tests/codexbot/test_search_state.py tests/codexbot/test_web_api.py tests/codexbot/test_search_contracts.py -q` passed with 70 tests.

---
*Phase: 03-live-queue-and-convergence*
*Completed: 2026-05-22*
