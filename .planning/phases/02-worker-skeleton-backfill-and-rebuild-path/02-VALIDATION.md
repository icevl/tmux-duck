---
phase: 02
slug: worker-skeleton-backfill-and-rebuild-path
status: audited
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-21
updated: 2026-05-25
---

# Phase 02 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 with pytest-asyncio 1.3.0 |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest tests/codexbot/test_search_worker.py tests/codexbot/test_search_backfill.py tests/codexbot/test_search_state.py tests/codexbot/test_web_api.py -q` |
| **Full suite command** | `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run pyright src/codexbot/ && uv run pytest -q` |
| **Estimated runtime** | ~90 seconds for targeted tests, full suite depends on local environment |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/codexbot/test_search_worker.py tests/codexbot/test_search_backfill.py tests/codexbot/test_search_state.py tests/codexbot/test_web_api.py -q`
- **After every plan wave:** Run `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run pyright src/codexbot/ && uv run pytest -q`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 90 seconds for targeted worker/backfill/status tests

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-W0-01 | 01 | 1 | INDX-02 | T-02-01 / T-02-05 | Worker startup is scheduled without blocking FastAPI/WebSocket/Telegram lifecycle and heavy imports stay out of request paths | unit + static | `uv run pytest tests/codexbot/test_search_worker.py tests/codexbot/test_web_server.py tests/codexbot/test_search_contracts.py -q` | yes | covered |
| 02-W0-02 | 01 | 1 | INDX-01 / INDX-08 | T-02-03 / T-02-04 | Worker/backfill state lives under `CODEXBOT_DIR/search` and incomplete generations are not active | unit | `uv run pytest tests/codexbot/test_search_state.py tests/codexbot/test_search_worker.py -q` | yes | covered |
| 02-W0-03 | 02 | 2 | CORP-01 / CORP-02 / INDX-03 | T-02-02 / T-02-06 | Backfill enumerates current tmux-backed sessions and parser-normalized text-bearing entries only | unit | `uv run pytest tests/codexbot/test_search_backfill.py tests/codexbot/test_transcript_parser.py -q` | yes | covered |
| 02-W0-04 | 03 | 3 | INDX-01 / INDX-08 | T-02-03 / T-02-04 | Explicit rebuild creates a fresh generation and activates it atomically only after success | unit + CLI smoke | `uv run pytest tests/codexbot/test_search_worker.py tests/codexbot/test_search_state.py -q` | yes | covered |
| 02-W0-05 | 03 | 3 | INDX-02 / INDX-08 | T-02-03 / T-02-05 | Status reports `building` during backfill and lexical degraded generation metadata after backfill succeeds before semantic retrieval exists | API | `uv run pytest tests/codexbot/test_web_api.py::test_search_status_reports_building_backfill tests/codexbot/test_web_api.py::test_search_status_after_successful_backfill_is_lexical_degraded -q` | yes | covered |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [x] `tests/codexbot/test_search_worker.py` - worker lifecycle, state placement, generation activation, rebuild, and interrupted generation assertions.
- [x] `tests/codexbot/test_search_backfill.py` - open-session transcript source, ParsedEntry-to-document conversion, chunking, Codex/Claude fixture assertions.
- [x] `tests/codexbot/test_web_api.py` additions - `building` and lexical degraded post-backfill search status behavior.
- [x] Existing `tests/codexbot/test_search_contracts.py` import-boundary test extended to keep worker/index dependencies out of `web/api.py` request paths.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live tmux-backed Codi process remains usable during initial search backfill | INDX-02 | Unit tests can prove nonblocking scheduling, but a live smoke verifies no operational regression in the local deployment | Start service, remove/rename `CODEXBOT_DIR/search`, load Web UI, send a message, confirm `/api/search/status` shows building or unavailable without blocking session list/message delivery. |

---

## Threat References

| Threat | Risk | Required Mitigation |
|--------|------|---------------------|
| T-02-01 | Worker startup blocks the main event loop | Supervisor launch/schedule returns quickly; tests prove startup does not await full backfill. |
| T-02-02 | Corpus exceeds v1 scope by scanning closed transcripts | Backfill source starts from open tmux windows and current `WindowState`, not raw historical directory scans. |
| T-02-03 | Search state tampers with authoritative monitor/session state | Worker/backfill writes only under `CODEXBOT_DIR/search`; tests prove `monitor_state.json` remains unchanged. |
| T-02-04 | Half-written generation becomes active | Rebuild writes inactive generation data and atomically activates metadata only after success. |
| T-02-05 | Heavy model/index dependencies reach request paths | Static import-boundary tests reject worker/index/model imports from `src/codexbot/web/api.py`. |
| T-02-06 | Status responses leak transcript text, local stacks, or secrets | Worker errors are summarized and sanitized before status exposure. |

## Validation Sign-Off

- [x] All tasks have automated verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all missing references
- [x] No watch-mode flags
- [x] Feedback latency target < 90s for targeted tests
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** passed

## Validation Audit 2026-05-25

| Metric | Count |
|--------|-------|
| Gaps found | 5 |
| Resolved | 5 |
| Escalated | 0 |

Audit notes:

- Updated all five Wave 0 task rows from pending to covered after matching current automated coverage.
- Replaced the stale post-backfill status selector with `test_search_status_after_successful_backfill_is_lexical_degraded`; later retrieval phases intentionally upgraded Phase 2's built-but-unqueryable state to lexical degraded availability.
- Replaced the absent `/tmp/codexbot-venv/bin/pytest -q` full-suite path with the repo-supported `uv run pytest -q`.
- Re-ran focused Phase 2 validation coverage: `uv run pytest tests/codexbot/test_search_worker.py tests/codexbot/test_web_server.py tests/codexbot/test_search_contracts.py tests/codexbot/test_search_state.py tests/codexbot/test_search_backfill.py tests/codexbot/test_transcript_parser.py tests/codexbot/test_web_api.py::test_search_status_reports_building_backfill tests/codexbot/test_web_api.py::test_search_status_after_successful_backfill_is_lexical_degraded -q` passed with 125 tests.
