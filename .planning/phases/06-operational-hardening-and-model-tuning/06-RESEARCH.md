# Phase 6: Operational Hardening and Model Tuning - Research

**Researched:** 2026-05-25
**Status:** Complete

## Research Question

What needs to be known to plan Phase 6 well: search worker observability,
stale/degraded status behavior, local failure isolation, Web UI status details,
and Mac-mini-appropriate embedding/index benchmarking for the existing Codi
open-session search stack.

## Source Notes

Primary local sources checked:

- `.planning/phases/06-operational-hardening-and-model-tuning/06-CONTEXT.md`
- `.planning/phases/06-operational-hardening-and-model-tuning/06-UI-SPEC.md`
- `.planning/phases/06-operational-hardening-and-model-tuning/06-AI-SPEC.md`
- `.planning/REQUIREMENTS.md`
- `.planning/phases/04-lancedb-hybrid-retrieval-and-ranking/04-RESEARCH.md`
- `.planning/phases/04-lancedb-hybrid-retrieval-and-ranking/04-VALIDATION.md`
- `.planning/phases/04-lancedb-hybrid-retrieval-and-ranking/04-*-SUMMARY.md`
- `.planning/phases/05-web-ui-search-experience-and-navigation/05-*-SUMMARY.md`
- Existing implementation and tests under `src/codexbot/search/`,
  `src/codexbot/web/api.py`, `web-ui/src/components/SessionSearch.tsx`,
  `web-ui/src/api.ts`, and search-related tests.

Relevant findings:

- Phase 4 already added a lazy local embedding provider, LanceDB index
  materialization, hybrid retrieval, lexical degraded fallback, and a
  `smoke-search-index` worker command.
- Phase 5 already added Web UI search DTOs, a compact sidebar search component,
  status chips, filters, result navigation, and static frontend contract tests.
- `pyproject.toml` already declares `lancedb>=0.21.0`,
  `sentence-transformers>=2.7.0`, and `transformers>=4.51.0`; `uv.lock`
  currently resolves LanceDB 0.30.x, Sentence Transformers 5.5.x, Transformers
  5.9.x, and Torch 2.12.x.
- Existing unit tests intentionally use fake embedders and fake LanceDB
  boundaries. Phase 6 must add an opt-in real/local benchmark path instead of
  making normal test runs load Qwen.
- Search status already exposes `SearchCounters`, `SearchQueueSnapshot`, and
  `SearchWorkerStatus`, but `SearchStatusResponse` does not yet carry enough
  operational detail for Phase 6 UI details: heartbeat freshness, queue lag
  classification, backfill progress, recent safe errors, recovery commands, or
  model/benchmark metadata.
- `search.client.get_status()` is already request-path lightweight and catches
  queue snapshot failures. This is the correct extension point for richer typed
  status.
- `search.supervisor.live_queue_loop()` already runs live draining via
  `asyncio.to_thread`, preserving backend startup responsiveness. Phase 6 should
  prove this isolation with regression tests rather than moving worker logic
  into request handlers.

## Codebase Findings

### Backend Status Surface

- `src/codexbot/search/contracts.py` defines the typed DTOs shared by backend
  and Web UI.
- `SearchWorkerStatus` currently includes `status`, `current_task`,
  `heartbeat_at`, `recent_error`, and optional counters.
- `SearchQueueSnapshot` already includes queued, leased, failed, oldest queued,
  recent error, and stale-source counts.
- `SearchStatusResponse` currently contains `state`, `available`, `scope`,
  `reason`, `counters`, `generation`, and `index`.
- `src/codexbot/search/client.py` merges worker, queue, generation, manifest,
  and index metadata without importing model or LanceDB code.
- `/api/search/status` in `src/codexbot/web/api.py` already passes current open
  session count to `search_client.get_status()`.

Phase 6 should extend typed DTOs rather than returning ad-hoc dictionaries.
Recommended additions:

