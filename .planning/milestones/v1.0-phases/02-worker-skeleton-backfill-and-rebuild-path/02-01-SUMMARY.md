---
phase: 02-worker-skeleton-backfill-and-rebuild-path
plan: 01
subsystem: search-worker
tags: [search, worker, status, lifecycle, fastapi]
requires:
  - phase: 01-search-contract-and-status-surface
    provides: Lightweight search contracts, search-owned state namespace, and authenticated search/status API stubs
provides:
  - Local `codexbot-search-worker` CLI boundary
  - Search-owned worker status persistence under `CODEXBOT_DIR/search`
  - Nonblocking backend startup hook for initial search worker scheduling
  - `building` and failed worker status reporting through existing search status surfaces
affects: [search, web-server, status, phase-02]
tech-stack:
  added: []
  patterns: [search-owned worker status JSON, nonblocking startup task, dependency-light status reader]
key-files:
  created:
    - src/codexbot/search/worker.py
    - src/codexbot/search/supervisor.py
    - tests/codexbot/test_search_worker.py
  modified:
    - pyproject.toml
    - src/codexbot/search/__init__.py
    - src/codexbot/search/contracts.py
    - src/codexbot/search/state.py
    - src/codexbot/search/client.py
    - src/codexbot/web/server.py
    - tests/codexbot/test_search_contracts.py
    - tests/codexbot/test_web_api.py
    - tests/codexbot/test_web_server.py
key-decisions:
  - "Worker status is modeled as search-owned derived state and is not written to monitor_state.json or state.json."
  - "Backend startup schedules a supervisor task for the worker path instead of awaiting backfill work in the web startup path."
  - "Failed worker status is summarized for API callers without exposing raw exceptions, transcript bodies, secret names, or local paths."
patterns-established:
  - "Search worker process boundary: expose a console script and keep worker modules out of web API request imports."
  - "Status precedence: active running worker status reports `building` before active generation metadata is considered."
requirements-completed:
  - INDX-01
  - INDX-02
  - INDX-08
duration: 24 min
completed: 2026-05-21
---

# Phase 02 Plan 01: Worker Lifecycle and Status Skeleton Summary

**Local search worker CLI boundary with search-owned worker status and nonblocking backend startup scheduling**

## Performance

- **Duration:** 24 min
- **Started:** 2026-05-21T21:32:00Z
- **Completed:** 2026-05-21T21:56:19Z
- **Tasks:** 2
- **Files modified:** 12

## Accomplishments

- Added RED coverage for worker status persistence, `building` status, sanitized failures, the web server supervisor hook, and the worker CLI entrypoint.
- Added `SearchWorkerStatus`, worker status read/write helpers, and `codexbot-search-worker`.
- Wired `start_web_server()` to schedule `search_supervisor.start_worker_if_needed()` without waiting for backfill completion.
- Extended `search_client.get_status()` to report active worker backfill as `building` and failed worker state as typed `unavailable`.

## Task Commits

1. **Task 1: Lock worker lifecycle and building status behavior in tests** - `997b5b1` (test)
2. **Task 2: Implement worker CLI skeleton, supervisor hook, and status reads** - `1cc36d4` (feat)

## Files Created/Modified

- `src/codexbot/search/worker.py` - Local CLI skeleton that marks initial backfill as running.
- `src/codexbot/search/supervisor.py` - Nonblocking launcher used by backend startup when no active generation exists.
- `src/codexbot/search/contracts.py` - Adds `SearchWorkerStatus`.
- `src/codexbot/search/state.py` - Adds worker status path/read/write helpers under `CODEXBOT_DIR/search`.
- `src/codexbot/search/client.py` - Reads worker status and maps running/failed state into typed status responses.
- `src/codexbot/web/server.py` - Schedules the search supervisor task during web startup and cancels it on shutdown.
- `pyproject.toml` - Exposes `codexbot-search-worker`.
- `tests/codexbot/test_search_worker.py` - Worker state, status, sanitization, and CLI tests.
- `tests/codexbot/test_web_api.py` - Building status API coverage.
- `tests/codexbot/test_web_server.py` - Nonblocking supervisor scheduling coverage.
- `tests/codexbot/test_search_contracts.py` - Narrows request-path import-boundary checks to lightweight modules.

## Decisions Made

- The worker skeleton records `running` status and returns; real backfill work is added by the next plan.
- The supervisor launches the worker with `python -m codexbot.search.worker initial-backfill`, which keeps the boundary local and dependency-light.
- Status does not echo `recent_error`; it uses a stable sanitized failure reason.

## Deviations from Plan

None - plan executed exactly as written.

**Total deviations:** 0 auto-fixed.
**Impact on plan:** No scope changes.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Ready for `02-02`: the backend can now schedule a search worker path and expose worker status, so the next plan can attach parser-backed open-session backfill and inactive generation artifacts.

---
*Phase: 02-worker-skeleton-backfill-and-rebuild-path*
*Completed: 2026-05-21*
