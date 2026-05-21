---
phase: 01-search-contract-and-status-surface
plan: 02
subsystem: backend
tags: [search, state, provider, pydantic, pytest]

requires:
  - phase: 01-search-contract-and-status-surface
    provides: Runtime-neutral search contracts from plan 01-01
provides:
  - Search-owned derived state namespace under CODEXBOT_DIR/search
  - Generation metadata helpers for active current-schema search index state
  - Dependency-light missing-index status and search provider responses
affects: [phase-01, phase-02, phase-03, phase-04, phase-05, search-state, search-api]

tech-stack:
  added: []
  patterns:
    - Search runtime metadata is isolated under codexbot_dir() / "search"
    - Missing-index search is represented as typed normal DTOs

key-files:
  created:
    - src/codexbot/search/state.py
    - src/codexbot/search/client.py
    - tests/codexbot/test_search_state.py
  modified:
    - src/codexbot/search/contracts.py
    - src/codexbot/search/__init__.py

key-decisions:
  - "Search-owned runtime state resolves only under codexbot_dir() / 'search' and never writes monitor_state.json."
  - "Missing-index status/search responses are typed normal responses with outcome not_ready and no transcript, secret, or local path leakage."
  - "SearchResponse now echoes total_results, limit, hits_per_session, and outcome to match the approved provider/API contract."

patterns-established:
  - "State helper pattern: read optional generation metadata through src/codexbot/search/state.py and treat missing, invalid, inactive, or schema-mismatched data as absent."
  - "Provider stub pattern: src/codexbot/search/client.py returns safe missing/not-ready DTOs without worker, retrieval, model, tmux, FastAPI, or monitor-state imports."

requirements-completed: [CORP-06]

duration: 6min
completed: 2026-05-21
---

# Phase 01 Plan 02: Search State and Missing-Index Provider Summary

**Search-owned derived state under CODEXBOT_DIR/search with safe typed missing-index status and not-ready search responses**

## Performance

- **Duration:** 6 min
- **Started:** 2026-05-21T13:22:19Z
- **Completed:** 2026-05-21T13:28:53Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added RED tests proving search state resolves under `CODEXBOT_DIR/search`, generation metadata is derived/rebuildable, status/search calls do not mutate `monitor_state.json`, and missing-index responses are safe typed JSON.
- Added `src/codexbot/search/state.py` with `SEARCH_SCHEMA_VERSION`, `search_dir()`, `generation_metadata_path()`, and `read_generation_metadata()`.
- Added `src/codexbot/search/client.py` with dependency-light `get_status()` and `search()` provider functions for typed missing/not-ready responses.
- Extended `SearchResponse` with the approved provider/API response fields required by this plan and plan 01-03.

## Task Commits

Each task was committed atomically:

1. **Task 1: Lock search-state isolation and missing-index behavior in tests** - `4b66225` (test)
2. **Task 2: Implement search-owned state helpers and typed provider** - `17bda7d` (feat)

**Plan metadata:** recorded by the commit that adds this summary and updates planning state.

## Files Created/Modified

- `tests/codexbot/test_search_state.py` - Covers CODEXBOT_DIR/search resolution, generation metadata filtering, monitor-state isolation, and safe missing-index status/search JSON.
- `src/codexbot/search/state.py` - Owns search state path helpers and active generation metadata reads.
- `src/codexbot/search/client.py` - Returns typed status/search provider responses without hot-path or worker dependencies.
- `src/codexbot/search/contracts.py` - Adds `SearchResponseOutcome`, `total_results`, echoed limits, and `outcome`.
- `src/codexbot/search/__init__.py` - Re-exports the lightweight `SearchResponseOutcome` contract type.

## Decisions Made

- Kept generation metadata reads tolerant: missing, unreadable, invalid, inactive, or schema-mismatched metadata returns `None` instead of raising on the request path.
- Returned `counters=None` for missing-index status unless an open-session count is provided by the caller.
- Preserved the provider as a pure typed boundary; it does not import monitor state, config state files, tmux, FastAPI, worker, retrieval, ranking, queue, or embedding/model libraries.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added missing SearchResponse provider fields**
- **Found during:** Task 2 (Implement search-owned state helpers and typed provider)
- **Issue:** Plan 01-02 and the later API plan require `SearchResponse(query, status, results, total_results, limit, hits_per_session, outcome)`, but plan 01-01's committed contract only exposed `total_sessions` and had no response outcome or echoed limits.
- **Fix:** Added `SearchResponseOutcome`, `total_results`, `limit`, `hits_per_session`, and `outcome` to the lightweight contract and re-exported the new type.
- **Files modified:** `src/codexbot/search/contracts.py`, `src/codexbot/search/__init__.py`
- **Verification:** `uv run pytest tests/codexbot/test_search_state.py tests/codexbot/test_search_contracts.py -q` passed.
- **Committed in:** `17bda7d`

---

**Total deviations:** 1 auto-fixed (Rule 2)
**Impact on plan:** Required to satisfy the approved provider/API response contract; no worker, retrieval, route, or UI scope was added.

## Issues Encountered

None beyond the auto-fixed contract field gap documented above.

## Authentication Gates

None.

## Known Stubs

- `src/codexbot/search/client.py:47` - Intentional Phase 1 provider stub. `search()` returns an empty typed `not_ready` response until later worker/retrieval phases implement real query execution. This is the planned D-05/D-07 behavior and does not block this plan's goal.

## Threat Scan

No unplanned security-relevant surfaces were introduced. The new file-access boundary is the planned search-owned derived state namespace under `CODEXBOT_DIR/search`; tests prove status/search calls do not create or mutate `monitor_state.json`, and missing-index status omits raw transcript content, secret names/values, and full local temp paths.

## Verification

- `uv run pytest tests/codexbot/test_search_state.py -q` - RED gate PASS as expected before implementation: 6 failures, all missing `codexbot.search.state` or `codexbot.search.client`.
- `uv run pytest tests/codexbot/test_search_state.py tests/codexbot/test_search_contracts.py -q` - PASS, 14 tests.
- `uv run pytest tests/codexbot/test_search_contracts.py tests/codexbot/test_search_state.py tests/codexbot/test_web_api.py -q` - PASS, 46 tests.
- `uv run ruff check src/ tests/` - PASS.
- `uv run ruff format --check src/ tests/` - PASS, 75 files already formatted.
- `uv run pyright src/codexbot/` - PASS, 0 errors.
- `uv run pytest -q` - PASS, 493 tests, 2 existing Telegram deprecation warnings.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 01-03 can wire authenticated search/status API routes to `codexbot.search.client` while keeping FastAPI request handlers free of worker, retrieval, indexing, and embedding/model dependencies.

## Self-Check: PASSED

- Created files exist: `src/codexbot/search/state.py`, `src/codexbot/search/client.py`, `tests/codexbot/test_search_state.py`, and this summary.
- Task commits exist: `4b66225` and `17bda7d`.
- Final verification commands passed.

---
*Phase: 01-search-contract-and-status-surface*
*Completed: 2026-05-21*