- `SearchWorkerHealth` or equivalent nested DTO with state, current task,
  heartbeat time, heartbeat age, stale flag, stale threshold, and safe error.
- `SearchOperationalStatus` or fields on `SearchStatusResponse` for queue lag,
  recent sanitized errors, backfill/index progress, local recovery commands,
  model id, vector dimension, package versions where available, and latest
  benchmark summary.
- Status state derivation that marks stale heartbeat or failed queue items as
  `degraded`/`unavailable` according to context decisions without losing lexical
  availability when a completed generation exists.

### Worker and Queue Behavior

- `src/codexbot/search/worker.py` writes worker status at generation-task start,
  failure, and completion. It does not update heartbeat during the live loop or
  expose batch/drain progress.
- Live drain already uses `ready_item_count`, `lease_ready_items`,
  `upsert_generation_documents`, `upsert_index_documents`, `complete_items`,
  and `fail_items`. Failures record a queue error and keep rows retryable or
  failed/dead-lettered after bounded attempts.
- `src/codexbot/search/queue.py` sanitizes errors, tracks failed rows, exposes
  oldest queued age, and supports explicit failed-item requeue. This is enough
  for read-only recovery guidance in Phase 6.
- `src/codexbot/search/supervisor.py` starts initial backfill only when no
  active generation exists and runs live draining without blocking startup.

Phase 6 should avoid adding browser mutation controls. Local recovery commands
can be shown in the UI and documented for shell execution.

### Web UI Status Surface

- `web-ui/src/components/SessionSearch.tsx` already renders compact status,
  scope, indexed/open counts, filters, result groups, degraded/unavailable
  panels, and match labels.
- The Phase 6 UI-SPEC requires the status details to live inside the existing
  `SessionSearch` area with a `Show details` / `Hide details` button and a
  real accessible details region.
- `web-ui/src/api.ts` mirrors backend snake_case DTOs. It should be updated
  alongside backend contracts.
- `tests/codexbot/test_web_ui_search_contract.py` is the current lightweight
  frontend contract lane until there is a browser test runner.

### Benchmark and Model Validation

- Existing `smoke-search-index` validates a one-row local index path and prints
  JSON with model id, vector dimension, table, index path, and elapsed time.
- Phase 6 needs a broader opt-in benchmark path over representative sanitized
  Codi transcript fixtures. It should measure embedding throughput, memory,
  batch size, chunk size, upsert/index creation time, query latency, exact
  recall, semantic recall, and fallback behavior.
- The benchmark should not run as part of normal `pytest -q`, Ruff, Pyright, or
  frontend build.
- Good fit: add `src/codexbot/search/benchmark.py` with a CLI entrypoint or a
  `codexbot-search-worker benchmark` subcommand. Use fake provider support for
  tests and only load the real model when the benchmark is explicitly invoked.
- Use structured JSON output so Web UI status and summary docs can report the
  last measured model/default decision without scraping console text.

## Recommended Architecture

### Status Details Slice

Extend `SearchStatusResponse` with typed operational details and render those
details in the existing search sidebar:

- Worker heartbeat: state, current task, heartbeat time, age, stale flag.
- Queue lag: queued, leased, failed, stale sources, oldest queued age.
- Backfill/index progress: indexed/open sessions, indexed chunks, active
  generation id, table/model metadata.
- Recent errors: sanitized strings only.
- Recovery commands: read-only strings such as `codexbot-search-worker
  live-drain-once`, `codexbot-search-worker rebuild`, and the benchmark command.

This plan covers OPS-03 and establishes the UI anchor required by D-01 through
D-04.

### Failure Isolation and Degraded Behavior Slice

Harden status derivation and tests around stale worker/queue/index failure:

- Stale heartbeat should degrade search status, not global service status.
- Failed queue items should be visible and inspectable through status.
- Semantic/index failures should keep lexical degraded search available when
  generation documents exist.
- Startup/supervisor/live-loop exceptions must not block FastAPI startup,
  session list, WebSocket/chat delivery, Telegram delivery, terminal panels, or
  existing search routes.
