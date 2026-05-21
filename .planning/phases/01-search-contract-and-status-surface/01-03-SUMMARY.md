---
phase: 01-search-contract-and-status-surface
plan: 03
subsystem: backend
tags: [search, api, fastapi, auth, pytest]

requires:
  - phase: 01-search-contract-and-status-surface
    provides: Runtime-neutral search contracts from plan 01-01
  - phase: 01-search-contract-and-status-surface
    provides: Missing-index search provider from plan 01-02
provides:
  - Authenticated GET /api/search/status route with typed missing-index status
  - Authenticated POST /api/search route with bounded request validation and typed not-ready response
  - Web API tests proving auth, validation, counters, response safety, and import boundaries
affects: [phase-01, phase-05, search-api, web-api, OPS-02]

tech-stack:
  added: []
  patterns:
    - FastAPI search routes delegate to lightweight search contracts/provider modules only
    - Open-session counters are derived from tmux window state at request time

key-files:
  created: []
  modified:
    - src/codexbot/web/api.py
    - tests/codexbot/test_web_api.py

key-decisions:
  - "Search API routes use the existing Web UI cookie auth dependency and return typed 200 missing/not-ready responses for first-run search state."
  - "Open-session counters are derived by listing current tmux windows at request time; tmux-listing failures omit the counter without leaking exception details."
  - "FastAPI search handlers import only lightweight search contracts and provider stubs, keeping model/index dependencies outside request handling."

patterns-established:
  - "Authenticated search route pattern: protect /api/search/status and /api/search with Depends(require_auth), then return Pydantic DTO model_dump(mode='json')."
  - "Counter context pattern: derive open_sessions from tmux_manager.list_windows() inside the route and pass it as nullable context to the search provider."

requirements-completed: [OPS-02]

duration: 4min
completed: 2026-05-21
---

# Phase 01 Plan 03: Search API Routes Summary

**Authenticated FastAPI search/status surfaces with typed missing-index semantics and request-path import-boundary coverage**

## Performance

- **Duration:** 4 min
- **Started:** 2026-05-21T13:35:50Z
- **Completed:** 2026-05-21T13:39:55Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added Web API tests for unauthenticated rejection, typed authenticated status, typed not-ready search response, Pydantic request validation, and response redaction.
- Added authenticated `GET /api/search/status` and `POST /api/search` routes to the existing FastAPI app.
- Wired both routes to lightweight search contracts/provider modules and request-time tmux open-session counts.
- Preserved the Phase 1 boundary: no LanceDB, embedding, worker, retrieval, Telegram search, or Web UI rendering implementation was added.

## Task Commits

Each task was committed atomically:

1. **Task 1: Lock authenticated search API behavior in tests** - `3d07c43` (test)
2. **Task 2: Wire authenticated search/status FastAPI routes** - `e9472e4` (feat)

**Plan metadata:** recorded by the commit that adds this summary and updates planning state.

## Files Created/Modified

- `tests/codexbot/test_web_api.py` - Adds authenticated search status/search route tests, request validation tests, and safe-response assertions.
- `src/codexbot/web/api.py` - Adds lightweight search imports, nullable open-session counter derivation, and authenticated search/status routes.

## Decisions Made

- Reused the existing Web UI `require_auth` dependency for both search endpoints instead of adding search-specific authentication.
- Counted open sessions from `tmux_manager.list_windows()` during each search/status request so status reflects current tmux state.
- Treated tmux listing errors as missing counter context rather than response failures, preserving typed missing/not-ready search semantics without exposing local exception details.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- RED verification behaved as intended before route implementation: `GET /api/search/status` fell through to the SPA fallback and `POST /api/search` returned 405 because the routes were missing.

## Authentication Gates

None.

## Known Stubs

- `src/codexbot/web/api.py:581` - The search route intentionally delegates to the Phase 1 typed not-ready provider until later worker/retrieval phases implement real search. This is the planned D-05/D-07 behavior and does not block OPS-02.

## Threat Scan

The new network/auth surfaces are the planned `GET /api/search/status` and `POST /api/search` routes from the plan threat model. Tests prove both require authentication, bounded requests return 422, responses omit sensitive/transcript/model details, and request-path imports avoid heavy model/index modules. No unplanned security-relevant surface was introduced.

## Verification

- RED: `uv run pytest tests/codexbot/test_web_api.py::test_search_status_requires_auth tests/codexbot/test_web_api.py::test_search_requires_auth tests/codexbot/test_web_api.py::test_search_status_returns_typed_missing tests/codexbot/test_web_api.py::test_search_stub_returns_typed_not_ready tests/codexbot/test_web_api.py::test_search_rejects_oversized_or_out_of_range_request tests/codexbot/test_web_api.py::test_search_responses_do_not_leak_sensitive_fields -q` - PASS as RED signal, 10 failures caused by missing route wiring.
- GREEN: `uv run pytest tests/codexbot/test_web_api.py::test_search_status_requires_auth tests/codexbot/test_web_api.py::test_search_requires_auth tests/codexbot/test_web_api.py::test_search_status_returns_typed_missing tests/codexbot/test_web_api.py::test_search_stub_returns_typed_not_ready tests/codexbot/test_web_api.py::test_search_rejects_oversized_or_out_of_range_request tests/codexbot/test_web_api.py::test_search_responses_do_not_leak_sensitive_fields tests/codexbot/test_search_contracts.py::test_web_search_boundary_has_no_heavy_imports -q` - PASS, 11 tests.
- `uv run pytest tests/codexbot/test_search_contracts.py tests/codexbot/test_search_state.py tests/codexbot/test_web_api.py -q` - PASS, 56 tests.
- `uv run ruff check src/ tests/` - PASS.
- `uv run ruff format --check src/ tests/` - PASS, 75 files already formatted.
- `uv run pyright src/codexbot/` - PASS, 0 errors.
- `uv run pytest -q` - PASS, 503 tests, 2 existing Telegram deprecation warnings.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 1 now exposes the backend search/status API contract required by later worker, retrieval, and Web UI phases. Phase 2 can build asynchronous open-session indexing against the established contracts without changing request-path auth or missing-index semantics.

## Self-Check: PASSED

- Created/modified files exist: `src/codexbot/web/api.py`, `tests/codexbot/test_web_api.py`, and this summary.
- Task commits exist: `3d07c43` and `e9472e4`.
- Final verification commands passed.

---
*Phase: 01-search-contract-and-status-surface*
*Completed: 2026-05-21*
