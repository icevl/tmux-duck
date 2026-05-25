---
phase: 06-operational-hardening-and-model-tuning
plan: "01"
subsystem: search-operations-ui
tags: [search, web-ui, status-contract, operations]
requires:
  - phase: 05-web-ui-search-experience-and-navigation
    provides: Open-session search panel and result navigation
provides:
  - Typed operational search status DTOs
  - Request-safe status derivation with worker, queue, progress, and recovery data
  - Accessible expandable Web UI search status details
affects: [search, web-ui, operations]
tech-stack:
  added: []
  patterns:
    - Lightweight search client boundary remains the Web API integration point
    - Sidebar status details stay read-only and polling-based
key-files:
  created:
    - .planning/phases/06-operational-hardening-and-model-tuning/06-01-SUMMARY.md
  modified:
    - src/codexbot/search/contracts.py
    - src/codexbot/search/client.py
    - src/codexbot/search/queue.py
    - web-ui/src/api.ts
    - web-ui/src/components/SessionSearch.tsx
    - web-ui/src/styles.css
    - tests/codexbot/test_search_contracts.py
    - tests/codexbot/test_search_worker.py
    - tests/codexbot/test_web_api.py
    - tests/codexbot/test_web_ui_search_contract.py
key-decisions:
  - "Operational details are derived in search.client so Web API routes keep a single lightweight search boundary."
  - "Web recovery controls are command text only; the browser does not trigger rebuilds in this phase."
  - "Traceback headers are stripped by the shared search sanitizer before surfacing recent errors."
patterns-established:
  - "SearchStatusResponse.operations carries worker, queue, progress, errors, recovery commands, and nullable benchmark data."
  - "SessionSearch polls /api/search/status every 10 seconds while mounted and keeps details hidden behind Show details."
requirements-completed: [OPS-03, OPS-06]
duration: 16min
completed: 2026-05-25
---

# Phase 6 Plan 01: Operational Status Contract And Web UI Details Summary

**Operational search status details now flow from typed backend contracts into an accessible expandable Web UI sidebar panel.**

## Performance

- **Duration:** 16 min
- **Started:** 2026-05-25T11:22:40Z
- **Completed:** 2026-05-25T11:38:40Z
- **Tasks:** 4
- **Files modified:** 10

## Accomplishments

- Added typed operational status DTOs for worker heartbeat, queue lag, backfill progress, recent errors, recovery commands, and benchmark metadata.
- Extended `get_status()` to derive request-safe operational details while preserving the lightweight Web API search client boundary.
- Rendered `Show details` / `Hide details` controls, status rows, degraded lexical copy, and compact desktop/mobile styling in `SessionSearch`.
- Tightened search error sanitization so traceback headers, secrets, and local paths do not leak through operational details.

## Task Commits

Each task was implemented as one cohesive plan commit in this inline execution path.

1. **Task 1: Operational status contract/API tests** - covered by this commit.
2. **Task 2: Backend DTOs and status derivation** - covered by this commit.
3. **Task 3: Web UI DTOs and details rendering** - covered by this commit.
4. **Task 4: Details styling and mobile constraints** - covered by this commit.

## Files Created/Modified

- `src/codexbot/search/contracts.py` - Added operational health/status DTOs and `SearchStatusResponse.operations`.
- `src/codexbot/search/client.py` - Derives operations data, stale heartbeat state, sanitized errors, and recovery commands.
- `src/codexbot/search/queue.py` - Strips traceback headers from status-safe error summaries.
- `web-ui/src/api.ts` - Mirrors the new operations DTOs for frontend code.
- `web-ui/src/components/SessionSearch.tsx` - Adds polling, accessible details toggle, details rows, and degraded lexical result copy.
- `web-ui/src/styles.css` - Adds compact desktop/mobile styling for status details.
- `tests/codexbot/test_search_contracts.py` - Covers operations DTO shape.
- `tests/codexbot/test_search_worker.py` - Covers building, stale heartbeat, and sanitized failure payloads.
- `tests/codexbot/test_web_api.py` - Covers operations data in authenticated search status responses.
- `tests/codexbot/test_web_ui_search_contract.py` - Covers polling, copy, details controls, and mobile selectors.

## Verification

- `uv run pytest -q tests/codexbot/test_search_contracts.py tests/codexbot/test_search_worker.py tests/codexbot/test_web_api.py tests/codexbot/test_web_ui_search_contract.py` - 78 passed.
- `uv run ruff check src/codexbot/search/contracts.py src/codexbot/search/client.py src/codexbot/search/queue.py tests/codexbot/test_search_contracts.py tests/codexbot/test_search_worker.py tests/codexbot/test_web_api.py tests/codexbot/test_web_ui_search_contract.py` - passed.
- `uv run pyright src/codexbot/search/client.py src/codexbot/search/contracts.py` - 0 errors.
- `pnpm --dir web-ui build` - passed.

## Decisions Made

Operational status stays behind `search.client.get_status()` rather than adding Web API imports from search implementation modules.

Recovery remains read-only command text in the browser because local rebuilds can be expensive and should stay operator-controlled.

## Deviations from Plan

Auto-fixed one sanitizer gap: traceback headers were previously safe for plain status reasons but became visible through the new details payload. The shared search sanitizer now collapses traceback-headed strings to `search error`.

## Issues Encountered

The repo-specific `/tmp/codexbot-venv/bin/pytest` path is not present in this environment, so focused tests were run with `uv run pytest`.

## User Setup Required

None.

## Next Phase Readiness

Ready for Plan 06-02 stale/degraded failure isolation. The status contract now has the fields needed for deeper stale/queue degradation and benchmark exposure.

## Self-Check: PASSED

---
*Phase: 06-operational-hardening-and-model-tuning*
*Completed: 2026-05-25*
