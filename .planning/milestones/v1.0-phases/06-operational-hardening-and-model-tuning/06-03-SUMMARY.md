---
phase: 06-operational-hardening-and-model-tuning
plan: "03"
subsystem: search-benchmark
tags: [search, benchmark, qwen, lancedb, degraded-mode]
requires:
  - phase: 06-01
    provides: Operational status contract and Web UI details
  - phase: 06-02
    provides: Search failure isolation coverage
provides:
  - Opt-in local search benchmark CLI
  - Fake-provider benchmark fixture and tests
  - Metrics-only benchmark summary state
  - Search operations documentation
affects: [search, docs, worker, web-ui]
tech-stack:
  added: []
  patterns:
    - Benchmark mode uses deterministic fake embeddings for normal tests
    - Real Qwen validation stays opt-in through provider=local
key-files:
  created:
    - src/codexbot/search/benchmark.py
    - tests/codexbot/test_search_benchmark.py
    - tests/fixtures/search/benchmark_cases.json
    - .planning/phases/06-operational-hardening-and-model-tuning/06-03-SUMMARY.md
  modified:
    - README.md
    - pyproject.toml
    - src/codexbot/search/client.py
    - src/codexbot/search/contracts.py
    - src/codexbot/search/state.py
    - src/codexbot/search/worker.py
    - web-ui/src/api.ts
    - tests/codexbot/test_search_contracts.py
    - tests/codexbot/test_web_api.py
key-decisions:
  - "Normal validation uses provider=fake so tests do not load or download Qwen weights."
  - "Benchmark indexing uses a temporary LanceDB directory; only metrics/config are persisted in benchmark_summary.json."
  - "Qwen/Qwen3-Embedding-0.6B remains the documented default pending target-host real-model benchmark."
patterns-established:
  - "Search benchmark summaries are read through SearchStatusResponse.operations.benchmark."
  - "codexbot-search-worker benchmark delegates to codexbot.search.benchmark."
requirements-completed: [OPS-05, OPS-06]
duration: 8min
completed: 2026-05-25
---

# Phase 6 Plan 03: Benchmark And Model Validation Summary

**Opt-in local search benchmark with fake-provider tests, metrics-only status persistence, and documented Qwen fallback operations.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-05-25T11:41:20Z
- **Completed:** 2026-05-25T11:49:22Z
- **Tasks:** 4
- **Files modified:** 13

## Accomplishments

- Added `codexbot.search.benchmark` with reusable `run_benchmark()` and CLI flags for fixtures, provider, model, batch size, chunking, thresholds, and summary persistence.
- Added `codexbot-search-benchmark` and `codexbot-search-worker benchmark` command paths.
- Added sanitized benchmark fixture coverage with 8 transcript-like documents and 6 exact/semantic/fallback queries.
- Added state helpers for `benchmark_summary.json` and exposed latest metrics through `SearchStatusResponse.operations.benchmark`.
- Documented model defaults, env overrides, degraded fallback modes, and local recovery/benchmark commands in README.

## Fake Benchmark Evidence

`uv run python -m codexbot.search.benchmark --fixtures tests/fixtures/search/benchmark_cases.json --provider fake --write-summary`

- `ok`: true
- `model_id`: `fake/codi-search-benchmark`
- `vector_dimension`: 16
- `document_count`: 8
- `query_count`: 6
- `embedding_docs_per_second`: 3419.32
- `index_elapsed_ms`: 6330.291
- `query_p95_ms`: 11.978
- `peak_memory_mb`: 43.009
- `exact_top3`: 1.0
- `semantic_top5`: 1.0
- `fallback_ok`: true

Real Qwen benchmark was not run in this execution because it is target-host optional and may require local model availability/download. The default remains `Qwen/Qwen3-Embedding-0.6B`; lexical degraded behavior is passing and documented if local semantic validation is unavailable.

## Task Commits

Each task was implemented as one cohesive plan commit in this inline execution path.

1. **Task 1: Benchmark schema and fixture tests** - covered by this commit.
2. **Task 2: Benchmark CLI and summary state** - covered by this commit.
3. **Task 3: Documentation** - covered by this commit.
4. **Task 4: Final validation and model status** - covered by this commit.

## Files Created/Modified

- `src/codexbot/search/benchmark.py` - Opt-in benchmark module and CLI.
- `tests/codexbot/test_search_benchmark.py` - Fake-provider schema, CLI, worker command, and no-raw-text persistence tests.
- `tests/fixtures/search/benchmark_cases.json` - Sanitized transcript-like benchmark fixture.
- `src/codexbot/search/contracts.py` - Expanded benchmark summary contract.
- `src/codexbot/search/state.py` - Added benchmark summary state helpers.
- `src/codexbot/search/client.py` - Reads latest benchmark summary into operational status.
- `src/codexbot/search/worker.py` - Added `benchmark` worker subcommand.
- `pyproject.toml` - Added `codexbot-search-benchmark` script.
- `web-ui/src/api.ts` - Mirrored benchmark DTO fields.
- `README.md` - Added search operations documentation.
- `tests/codexbot/test_search_contracts.py` - Added benchmark summary contract coverage.
- `tests/codexbot/test_web_api.py` - Added benchmark status API coverage.

## Verification

- `uv run pytest -q tests/codexbot/test_search_benchmark.py tests/codexbot/test_search_worker.py tests/codexbot/test_search_contracts.py tests/codexbot/test_web_api.py` - 84 passed, 6 warnings.
- `uv run python -m codexbot.search.benchmark --fixtures tests/fixtures/search/benchmark_cases.json --provider fake --write-summary` - exited 0 and wrote metrics summary.
- `rg -n "Search operations|Qwen/Qwen3-Embedding-0.6B|codexbot-search-benchmark|CODEXBOT_SEARCH_MODEL_ID|CODEXBOT_SEARCH_VECTOR_DIM|CODEXBOT_SEARCH_BATCH_SIZE|CODEXBOT_SEARCH_LOCAL_FILES_ONLY|lexical degraded" README.md` - all required strings present.
- `uv run ruff check src/ tests/` - passed.
- `uv run ruff format --check src/ tests/` - passed.
- `uv run pyright src/codexbot/` - 0 errors.
- `uv run pytest -q` - 580 passed, 8 warnings.
- `pnpm --dir web-ui build` - passed.
- `git diff --check` - passed.

## Decisions Made

The fake benchmark intentionally exercises embedding/index/query plumbing without Qwen so CI and normal local checks stay fast and offline.

The benchmark uses temporary LanceDB storage for indexed rows and persists only the summary metrics/config under `CODEXBOT_DIR/search/benchmark_summary.json`.

## Deviations from Plan

None.

## Issues Encountered

None. Existing warnings remain external/deprecation warnings from PTB and LanceDB `table_names()`.

## User Setup Required

Optional target-host validation:

```bash
codexbot-search-benchmark --fixtures tests/fixtures/search/benchmark_cases.json --provider local --model Qwen/Qwen3-Embedding-0.6B
```

## Next Phase Readiness

Phase 6 implementation is complete and ready for phase-level verification/closure.

## Self-Check: PASSED

---
*Phase: 06-operational-hardening-and-model-tuning*
*Completed: 2026-05-25*
