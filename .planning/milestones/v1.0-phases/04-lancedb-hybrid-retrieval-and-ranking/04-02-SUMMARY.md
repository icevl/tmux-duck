---
phase: 04-lancedb-hybrid-retrieval-and-ranking
plan: 02
subsystem: search
tags: [search, lancedb, embeddings, worker, queue]
requires:
  - phase: 04-lancedb-hybrid-retrieval-and-ranking
    provides: 04-01 lexical contracts and degraded retrieval boundary
provides:
  - Lazy local Qwen/SentenceTransformer embedding provider boundary
  - Generation-owned LanceDB path and index metadata helpers
  - Idempotent row conversion and merge-upsert by stable row_id
  - Worker backfill/rebuild/live hooks for index writes
affects: [phase-04, search-worker, search-index, live-queue]
tech-stack:
  added:
    - lancedb>=0.21.0
    - sentence-transformers>=2.7.0
    - transformers>=4.51.0
  patterns:
    - Heavy model/index imports occur only inside worker/provider functions
    - Unit tests use fake embedders and fake LanceDB connections
key-files:
  created:
    - src/codexbot/search/embedding.py
    - src/codexbot/search/index.py
    - tests/codexbot/test_search_index.py
  modified:
    - pyproject.toml
    - src/codexbot/search/client.py
    - src/codexbot/search/state.py
    - src/codexbot/search/worker.py
    - tests/codexbot/test_search_worker.py
key-decisions:
  - "Index metadata is generation-owned in `search/generations/<generation_id>/index.json` and excludes transcript text."
  - "Live queue rows are only marked done after both generation JSONL and index upsert succeed."
patterns-established:
  - "Search index rows flatten provenance and routing metadata while keeping `row_id` derived from immutable `SearchRowIdentity`."
  - "Embedding provider injection keeps unit tests offline and deterministic."
requirements-completed: [SRCH-02, RETR-02, RETR-04, RETR-05, OPS-01]
duration: 26min
completed: 2026-05-22
---

# Phase 04 Plan 02: Local Index Materialization Summary

**Generation-owned LanceDB index metadata and lazy local embedding worker integration**

## Performance

- **Duration:** 26 min
- **Started:** 2026-05-22T17:11:00Z
- **Completed:** 2026-05-22T17:37:00Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- Added a lazy local embedding provider defaulting to `Qwen/Qwen3-Embedding-0.6B`, with fake-provider injection for tests.
- Added LanceDB index helpers for stable `row_id`, flattened chunk rows, FTS/scalar index creation, merge-upsert, and generation-owned metadata.
- Added search state helpers for generation `lancedb/` and `index.json` paths.
- Wired worker initial backfill/rebuild and live queue drain so index writes happen before ready/completed queue status.
- Added deterministic index tests without real model downloads or hosted services.

## Task Commits

1. **Task 1 and Task 2: Local embedding and LanceDB index materialization** - `081a5ef` (`feat(04-02)`)

**Plan metadata:** this summary commit.

## Files Created/Modified

- `src/codexbot/search/embedding.py` - Lazy local SentenceTransformer provider and fake-provider test hook.
- `src/codexbot/search/index.py` - LanceDB row conversion, table upsert, indexes, and metadata writes.
- `src/codexbot/search/state.py` - Generation-owned index paths and metadata read/write helpers.
- `src/codexbot/search/worker.py` - Backfill/rebuild/live queue index write hooks.
- `tests/codexbot/test_search_index.py` - Fake embedder/table coverage for local index behavior.

## Decisions Made

- `row_id` is derived only from `SearchRowIdentity`, so mutable routing metadata updates one logical index row.
- `uv.lock` was regenerated locally for validation but remains ignored by this repository's `.gitignore`; the committed dependency contract is `pyproject.toml`.
- Worker queue completion depends on both JSONL generation upsert and LanceDB/index upsert succeeding.

## Deviations from Plan

None - plan executed exactly as written.

**Total deviations:** 0 auto-fixed.
**Impact on plan:** No scope changes.

## Issues Encountered

- Initial `uv run` after adding `sentence-transformers` downloaded large platform wheels, including Torch dependencies. Tests still use fake embedders and do not load or download Qwen.

## User Setup Required

None - no external service configuration required.

## Verification

- `uv lock` - resolved local dependency graph.
- `uv run pytest tests/codexbot/test_search_index.py tests/codexbot/test_search_worker.py tests/codexbot/test_search_live_queue.py tests/codexbot/test_search_contracts.py -q` - 39 passed.

## Next Phase Readiness

Ready for `04-03`: hybrid retrieval can read completed index metadata and add semantic/vector candidates while retaining lexical degraded fallback.

---
*Phase: 04-lancedb-hybrid-retrieval-and-ranking*
*Completed: 2026-05-22*
