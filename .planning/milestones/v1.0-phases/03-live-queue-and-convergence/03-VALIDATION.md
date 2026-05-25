---
phase: 03
slug: live-queue-and-convergence
status: audited
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-22
updated: 2026-05-25
---

# Phase 03 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 with pytest-asyncio 1.3.0 |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest tests/codexbot/test_search_live_queue.py tests/codexbot/test_search_state.py tests/codexbot/test_search_worker.py -q` |
| **Full suite command** | `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run pyright src/codexbot/ && uv run pytest -q` |
| **Estimated runtime** | ~60-180 seconds for full suite |

---

## Sampling Rate

- **After every task commit:** Run the plan's targeted `uv run pytest ... -q`
  command.
- **After every plan wave:** Run all Phase 3 targeted tests:
  `uv run pytest tests/codexbot/test_search_live_queue.py tests/codexbot/test_search_state.py tests/codexbot/test_search_worker.py tests/codexbot/test_search_backfill.py tests/codexbot/test_session_monitor.py tests/codexbot/test_web_server.py tests/codexbot/test_web_api.py tests/codexbot/test_search_contracts.py -q`
- **Before `$gsd-verify-work`:** Run
  `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run pyright src/codexbot/ && uv run pytest -q`
- **Max feedback latency:** 180 seconds for targeted lanes; full suite may take
  longer on constrained local machines.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | INDX-04, INDX-06, INDX-07 | T-03-01 / T-03-02 | Queue DB stays under search state; duplicate queue ids are idempotent | unit | `uv run pytest tests/codexbot/test_search_live_queue.py tests/codexbot/test_search_state.py -q` | yes | covered |
| 03-01-02 | 01 | 1 | INDX-04, INDX-06, INDX-07 | T-03-01 / T-03-03 | Leases, retries, dead-letter state, and status counters persist safely | unit | `uv run pytest tests/codexbot/test_search_live_queue.py tests/codexbot/test_search_worker.py tests/codexbot/test_web_api.py -q` | yes | covered |
| 03-02-01 | 02 | 2 | INDX-04, INDX-06 | T-03-04 / T-03-05 | Monitor listener does not block delivery; replay catches up from search watermarks | unit/integration | `uv run pytest tests/codexbot/test_search_live_queue.py tests/codexbot/test_session_monitor.py tests/codexbot/test_web_server.py -q` | yes | covered |
| 03-02-02 | 02 | 2 | INDX-04, INDX-06, INDX-07 | T-03-02 / T-03-05 | Parsed live entries use backfill chunking and stable row identities | unit | `uv run pytest tests/codexbot/test_search_live_queue.py tests/codexbot/test_search_backfill.py -q` | yes | covered |
| 03-03-01 | 03 | 3 | CORP-05, INDX-05, INDX-06, INDX-07 | T-03-02 / T-03-06 | Live batches upsert documents idempotently and hide stale closed-session sources | unit/integration | `uv run pytest tests/codexbot/test_search_live_queue.py tests/codexbot/test_search_state.py tests/codexbot/test_web_api.py -q` | yes | covered |
| 03-03-02 | 03 | 3 | CORP-05, INDX-05, INDX-06, INDX-07 | T-03-03 / T-03-06 | Worker drain loop honors 32-item/60-second flush, bounded retries, and safe status degradation | unit/integration | `uv run pytest tests/codexbot/test_search_live_queue.py tests/codexbot/test_search_worker.py tests/codexbot/test_web_server.py -q` | yes | covered |

---

## Wave 0 Requirements

Existing infrastructure covers all Phase 3 requirements. Add
`tests/codexbot/test_search_live_queue.py` in Plan 01 as the focused queue and
live convergence test module.

---

## Manual-Only Verifications

All phase behaviors have automated verification. Manual smoke testing through
the live Web UI can be done after execution, but it is not required for plan
completion because this phase does not add Web UI search UX.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands or existing Wave 0 coverage
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency target defined
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** passed

## Validation Audit 2026-05-25

| Metric | Count |
|--------|-------|
| Gaps found | 6 |
| Resolved | 6 |
| Escalated | 0 |

Audit notes:

- Updated all six Phase 3 task rows from pending to covered after matching current automated coverage.
- Replaced the absent `/tmp/codexbot-venv/bin/pytest -q` full-suite path with the repo-supported `uv run pytest -q` lane.
- Re-ran focused Phase 3 validation coverage: `uv run pytest tests/codexbot/test_search_live_queue.py tests/codexbot/test_search_state.py tests/codexbot/test_search_worker.py tests/codexbot/test_search_backfill.py tests/codexbot/test_session_monitor.py tests/codexbot/test_web_server.py tests/codexbot/test_web_api.py tests/codexbot/test_search_contracts.py -q` passed with 130 tests.
