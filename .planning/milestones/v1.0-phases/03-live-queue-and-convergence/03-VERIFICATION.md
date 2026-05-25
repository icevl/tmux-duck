---
phase: 03-live-queue-and-convergence
status: passed
verified_at: 2026-05-22
verifier: inline-gsd-verifier
requirements:
  - CORP-05
  - INDX-04
  - INDX-05
  - INDX-06
  - INDX-07
automated_checks:
  ruff: passed
  ruff_format: passed
  pyright: passed
  pytest: passed
  schema_drift: passed
human_verification: []
---

# Phase 03 Verification

## Verdict

Passed. Phase 03 delivers durable live queue capture and convergence for open-session search state while preserving existing Codi hot paths.

## Must-Have Verification

| Requirement | Verdict | Evidence |
|-------------|---------|----------|
| CORP-05 | Passed | `refresh_stale_sources()` compares generation document sources with current open tmux/session sources, stores stale markers, and `filter_stale_documents()` hides stale rows. Covered by `test_stale_source_helper_hides_closed_session_documents`. |
| INDX-04 | Passed | `LiveQueueProducer` queues useful `NewMessage` entries through `enqueue_documents()` and startup replay queues missed parsed entries from watermarks. Covered by live producer and replay tests. |
| INDX-05 | Passed | `drain_live_queue_once()` flushes immediately at 32 ready rows and flushes smaller batches after 60 seconds. Covered by worker batching tests. |
| INDX-06 | Passed | Queue ids are deterministic from `SearchRowIdentity`, and `upsert_generation_documents()` merges generation JSONL rows by the same stable identity. Covered by duplicate enqueue and generation upsert tests. |
| INDX-07 | Passed | Queue leases, attempts, failed rows, transcript watermarks, queue errors, and worker status live under `CODEXBOT_DIR/search`, outside `monitor_state.json`. Covered by queue ownership, lease/retry, status, and watermark tests. |

## Automated Checks

- `uv run ruff check src/ tests/` - passed
- `uv run ruff format --check src/ tests/` - passed
- `uv run pyright src/codexbot/` - passed
- `git diff --check` - passed
- `uv run pytest -q` - passed: 542 passed, 2 warnings
- `gsd-sdk query verify.schema-drift 03` - passed: no drift detected

The AGENTS-provided `/tmp/codexbot-venv/bin/pytest -q` path is not present in this environment, so the full suite was run with `uv run pytest -q`.

## Gaps

None.

## Residual Risk

- Retrieval is intentionally still unavailable until Phase 4, so stale filtering is verified as helper behavior rather than live search-result filtering.
- Startup replay and stale-source refresh parse open transcripts in background tasks; this keeps hot paths free but can still consume local CPU on very large open transcripts.

## Outcome

Phase 03 is ready to mark complete and hand off to Phase 4 retrieval planning/execution.
