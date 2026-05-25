---
status: passed
phase: 06-operational-hardening-and-model-tuning
verified_at: 2026-05-25T11:50:00Z
verifier: inline-gsd-verifier
requirements:
  - OPS-03
  - OPS-04
  - OPS-05
  - OPS-06
score: 12/12
human_verification: []
---

# Phase 06 Verification: Operational Hardening And Model Tuning

## Verdict

Status: passed

Phase 6 achieved the operational hardening goal: search status now exposes worker/queue/progress/error/benchmark details, search failures degrade only search, lexical fallback remains usable, and local benchmark/model validation is opt-in and documented.

## Requirement Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| OPS-03 | passed | `SearchStatusResponse.operations` exposes `worker`, `queue`, `progress`, `recent_errors`, `recovery_commands`, and nullable `benchmark`; `SessionSearch` renders accessible `Show details` / `Hide details` rows. |
| OPS-04 | passed | Stale workers, worker launch failures, live-loop ordinary failures, dead-letter rows, and semantic exceptions are covered by regression tests without touching session/chat/terminal delivery paths. |
| OPS-05 | passed | `codexbot-search-benchmark` and `codexbot-search-worker benchmark` run fake/local provider benchmarks with metrics, thresholds, temporary LanceDB indexing, and metrics-only persisted summary state. |
| OPS-06 | passed | README documents no-generation, lexical degraded, semantic failure fallback, Qwen defaults, env overrides, and recovery commands; Web UI shows nonblocking degraded lexical copy. |

## Must-Have Verification

| Must-Have | Status | Evidence |
|-----------|--------|----------|
| Worker heartbeat and queue lag visible in existing search panel. | passed | `web-ui/src/components/SessionSearch.tsx` renders `Worker heartbeat`, `Queue lag`, `Backfill`, `Recent errors`, `Model/index`, and `Local recovery`. |
| Details are compact and hidden by default. | passed | `detailsOpen` controls a button with `aria-expanded` and details region `aria-label="Search status details"`. |
| Status refresh is modest and request-safe. | passed | `SessionSearch` polls `api.getSearchStatus()` every `10000` ms; Web API still calls only `search_client.get_status()`. |
| Recovery guidance is read-only. | passed | Recovery commands render as `<code>` text; no browser rebuild/retry mutation was added. |
| Stale heartbeat does not falsely report ready search. | passed | `test_stale_running_worker_without_generation_is_unavailable` and `test_stale_running_worker_with_generation_stays_degraded_available`. |
| Search worker/index failures do not block session list. | passed | `test_list_sessions_does_not_touch_search_runtime`; supervisor OSError/live-loop tests pass. |
| Queue failures remain inspectable and later rows continue. | passed | `test_failed_queue_rows_do_not_block_later_live_drain`. |
| Semantic failure preserves lexical degraded results. | passed | `test_semantic_exception_returns_sanitized_lexical_degraded_results`. |
| Benchmark is opt-in and fake-provider tests do not load Qwen. | passed | `tests/codexbot/test_search_benchmark.py` uses `provider_name="fake"` and validates CLI output/state. |
| Benchmark summary does not persist raw fixture text. | passed | Benchmark tests assert summary file excludes representative fixture text. |
| Qwen defaults and env overrides are documented. | passed | README contains `Qwen/Qwen3-Embedding-0.6B`, `CODEXBOT_SEARCH_MODEL_ID`, `CODEXBOT_SEARCH_VECTOR_DIM`, `CODEXBOT_SEARCH_BATCH_SIZE`, and `CODEXBOT_SEARCH_LOCAL_FILES_ONLY`. |
| Full automated validation passes. | passed | Ruff, format check, Pyright, full pytest, frontend build, and diff whitespace check passed. |

## Automated Validation

- `uv run pytest -q tests/codexbot/test_search_contracts.py tests/codexbot/test_search_worker.py tests/codexbot/test_web_api.py tests/codexbot/test_web_ui_search_contract.py` - passed: 78 tests.
- `uv run pytest -q tests/codexbot/test_search_worker.py tests/codexbot/test_search_live_queue.py tests/codexbot/test_search_retrieval.py tests/codexbot/test_web_api.py tests/codexbot/test_web_ui_search_contract.py` - passed: 90 tests.
- `uv run pytest -q tests/codexbot/test_search_benchmark.py tests/codexbot/test_search_worker.py tests/codexbot/test_search_contracts.py tests/codexbot/test_web_api.py` - passed: 84 tests, 6 LanceDB deprecation warnings.
- `uv run python -m codexbot.search.benchmark --fixtures tests/fixtures/search/benchmark_cases.json --provider fake --write-summary` - passed and wrote metrics-only summary.
- `uv run ruff check src/ tests/` - passed.
- `uv run ruff format --check src/ tests/` - passed.
- `uv run pyright src/codexbot/` - passed.
- `uv run pytest -q` - passed: 580 tests, 8 warnings.
- `pnpm --dir web-ui build` - passed, with existing Vite large chunk warning.
- `git diff --check` - passed.

## Manual Smoke

Not run. The real Qwen benchmark is target-host optional because it may require local model files or first-time download. Fake-provider benchmark, fallback behavior, API shape, and frontend build were fully validated.

## Environment Notes

The AGENTS full-suite pytest path `/tmp/codexbot-venv/bin/pytest` is absent on this host; the full test suite was run with `uv run pytest -q`.

## Gaps

None.

## Residual Risk

- Real Qwen latency and memory should be measured on the target Mac-mini-class host with `--provider local`.
- Vite still reports the existing large bundle warning.
- LanceDB emits a deprecation warning for `table_names()` from existing index helper code.

## Outcome

Phase 06 is complete and ready for any optional secure/validate/review follow-up gates.
