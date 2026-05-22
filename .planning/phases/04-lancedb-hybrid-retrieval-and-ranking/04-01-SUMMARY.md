---
phase: 04-lancedb-hybrid-retrieval-and-ranking
plan: 01
subsystem: search
tags: [search, lexical, ranking, fastapi, pydantic]
requires:
  - phase: 01-search-foundation-contracts-and-api
    provides: lightweight search DTOs and authenticated search endpoints
provides:
  - Phase 4 search request filters for window, session, pinned, and recent time
  - Highlighted grouped lexical/degraded search results over active generation documents
  - Dependency-light exact-first ranking helpers
affects: [phase-04, search-client, search-contracts, web-api]
tech-stack:
  added: []
  patterns:
    - Function-level retrieval import from search client preserves request-path import boundaries
    - Lexical degraded retrieval stays stdlib-only and uses active generation JSONL
key-files:
  created:
    - src/codexbot/search/ranking.py
    - src/codexbot/search/retrieval.py
    - tests/codexbot/test_search_retrieval.py
  modified:
    - src/codexbot/search/contracts.py
    - src/codexbot/search/client.py
    - src/codexbot/search/__init__.py
    - tests/codexbot/test_search_contracts.py
    - tests/codexbot/test_search_state.py
    - tests/codexbot/test_web_api.py
key-decisions:
  - "Active generation without semantic index now reports degraded but usable lexical search when a completed manifest exists."
  - "Metadata-only query matches do not create results without transcript evidence."
patterns-established:
  - "Search ranking returns normalized scores, match labels, source order, timestamps, and snippet-local highlight spans."
  - "Search client lazily imports retrieval implementation only after lightweight status confirms a usable generation."
requirements-completed: [SRCH-04, SRCH-05, SRCH-06, RETR-01, RETR-06, RETR-07, OPS-01]
duration: 11min
completed: 2026-05-22
---

# Phase 04 Plan 01: Lexical Retrieval Contract Summary

**Exact-first lexical session retrieval with Phase 4 filters, snippets, labels, and safe degraded status**

## Performance

- **Duration:** 11 min
- **Started:** 2026-05-22T17:00:32Z
- **Completed:** 2026-05-22T17:11:00Z
- **Tasks:** 2
- **Files modified:** 9

## Accomplishments

- Extended `SearchRequest`, `SearchHit`, and `SearchStatusResponse` for Phase 4 filters, source positions, timestamps, highlights, labels, and index metadata.
- Added stdlib-only ranking and lexical retrieval over active generation JSONL with stale-source filtering.
- Updated `/api/search` behavior so completed generations can return typed degraded lexical results before semantic indexing is available.
- Added contract, API, import-boundary, and retrieval fixtures covering exact technical matches, filters, metadata-only suppression, stale sources, and no-match behavior.

## Task Commits

1. **Task 1 and Task 2: Phase 4 contract plus lexical/degraded retrieval** - `5c6fefe` (`feat(04-01)`)

**Plan metadata:** this summary commit.

## Files Created/Modified

- `src/codexbot/search/ranking.py` - Exact-first lexical scoring, filtering, highlight construction, and grouped session aggregation.
- `src/codexbot/search/retrieval.py` - Degraded lexical provider over active generation documents.
- `src/codexbot/search/contracts.py` - Phase 4 filters, highlight DTO, index metadata DTO, and richer hit fields.
- `src/codexbot/search/client.py` - Lazy retrieval call and degraded lexical status for completed generations without semantic index.
- `tests/codexbot/test_search_retrieval.py` - Deterministic lexical retrieval fixtures.

## Decisions Made

- Completed generation manifests now expose lexical search as `state="degraded"` and `available=true` until the semantic index is ready.
- Metadata query matches are capped and cannot produce a result without transcript text evidence.
- Retrieval remains hidden behind `codexbot.search.client` function-level imports to preserve FastAPI import boundaries.

## Deviations from Plan

None - plan executed exactly as written.

**Total deviations:** 0 auto-fixed.
**Impact on plan:** No scope changes.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Verification

- `uv run pytest tests/codexbot/test_search_contracts.py tests/codexbot/test_web_api.py tests/codexbot/test_search_retrieval.py -q` - 61 passed.

## Next Phase Readiness

Ready for `04-02`: local embedding provider, generation-owned LanceDB metadata, index materialization, and worker/live queue integration can build on the locked lexical contract.

---
*Phase: 04-lancedb-hybrid-retrieval-and-ranking*
*Completed: 2026-05-22*
