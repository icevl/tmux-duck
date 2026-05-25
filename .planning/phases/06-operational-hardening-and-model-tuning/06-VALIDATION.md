---
phase: 06
slug: operational-hardening-and-model-tuning
status: audited
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-25
updated: 2026-05-25
---

# Phase 06 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x, pytest-asyncio, Ruff, Pyright, Vite TypeScript build |
| **Config file** | `pyproject.toml`, `web-ui/tsconfig.json`, `web-ui/vite.config.ts` |
| **Quick run command** | `uv run pytest tests/codexbot/test_search_contracts.py tests/codexbot/test_search_worker.py tests/codexbot/test_web_api.py tests/codexbot/test_web_ui_search_contract.py -q && pnpm --dir web-ui build` |
| **Full suite command** | `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run pyright src/codexbot/ && uv run pytest -q && pnpm --dir web-ui build` |
| **Estimated runtime** | ~10-30 seconds targeted, ~60-240 seconds full suite; real-model benchmark is opt-in and may be slower |

---

## Sampling Rate

- **After every task commit:** Run the task's targeted `uv run pytest ... -q`
  command and `pnpm --dir web-ui build` for frontend tasks.
- **After every plan wave:** Run all Phase 6 targeted tests:
  `uv run pytest tests/codexbot/test_search_contracts.py tests/codexbot/test_search_worker.py tests/codexbot/test_search_live_queue.py tests/codexbot/test_search_retrieval.py tests/codexbot/test_search_index.py tests/codexbot/test_web_api.py tests/codexbot/test_web_ui_search_contract.py -q`
- **Before `$gsd-verify-work`:** Run the full suite command above.
- **Before claiming Qwen readiness:** Run the opt-in benchmark on the target
  host and record model id, dimensions, package versions, batch/chunk defaults,
  throughput, memory, and query latency.
- **Max feedback latency:** 240 seconds for targeted lanes excluding real-model
  first download/load.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | OPS-03, OPS-06 | T-06-01 / T-06-02 | Status DTO/API exposes heartbeat, queue lag, progress, recovery commands, and sanitized errors without importing model/index code in request handlers | unit/API | `uv run pytest tests/codexbot/test_search_contracts.py tests/codexbot/test_search_worker.py tests/codexbot/test_web_api.py -q` | yes | covered |
| 06-01-02 | 01 | 1 | OPS-03 | T-06-03 / T-06-04 | Web UI renders compact details with accessible toggle and no horizontal/mobile overflow | static-contract/build | `uv run pytest tests/codexbot/test_web_ui_search_contract.py -q && pnpm --dir web-ui build` | yes | covered |
| 06-02-01 | 02 | 2 | OPS-04, OPS-06 | T-06-05 / T-06-06 | Stale worker and failed queue items degrade search only while preserving lexical availability when a generation exists | unit/API | `uv run pytest tests/codexbot/test_search_worker.py tests/codexbot/test_search_live_queue.py tests/codexbot/test_search_retrieval.py tests/codexbot/test_web_api.py -q` | yes | covered |
| 06-02-02 | 02 | 2 | OPS-04, OPS-06 | T-06-07 / T-06-08 | Startup, live loop, API, and frontend contracts prove search failures do not block session/chat/terminal/WebSocket surfaces | unit/static-contract | `uv run pytest tests/codexbot/test_search_contracts.py tests/codexbot/test_web_api.py tests/codexbot/test_web_ui_search_contract.py -q` | yes | covered |
| 06-03-01 | 03 | 3 | OPS-05, OPS-06 | T-06-09 / T-06-10 | Benchmark command emits structured local metrics with fake-provider tests and optional real Qwen run kept out of normal checks | unit/CLI | `uv run pytest tests/codexbot/test_search_benchmark.py tests/codexbot/test_search_worker.py -q` | yes | covered |
| 06-03-02 | 03 | 3 | OPS-05, OPS-06 | T-06-11 / T-06-12 | Model/default decision and fallback docs are recorded in search-owned state/status without leaking transcripts or secrets | unit/docs | `uv run pytest tests/codexbot/test_search_contracts.py tests/codexbot/test_search_benchmark.py tests/codexbot/test_web_api.py -q` | yes | covered |

---

## Wave 0 Requirements

Existing infrastructure covers Phase 6 foundations:

- [x] `tests/codexbot/test_search_contracts.py` - search DTO and import-boundary tests.
- [x] `tests/codexbot/test_search_worker.py` - worker lifecycle, status, queue, and smoke command tests.
- [x] `tests/codexbot/test_search_live_queue.py` - live producer/queue behavior.
- [x] `tests/codexbot/test_search_retrieval.py` - degraded lexical and hybrid retrieval behavior.
- [x] `tests/codexbot/test_search_index.py` - fake embedder/index materialization.
- [x] `tests/codexbot/test_web_api.py` - authenticated search/status API behavior.
- [x] `tests/codexbot/test_web_ui_search_contract.py` - frontend static contract and mobile CSS checks.
- [x] `tests/codexbot/test_search_benchmark.py` - benchmark schema/CLI behavior, fake provider, and metrics-only summary state.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real Qwen throughput and memory on target Mac-mini-class deployment | OPS-05, OPS-06 | Unit tests use fake providers and should not download/load the model | Run `uv run python -m codexbot.search.benchmark --fixtures tests/fixtures/search/benchmark_cases.json --provider local --model Qwen/Qwen3-Embedding-0.6B` on the deployment host and record the JSON output in the summary. |
| Live Web UI details with real long-running service | OPS-03, OPS-04 | Static frontend tests cannot prove tactile status readability against a real worker/index | Open authenticated Web UI, expand search details, confirm heartbeat/queue/backfill/recovery rows wrap on desktop and mobile and search/chat remain usable during a forced worker error. |

---

## Validation Sign-Off

- [x] All tasks have automated verify commands or existing Wave 0 coverage.
- [x] Sampling continuity: no 3 consecutive tasks without automated verify.
- [x] Wave 0 covers all missing references except the new benchmark module, assigned to 06-03.
- [x] No watch-mode flags.
- [x] Feedback latency target defined.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** passed

## Validation Audit 2026-05-25

| Metric | Count |
|--------|-------|
| Gaps found | 1 |
| Resolved | 1 |
| Escalated | 0 |

Audit notes:

- Updated all six task rows from `pending`/`missing` to `covered` after execution artifacts and tests were present.
- Filled the recovery-command coverage gap by adding directly runnable `codexbot-search-worker live-drain-once`, `codexbot-search-worker rebuild`, and `python -m codexbot.search.benchmark --fixtures tests/fixtures/search/benchmark_cases.json --provider fake` status commands, then locking them in `tests/codexbot/test_web_api.py`.
- Re-ran targeted Phase 6 validation coverage: `uv run pytest tests/codexbot/test_search_contracts.py tests/codexbot/test_search_worker.py tests/codexbot/test_search_live_queue.py tests/codexbot/test_search_retrieval.py tests/codexbot/test_search_benchmark.py tests/codexbot/test_web_api.py tests/codexbot/test_web_ui_search_contract.py -q` passed with 109 tests.