- Request-path import-boundary tests must keep heavy model/index imports out of
  `web/api.py` and `search.client`.

This plan covers OPS-04 and OPS-06.

### Benchmark and Model Decision Slice

Add an opt-in benchmark path:

- Fixture loader for sanitized transcript-like JSONL/JSON cases.
- Fake-provider tests for deterministic benchmark logic.
- Optional real Qwen run that records package versions, model id, vector
  dimension, query instruction, batch size, chunk sizing, local-files flag,
  throughput, memory, index timings, query latencies, and recall scores.
- Store last benchmark/model decision as search-owned derived state and expose
  it through status details.
- Document fallback/degraded behavior and environment overrides.

This plan covers OPS-05 and closes OPS-06 from the model-readiness side.

## Plan Implications

Recommended plan split:

1. `06-01`: Operational search status contract and Web UI details.
2. `06-02`: Failure isolation, stale/degraded semantics, and read-only local
   recovery guidance.
3. `06-03`: Local benchmark, model/default validation metadata, and fallback
   documentation.

All plans can be autonomous. Wave 1 should land status DTO/UI details first so
later slices can add fields without redesigning the frontend. Wave 2 can harden
failure semantics and isolation tests. Wave 3 can add benchmark/model decision
support and update documentation.

## Validation Architecture

### Test Dimensions

1. Status contract and API detail shape
   - `/api/search/status` returns worker heartbeat detail, queue lag, progress,
     recent safe errors, recovery commands, and model/index metadata without
     raw transcript content.

2. Web UI status details
   - `SessionSearch` renders a `Show details` / `Hide details` button, uses
     `aria-expanded`, keeps details inside the search sidebar, and shows queue,
     heartbeat, backfill, recent errors, model/index, and recovery details.

3. Failure isolation
   - Failing worker startup, stale heartbeat, live-drain exceptions, queue
     failures, embedding failures, and LanceDB errors degrade search only.
   - Session list, chat delivery, terminal, Telegram, and WebSocket code paths
     stay free of search worker/model blocking.

4. Degraded/fallback behavior
   - Missing first generation shows indexing/not-ready status and no request-time
     transcript scan.
   - Completed generation without semantic index returns lexical degraded
     results.
   - Semantic failures return lexical degraded results with sanitized reasons.

5. Benchmark and model validation
   - Benchmark command runs on fixture data with fake providers in tests.
   - Optional real-model invocation records model id, vector dimension, package
     versions, batch size, chunk size, throughput, memory, and query latency.
   - Benchmark output is structured JSON and never required for normal unit
     tests.

6. Privacy and redaction
   - Recent errors/status/benchmark summaries never include raw secrets,
     full local paths, raw stack traces, or raw transcript fragments.

### Recommended Commands

- Target backend status/failure:
  `uv run pytest tests/codexbot/test_search_contracts.py tests/codexbot/test_search_worker.py tests/codexbot/test_search_live_queue.py tests/codexbot/test_web_api.py -q`
- Target retrieval/degraded:
  `uv run pytest tests/codexbot/test_search_retrieval.py tests/codexbot/test_search_index.py tests/codexbot/test_search_worker.py -q`
- Target frontend status contract:
  `uv run pytest tests/codexbot/test_web_ui_search_contract.py -q && pnpm --dir web-ui build`
- Full final lane:
  `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run pyright src/codexbot/ && uv run pytest -q && pnpm --dir web-ui build`
- Optional local benchmark:
  `uv run python -m codexbot.search.benchmark --fixtures tests/fixtures/search --provider fake`
  and, on the target host only,
  `uv run python -m codexbot.search.benchmark --fixtures tests/fixtures/search --model Qwen/Qwen3-Embedding-0.6B`

## Research Complete

Phase 6 can be planned as three vertical MVP slices that extend existing search
contracts, status APIs, Web UI details, worker failure semantics, and opt-in
benchmarking without expanding beyond open-session v1 scope.
