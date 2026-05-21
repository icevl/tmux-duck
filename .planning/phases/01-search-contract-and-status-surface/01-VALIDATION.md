---
phase: 01
slug: search-contract-and-status-surface
status: verified
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-21
validated: 2026-05-21
---

# Phase 01 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 with pytest-asyncio 1.3.0 |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `uv run pytest tests/codexbot/test_search_contracts.py tests/codexbot/test_search_state.py tests/codexbot/test_web_api.py -q` |
| **Full suite command** | `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run pyright src/codexbot/ && uv run pytest -q` |
| **Estimated runtime** | ~90 seconds for targeted tests, full suite depends on local environment |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/codexbot/test_search_contracts.py tests/codexbot/test_search_state.py tests/codexbot/test_web_api.py -q`
- **After every plan wave:** Run `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run pyright src/codexbot/ && uv run pytest -q`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 90 seconds for targeted contract/API tests

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-W0-01 | 01 | 0 | CORP-03 | T-01-03 / T-01-04 | Provenance DTOs validate required fields without leaking runtime-specific raw records | unit | `uv run pytest tests/codexbot/test_search_contracts.py::test_provenance_contract_contains_required_fields -q` | `tests/codexbot/test_search_contracts.py` | green |
| 01-W0-02 | 01 | 0 | CORP-04 | T-01-04 | Row identity excludes mutable `window_id`, cwd, display name, pinned, and sort metadata | unit | `uv run pytest tests/codexbot/test_search_contracts.py::test_row_identity_excludes_mutable_window_metadata -q` | `tests/codexbot/test_search_contracts.py` | green |
| 01-W0-03 | 01 | 0 | CORP-06 | T-01-04 | Search state resolves under `$CODEXBOT_DIR/search/` and does not modify `monitor_state.json` | unit | `uv run pytest tests/codexbot/test_search_state.py::test_search_state_does_not_modify_monitor_state -q` | `tests/codexbot/test_search_state.py` | green |
| 01-W0-04 | 01 | 0 | OPS-02 | T-01-01 / T-01-02 / T-01-05 | Search routes require auth, return typed 200 not-ready responses, and web handlers avoid heavy model/index imports | API + static | `uv run pytest tests/codexbot/test_web_api.py::test_search_status_requires_auth tests/codexbot/test_web_api.py::test_search_stub_returns_typed_not_ready tests/codexbot/test_search_contracts.py::test_web_search_boundary_has_no_heavy_imports -q` | `tests/codexbot/test_web_api.py`, `tests/codexbot/test_search_contracts.py` | green |

*Status: pending / green / red / flaky*

---

## Wave 0 Requirements

- [x] `tests/codexbot/test_search_contracts.py` - stubs and assertions for CORP-03, CORP-04, and OPS-02 import-boundary behavior.
- [x] `tests/codexbot/test_search_state.py` - stubs and assertions for CORP-06 state namespace and monitor-state isolation.
- [x] `tests/codexbot/test_web_api.py` additions - authenticated `/api/search/status` and `/api/search` stub behavior.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| None | N/A | All Phase 1 behaviors should be automated through unit/API/static-import tests. | N/A |

---

## Threat References

| Threat | Risk | Required Mitigation |
|--------|------|---------------------|
| T-01-01 | Unauthenticated transcript/status discovery | Both search endpoints use existing Web UI auth and tests prove unauthenticated requests fail. |
| T-01-02 | Oversized search query or result limits | Pydantic request models bound query length and requested result counts. |
| T-01-03 | Status response leaks secrets or unnecessary local paths | Status DTOs expose state/reason/counters only, not environment secrets or raw transcript content. |
| T-01-04 | Search mutates authoritative session or monitor state | Search state helpers write only under `$CODEXBOT_DIR/search/`, and tests prove `monitor_state.json` remains unchanged. |
| T-01-05 | Heavy model/index imports in request handlers | Static import-boundary tests reject LanceDB, torch, transformers, sentence-transformers, and worker imports from Web API request modules. |

## Validation Audit 2026-05-21

| Metric | Count |
|--------|-------|
| Requirement rows audited | 4 |
| Covered | 4 |
| Partial | 0 |
| Missing | 0 |
| Generated test files | 0 |
| Manual-only escalations | 0 |

Audit evidence:

- `uv run pytest tests/codexbot/test_search_contracts.py::test_provenance_contract_contains_required_fields tests/codexbot/test_search_contracts.py::test_row_identity_excludes_mutable_window_metadata tests/codexbot/test_search_state.py::test_search_state_does_not_modify_monitor_state tests/codexbot/test_web_api.py::test_search_status_requires_auth tests/codexbot/test_web_api.py::test_search_stub_returns_typed_not_ready tests/codexbot/test_search_contracts.py::test_web_search_boundary_has_no_heavy_imports -q` - PASS, 6 tests.
- `uv run pytest tests/codexbot/test_search_contracts.py tests/codexbot/test_search_state.py tests/codexbot/test_web_api.py -q` - PASS, 58 tests.
- No new tests were generated because all Phase 1 requirement rows already had automated coverage in the implemented test files.

## Validation Sign-Off

- [x] All tasks have automated verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all missing references
- [x] No watch-mode flags
- [x] Feedback latency target < 90s for targeted tests
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** verified 2026-05-21
