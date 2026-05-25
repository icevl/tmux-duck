---
phase: 04-lancedb-hybrid-retrieval-and-ranking
plan: 03
subsystem: search
tags: [search, hybrid, semantic, lancedb, qwen, worker-cli]
requires:
  - phase: 04-lancedb-hybrid-retrieval-and-ranking
    provides: 04-01 lexical ranking and 04-02 local index materialization
provides:
  - Hybrid lexical plus semantic retrieval path with exact-first ranking
  - Ready/degraded search status behavior based on completed index metadata
  - Safe semantic failure fallback to lexical results
  - Local `smoke-search-index` worker command
affects: [phase-04, search-client, search-retrieval, search-worker, web-api]
tech-stack:
  added: []
  patterns:
    - Hybrid candidate merge by stable `row_id`
    - Semantic failures are downgraded to typed degraded lexical responses
key-files:
  created: []
  modified:
    - src/codexbot/search/client.py
    - src/codexbot/search/retrieval.py
    - src/codexbot/search/index.py
    - src/codexbot/search/ranking.py
    - src/codexbot/search/worker.py
    - tests/codexbot/test_search_retrieval.py
    - tests/codexbot/test_search_index.py
    - tests/codexbot/test_search_worker.py
    - tests/codexbot/test_web_api.py
key-decisions:
  - "Completed index metadata changes search status from degraded lexical to ready."
  - "Hybrid search uses local semantic scores as candidate support while exact lexical matches remain protected by app ranking."
patterns-established:
  - "Retrieval catches semantic provider failures and returns sanitized degraded lexical results."
  - "Worker smoke command reports model id, vector dimension, table, index path, and elapsed time as JSON."
requirements-completed: [SRCH-02, SRCH-04, SRCH-05, SRCH-06, RETR-01, RETR-02, RETR-03, RETR-04, RETR-05, RETR-06, RETR-07, RETR-08, OPS-01]
duration: 21min
completed: 2026-05-22
---

# Phase 04 Plan 03: Hybrid Retrieval Summary

**Hybrid session search with ready status, semantic candidate support, and lexical degraded fallback**

## Performance

- **Duration:** 21 min
- **Started:** 2026-05-22T17:37:00Z
- **Completed:** 2026-05-22T17:58:00Z
- **Tasks:** 2
- **Files modified:** 11

## Accomplishments

- Added a hybrid retrieval path that reads completed index metadata, gets semantic scores from the local LanceDB/query provider, merges by stable row identity, and reuses exact-first ranking.
- Preserved lexical degraded fallback when semantic retrieval raises, with sanitized reasons that avoid secrets and local paths.
- Added readiness behavior so completed index metadata reports `state="ready"` while missing semantic index remains degraded lexical.
- Added `codexbot-search-worker smoke-search-index` to validate local embedding/index setup and report model id, vector dimension, index path, and elapsed time.
- Added fixtures for exact technical matches, semantic paraphrases, hybrid labels, stale routing, metadata filters, degraded semantic failure, no-match ready indexes, and Web API grouped payloads.

## Task Commits

1. **Task 1 and Task 2: Hybrid retrieval and readiness behavior** - `fd799ce` (`feat(04-03)`)

**Plan metadata:** this summary commit.

## Files Created/Modified

- `src/codexbot/search/retrieval.py` - Hybrid retrieval orchestration and semantic-failure fallback.
- `src/codexbot/search/index.py` - Semantic score query helper and row rehydration support.
- `src/codexbot/search/client.py` - Ready status/search routing when completed index metadata exists.
- `src/codexbot/search/worker.py` - Local smoke command.
- `tests/codexbot/test_search_retrieval.py` - Hybrid ranking and degraded fallback fixtures.
- `tests/codexbot/test_web_api.py` - Authenticated grouped hybrid payload route fixture.

## Decisions Made

- Ready status requires a completed generation manifest plus completed local index metadata.
- Semantic retrieval errors are non-fatal once lexical generation documents exist; search remains available with `state="degraded"`.
- The smoke command is explicit and opt-in, so the normal service does not load or download the embedding model on import/startup.

## Deviations from Plan

None - plan executed exactly as written.

**Total deviations:** 0 auto-fixed.
**Impact on plan:** No scope changes.

## Issues Encountered

- Ruff formatting drift was fixed with `uv run ruff format src/ tests/`.
- Pyright required explicit ellipsis bodies for `EmbeddingProvider` protocol methods.

## User Setup Required

None - no external service configuration required.

## Verification

- `uv run pytest tests/codexbot/test_search_retrieval.py tests/codexbot/test_search_index.py tests/codexbot/test_search_worker.py tests/codexbot/test_web_api.py -q` - 72 passed.
- `uv run pytest tests/codexbot/test_search_contracts.py tests/codexbot/test_search_state.py tests/codexbot/test_search_live_queue.py tests/codexbot/test_search_backfill.py -q` - 39 passed.
- `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run pyright src/codexbot/` - passed.

## Next Phase Readiness

Phase 4 implementation is ready for full validation and phase verification. The remaining risk is live model/index smoke performance on the deployment host, because unit tests intentionally use fake embedders.

---
*Phase: 04-lancedb-hybrid-retrieval-and-ranking*
*Completed: 2026-05-22*
