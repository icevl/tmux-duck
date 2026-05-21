---
phase: 02-worker-skeleton-backfill-and-rebuild-path
plan: 02
subsystem: search-backfill
tags: [search, backfill, transcripts, tmux, parser, worker]
requires:
  - phase: 02-worker-skeleton-backfill-and-rebuild-path
    provides: Local search worker CLI boundary, worker status, and startup supervisor
provides:
  - Parser-backed open-session backfill source for current tmux windows
  - Stable chunk document identities based on transcript provenance and chunk index
  - Inactive generation artifact writer under `CODEXBOT_DIR/search/generations`
  - Worker path that materializes initial inactive backfill generations and reports completion
affects: [search, worker, transcript-parser, session-state, phase-02]
tech-stack:
  added: []
  patterns: [parser-backed corpus source, search-owned generation artifacts, chunk identity from transcript provenance]
key-files:
  created:
    - src/codexbot/search/backfill.py
    - tests/codexbot/test_search_backfill.py
  modified:
    - src/codexbot/session.py
    - src/codexbot/search/contracts.py
    - src/codexbot/search/state.py
    - src/codexbot/search/worker.py
    - src/codexbot/search/__init__.py
    - tests/codexbot/test_search_worker.py
key-decisions:
  - "Backfill enumerates only currently open tmux windows and asks SessionManager to resolve parser-backed transcript entries."
  - "Web UI history snapshots remain out of the search corpus path; parser-level ParsedEntry values are the source of truth."
  - "Generation documents and manifests are written as inactive derived artifacts under CODEXBOT_DIR/search/generations, leaving active generation metadata untouched."
patterns-established:
  - "Open-session corpus collection: tmux window list -> SessionManager parsed transcript helper -> chunk documents."
  - "Stable row identity: transcript provenance plus chunk_index, with mutable window metadata stored separately as routing metadata."
requirements-completed:
  - CORP-01
  - CORP-02
  - INDX-03
duration: 10 min
completed: 2026-05-21
---

# Phase 02 Plan 02: Worker Skeleton Backfill and Rebuild Path Summary

**Parser-backed open-session search backfill with inactive generation artifacts**

## Performance

- **Duration:** 10 min
- **Started:** 2026-05-21T21:56:40Z
- **Completed:** 2026-05-21T22:06:37Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- Added RED coverage for parser-backed session resolution, current tmux-window enumeration, Codex and Claude transcript handling, text-bearing parsed entry coverage, chunk identity, and inactive generation artifacts.
- Added `SessionManager.read_parsed_transcript_for_window()` so search backfill can share the transcript parser without depending on Web UI history DTOs.
- Added `src/codexbot/search/backfill.py` to collect current open sessions, chunk parsed entries, attach transcript provenance/routing metadata, and write inactive `documents.jsonl` plus `manifest.json`.
- Updated the worker to materialize an initial inactive generation and report completed or failed worker status through the existing status file.

## Task Commits

1. **Task 1: Lock open-session backfill source and chunking in tests** - `5901eb4` (test)
2. **Task 2: Implement parser-backed open-session backfill and inactive document artifacts** - `7eeaed3` (feat)

## Files Created/Modified

- `src/codexbot/search/backfill.py` - Open-session corpus collector, chunk document builder, and inactive generation materializer.
- `src/codexbot/session.py` - Adds a reusable parsed-transcript helper for search backfill.
- `src/codexbot/search/contracts.py` - Adds backfill document and manifest DTOs.
- `src/codexbot/search/state.py` - Adds generation directory, manifest, and document path helpers.
- `src/codexbot/search/worker.py` - Runs initial backfill materialization and writes completed/failed worker status.
- `src/codexbot/search/__init__.py` - Exports new backfill DTOs.
- `tests/codexbot/test_search_backfill.py` - Parser source, window enumeration, chunking, provenance, and artifact tests.
- `tests/codexbot/test_search_worker.py` - Worker materialization status test.

## Decisions Made

- Backfill treats unresolved current windows as failed items in counters, but does not abort other sessions.
- Chunking is deterministic and bounded, with overlap support for later semantic indexing.
- Active generation metadata is not written by this plan; activation is left to the next generation-activation plan.

## Deviations from Plan

None - plan executed exactly as written.

**Total deviations:** 0 auto-fixed.
**Impact on plan:** No scope changes.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Ready for `02-03`: the worker can now produce inactive parser-backed documents and a manifest, so the next plan can add safe generation activation and rebuild recovery semantics.

---
*Phase: 02-worker-skeleton-backfill-and-rebuild-path*
*Completed: 2026-05-21*
