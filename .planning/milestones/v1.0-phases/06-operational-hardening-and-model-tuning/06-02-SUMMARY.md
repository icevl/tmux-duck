---
phase: 06-operational-hardening-and-model-tuning
plan: "02"
subsystem: search-failure-isolation
tags: [search, stale-heartbeat, degraded-mode, queue, supervisor]
requires:
  - phase: 06-01
    provides: Operational status contract and Web UI details
provides:
  - Stale heartbeat degradation coverage
  - Dead-letter queue continuation coverage
  - Semantic-to-lexical fallback coverage
  - Non-search request path isolation coverage
affects: [search, web-api, web-ui]
tech-stack:
  added: []
  patterns:
    - Derived search failures are represented as degraded status instead of global service failures
    - Supervisor startup/live-loop errors are contained behind the worker boundary
key-files:
  created:
    - .planning/phases/06-operational-hardening-and-model-tuning/06-02-SUMMARY.md
  modified:
    - tests/codexbot/test_search_worker.py
    - tests/codexbot/test_search_retrieval.py
    - tests/codexbot/test_web_api.py
    - tests/codexbot/test_web_ui_search_contract.py
key-decisions:
  - "A stale worker with an active generation remains search-available as degraded lexical status."
  - "Failed queue rows stay inspectable and are not converted to done just to unblock later rows."
  - "Session listing tests explicitly fail if search status or search execution is called."
patterns-established:
  - "Use monkeypatched failing search boundaries to prove non-search API routes stay isolated."
  - "Semantic failures are tested at retrieval level with sanitized lexical fallback payloads."
requirements-completed: [OPS-04, OPS-06]
duration: 3min
completed: 2026-05-25
---

# Phase 6 Plan 02: Stale And Degraded Failure Isolation Summary

**Stale workers, failed queue rows, semantic errors, and worker launch failures now have regression coverage that keeps normal Codi paths usable.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-05-25T11:38:40Z
- **Completed:** 2026-05-25T11:41:20Z
- **Tasks:** 4
- **Files modified:** 4

## Accomplishments

- Added stale-worker-with-generation coverage proving existing searchable data remains available as degraded lexical status.
- Added queue coverage proving dead-letter rows stay failed while later queued rows still drain successfully.
- Added semantic exception coverage proving LanceDB/provider failures fall back to sanitized lexical degraded results.
- Added supervisor and Web API isolation coverage proving subprocess launch failures, live-loop ordinary failures, and `/api/sessions` do not couple to search execution.
- Preserved the nonblocking degraded Web UI branch and asserted no acknowledgement gate is introduced.

## Task Commits

Each task was implemented as one cohesive plan commit in this inline execution path.

1. **Task 1: Failure behavior tests** - covered by this commit.
2. **Task 2: Stale/degraded status and queue isolation** - behavior already implemented in 06-01 and locked by this commit.
3. **Task 3: Non-search path isolation** - covered by this commit.
4. **Task 4: Nonblocking degraded labels** - covered by 06-01 UI implementation and this commit's static assertions.

## Files Created/Modified

- `tests/codexbot/test_search_worker.py` - Added stale-with-generation, failed-row continuation, and supervisor isolation tests.
- `tests/codexbot/test_search_retrieval.py` - Added semantic exception to lexical degraded fallback coverage.
- `tests/codexbot/test_web_api.py` - Added `/api/sessions` search-isolation coverage.
- `tests/codexbot/test_web_ui_search_contract.py` - Added degraded branch/no-acknowledgement assertions.

## Verification

- `uv run pytest -q tests/codexbot/test_search_worker.py tests/codexbot/test_search_live_queue.py tests/codexbot/test_search_retrieval.py tests/codexbot/test_web_api.py tests/codexbot/test_web_ui_search_contract.py` - 90 passed.
- `uv run ruff check src/codexbot/search/client.py src/codexbot/search/contracts.py src/codexbot/search/queue.py src/codexbot/search/retrieval.py src/codexbot/search/supervisor.py src/codexbot/search/worker.py tests/codexbot/test_search_contracts.py tests/codexbot/test_search_worker.py tests/codexbot/test_search_live_queue.py tests/codexbot/test_search_retrieval.py tests/codexbot/test_web_api.py tests/codexbot/test_web_ui_search_contract.py` - passed.
- `uv run pyright src/codexbot/search/client.py src/codexbot/search/retrieval.py src/codexbot/search/supervisor.py src/codexbot/search/worker.py` - 0 errors.
- `pnpm --dir web-ui build` - passed.

## Decisions Made

No additional production code changes were needed beyond 06-01 because stale/degraded derivation, operations preservation, and degraded UI labeling were already implemented there. This plan hardened them with targeted regression tests.

## Deviations from Plan

None - behavior matched the plan after 06-01 implementation, so this slice focused on missing regression coverage.

## Issues Encountered

None.

## User Setup Required

None.

## Next Phase Readiness

Ready for Plan 06-03 benchmark and model validation. The failure-mode contract is now covered before benchmark metadata is persisted into the same status details surface.

## Self-Check: PASSED

---
*Phase: 06-operational-hardening-and-model-tuning*
*Completed: 2026-05-25*
