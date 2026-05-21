---
phase: 02-worker-skeleton-backfill-and-rebuild-path
plan: 03
subsystem: search-worker
tags: [search, worker, rebuild, activation, recovery, status]
requires:
  - phase: 02-worker-skeleton-backfill-and-rebuild-path
    provides: Parser-backed open-session backfill documents and inactive generation manifests
provides:
  - Atomic active generation metadata activation after complete backfill manifests
  - Local `codexbot-search-worker rebuild` command for explicit rebuilds
  - Recovery behavior that ignores incomplete generation manifests
  - Built-but-unqueryable status with active generation metadata and manifest counters
affects: [search, worker, status, phase-02]
tech-stack:
  added: []
  patterns: [inactive-build-then-activate, local-only rebuild command, manifest-backed status counters]
key-files:
  created: []
  modified:
    - src/codexbot/search/contracts.py
    - src/codexbot/search/state.py
    - src/codexbot/search/client.py
    - src/codexbot/search/worker.py
    - src/codexbot/search/backfill.py
    - tests/codexbot/test_search_worker.py
    - tests/codexbot/test_search_state.py
    - tests/codexbot/test_web_api.py
key-decisions:
  - "Active generation metadata is written only after a complete manifest and document artifact exist."
  - "Explicit rebuild is a local worker CLI command, not a Web UI/API control."
  - "Completed Phase 2 backfill reports active generation metadata but remains available=false until retrieval is implemented."
patterns-established:
  - "Generation activation: materialize inactive documents/manifest, validate completion, then atomically write active generation.json."
  - "Status counters: active generation status reads counters from the completed manifest and overlays the live open-session count."
requirements-completed:
  - INDX-01
  - INDX-02
  - INDX-03
  - INDX-08
duration: 7 min
completed: 2026-05-21
---

# Phase 02 Plan 03: Worker Skeleton Backfill and Rebuild Path Summary

**Atomic search generation activation with local rebuild and built-but-unavailable status**

## Performance

- **Duration:** 7 min
- **Started:** 2026-05-21T22:07:25Z
- **Completed:** 2026-05-21T22:14:07Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- Added tests for success-only generation activation, incomplete generation recovery, startup scheduling, explicit rebuild, and HTTP status/search behavior after backfill.
- Added completed manifest validation and atomic active `generation.json` writes under `CODEXBOT_DIR/search`.
- Added local `codexbot-search-worker rebuild` support that creates and activates a fresh generation without mutating the previous generation in place.
- Extended search status to report active generation metadata and manifest counters while keeping search `available=false` and `outcome=not_ready`.

## Task Commits

1. **Task 1: Lock atomic rebuild, recovery, and final status behavior in tests** - `6eac84a` (test)
2. **Task 2: Implement explicit rebuild, atomic activation, recovery, and counters** - `a3a3a88` (feat)

## Files Created/Modified

- `src/codexbot/search/contracts.py` - Adds `completed` to backfill manifests.
- `src/codexbot/search/state.py` - Adds manifest read/write helpers and atomic generation activation.
- `src/codexbot/search/client.py` - Reads active manifest counters for built-but-unqueryable status.
- `src/codexbot/search/worker.py` - Activates successful backfills and adds explicit `rebuild`.
- `src/codexbot/search/backfill.py` - Writes manifests through search state helpers.
- `tests/codexbot/test_search_worker.py` - Worker rebuild and startup scheduling tests.
- `tests/codexbot/test_search_state.py` - Activation, recovery, and manifest counter tests.
- `tests/codexbot/test_web_api.py` - HTTP built-but-unavailable status/search contract test.

## Decisions Made

- Incomplete manifests are ignored by `read_generation_manifest()` and cannot be activated.
- `read_generation_metadata()` remains focused on the active metadata file; incomplete generation directories have no effect unless activation succeeds.
- Status overlays live `open_sessions` onto manifest counters so the response reflects current windows without rewriting generation artifacts.

## Deviations from Plan

None - plan executed exactly as written.

**Total deviations:** 0 auto-fixed.
**Impact on plan:** No scope changes.

## Issues Encountered

The documented `/tmp/codexbot-venv/bin/pytest` gate binary is absent in this environment. Validation used `uv run pytest -q`, which is the working repo test lane used by the earlier phase gates.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Phase 2 is ready for verification: search storage can be built and rebuilt safely, but querying remains intentionally unavailable until later retrieval/index phases.

---
*Phase: 02-worker-skeleton-backfill-and-rebuild-path*
*Completed: 2026-05-21*
