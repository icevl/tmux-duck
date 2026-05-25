---
phase: 01-search-contract-and-status-surface
plan: 01
subsystem: backend
tags: [search, contracts, pydantic, provenance, pytest]

requires: []
provides:
  - Runtime-neutral search provenance, identity, request, status, and response DTOs
  - Contract tests for provenance coverage, identity/routing separation, input bounds, lifecycle states, generation metadata, and import boundaries
affects: [phase-01, phase-02, phase-03, phase-04, phase-05, search-contracts, search-api]

tech-stack:
  added: []
  patterns:
    - Lightweight Pydantic v2 DTOs under src/codexbot/search/
    - AST import-boundary regression tests for request-path modules

key-files:
  created:
    - src/codexbot/search/__init__.py
    - src/codexbot/search/contracts.py
    - tests/codexbot/test_search_contracts.py
  modified: []

key-decisions:
  - "SearchRowIdentity derives from transcript provenance and chunk index while routing/display metadata lives in SearchRoutingMetadata."
  - "Search contracts stay import-light and do not pull worker, retrieval, index, embedding, or model packages into request-path modules."

patterns-established:
  - "Contract DTOs: define API/worker shared search shapes in src/codexbot/search/contracts.py using Pydantic BaseModel and Field bounds."
  - "Import-boundary tests: parse Python imports with ast instead of grep so comments and prose do not trigger false positives."

requirements-completed: [CORP-03, CORP-04]

duration: 6min
completed: 2026-05-21
---

# Phase 01 Plan 01: Search Contract and Status Surface Summary

**Runtime-neutral search contracts with stable transcript provenance, chunk-row identity, bounded request inputs, status lifecycle semantics, and import-boundary tests**

## Performance

- **Duration:** 6 min
- **Started:** 2026-05-21T13:11:01Z
- **Completed:** 2026-05-21T13:16:33Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Added RED tests for provenance coverage, mutable routing separation, bounded search requests, lifecycle states, D-05 typed not-ready status, D-11 generation metadata, and request-path import hygiene.
- Added `codexbot.search` contract package with lightweight Pydantic DTOs only.
- Proved `SearchRowIdentity` excludes mutable `window_id`, cwd, name, status, pinned, and sort metadata while supporting multiple chunks for one transcript message.
- Proved `SearchRequest` rejects oversized query text and out-of-range result limits.

## Task Commits

Each task was committed atomically:

1. **Task 1: Lock search contract behavior in tests** - `a17b28e` (test)
2. **Task 2: Implement runtime-neutral search contracts** - `dae2cd0` (feat)

**Plan metadata:** recorded by the commit that adds this summary and updates planning state.

## Files Created/Modified

- `src/codexbot/search/__init__.py` - Re-exports only lightweight search contract names for request-path imports.
- `src/codexbot/search/contracts.py` - Defines search provenance, row identity, routing metadata, generation metadata, counters, status, hit/session result, request, and response DTOs.
- `tests/codexbot/test_search_contracts.py` - Locks contract behavior and static import boundaries.

## Decisions Made

- Kept `TranscriptProvenance` as the complete source-coordinate contract and `SearchRowIdentity` as the chunk identity subset, so mutable routing/display fields cannot affect indexed row identity.
- Used Pydantic `Field` bounds for query length and result caps to satisfy T-01-02 before any retrieval path exists.
- Kept `SearchStatusResponse` limited to state, availability, `open_sessions` scope, reason, nullable counters, and nullable generation metadata to avoid exposing transcript text or secrets.

## Deviations from Plan

None - plan executed as written.

## Issues Encountered

None.

## Authentication Gates

None.

## Known Stubs

None.

## Threat Scan

No new network endpoints, auth paths, file access patterns, or schema changes were introduced. The plan-created trust-boundary DTOs include the mitigations from T-01-02, T-01-03, T-01-04, and T-01-05.

## Verification

- `uv run pytest tests/codexbot/test_search_contracts.py -q` - PASS, 8 tests.
- `uv run ruff check src/ tests/` - PASS.
- `uv run ruff format --check src/ tests/` - PASS, 72 files already formatted.
- `uv run pyright src/codexbot/` - PASS, 0 errors.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Plan 01-02 can consume `codexbot.search.contracts` to reserve search-owned derived state and missing-index provider behavior. The contracts do not introduce worker/index dependencies into the FastAPI request path.

## Self-Check: PASSED

- Created files exist: `src/codexbot/search/__init__.py`, `src/codexbot/search/contracts.py`, `tests/codexbot/test_search_contracts.py`, and this summary.
- Task commits exist: `a17b28e` and `dae2cd0`.
- Final verification commands passed.

---
*Phase: 01-search-contract-and-status-surface*
*Completed: 2026-05-21*
