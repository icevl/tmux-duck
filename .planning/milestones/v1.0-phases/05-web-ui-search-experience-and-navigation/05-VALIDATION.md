---
phase: 05
slug: web-ui-search-experience-and-navigation
status: audited
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-22
audited: 2026-05-25
---

# Phase 05 - Validation Strategy

Retroactive Nyquist audit for Phase 05 Web UI search experience and
navigation. This file records the automated coverage used to verify the phase
requirements after execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x, Ruff, Pyright, Vite TypeScript build |
| **Config file** | `pyproject.toml`, `web-ui/tsconfig.json`, `web-ui/vite.config.ts` |
| **Quick run command** | `uv run pytest tests/codexbot/test_web_api.py tests/codexbot/test_web_ui_search_contract.py -q && pnpm --dir web-ui build` |
| **Full suite command** | `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run pyright src/codexbot/ && uv run pytest -q && pnpm --dir web-ui build` |
| **Legacy unavailable command** | `/tmp/codexbot-venv/bin/pytest -q` - binary does not exist on this host |
| **Estimated runtime** | ~10 seconds for targeted pytest, ~20 seconds for full pytest, ~4 seconds for frontend build |

---

## Requirement Coverage

| Requirement | Status | Automated Evidence |
|-------------|--------|--------------------|
| SRCH-01 | COVERED | `test_app_and_chatview_search_hit_navigation_contract` proves hit navigation changes active session/search target/sidebar state only; `test_sidebar_search_keeps_session_ordering_and_pinned_list` proves the existing sidebar list remains intact. |
| SRCH-03 | COVERED | `test_session_search_uses_bounded_backend_search_only` proves `Open sessions only` scope copy and typed search status handling exist. |
| WEB-01 | COVERED | `test_session_search_uses_bounded_backend_search_only` proves status labels/states for indexing, degraded, unavailable, and related states are present. |
| WEB-02 | COVERED | `test_session_search_uses_bounded_backend_search_only` proves no-match, indexing, and unavailable copy are distinct. |
| WEB-03 | COVERED | `test_session_search_routes_by_window_id_and_preserves_local_query` proves group/hit routing uses `result.routing.window_id`. |
| WEB-04 | COVERED | `test_get_messages_filters_around_transcript_order` proves bounded backend around-window loading; `test_app_and_chatview_search_hit_navigation_contract` proves ChatView requests `around_offset`, scroll/highlight wiring, and `Search hit` label. |
| WEB-05 | COVERED | `test_app_and_chatview_search_hit_navigation_contract` proves exact fallback copy and callback wiring. |
| WEB-06 | COVERED | `test_session_search_uses_bounded_backend_search_only` proves `SessionSearch` does not call `api.getMessages`; `test_app_and_chatview_search_hit_navigation_contract` proves hit navigation loads only `limit: 120` around target coordinates. |
| WEB-07 | COVERED | `test_session_search_uses_bounded_backend_search_only` proves debounce, `limit: 10`, and `hits_per_session: 3`; `test_search_mobile_styles_and_highlight_contract` proves responsive snippet clamps. |

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | SRCH-01, SRCH-03, WEB-01, WEB-02, WEB-06, WEB-07 | T-05-01 / T-05-02 | Search UI consumes authenticated bounded backend responses and does not browser-index full transcripts | static-contract/build | `uv run pytest tests/codexbot/test_web_ui_search_contract.py -q && pnpm --dir web-ui build` | yes | COVERED |
| 05-01-02 | 01 | 1 | SRCH-03, WEB-01, WEB-02, WEB-07 | T-05-01 / T-05-03 | Status, scope, filter, and empty-state rendering distinguish not-ready/degraded/unavailable from no matches | static-contract/build | `uv run pytest tests/codexbot/test_web_ui_search_contract.py -q && pnpm --dir web-ui build` | yes | COVERED |
| 05-02-01 | 02 | 2 | WEB-03, WEB-04, WEB-05, WEB-06 | T-05-04 / T-05-05 | Result clicks route only by current tmux window ID and bounded transcript coordinates | pytest/static-contract/build | `uv run pytest tests/codexbot/test_web_api.py tests/codexbot/test_web_ui_search_contract.py -q && pnpm --dir web-ui build` | yes | COVERED |
| 05-02-02 | 02 | 2 | WEB-04, WEB-05, WEB-06 | T-05-05 / T-05-06 | Exact hit navigation loads bounded message windows, highlights a target, and falls back safely | pytest/static-contract/build | `uv run pytest tests/codexbot/test_web_api.py tests/codexbot/test_web_ui_search_contract.py -q && pnpm --dir web-ui build` | yes | COVERED |
| 05-03-01 | 03 | 3 | SRCH-01, SRCH-03, WEB-01, WEB-02, WEB-03, WEB-04, WEB-05, WEB-06, WEB-07 | T-05-01 / T-05-07 | Responsive/mobile UI preserves active chat/draft input and closes the drawer after selection | static-contract/build | `uv run pytest tests/codexbot/test_web_ui_search_contract.py -q && pnpm --dir web-ui build` | yes | COVERED |
| 05-03-02 | 03 | 3 | SRCH-01, SRCH-03, WEB-01, WEB-02, WEB-03, WEB-04, WEB-05, WEB-06, WEB-07 | T-05-08 / T-05-09 | Final regression checks preserve existing session list, chat, choices, slash/skill hints, and Web API behavior | full | `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run pyright src/codexbot/ && uv run pytest -q && pnpm --dir web-ui build` | yes | COVERED |

---

## Generated Test Coverage

| File | Purpose | Requirements |
|------|---------|--------------|
| `tests/codexbot/test_web_ui_search_contract.py` | Static pytest contract tests for frontend search API usage, sidebar integration, hit routing, active prompt preservation, and mobile CSS constraints. | SRCH-01, SRCH-03, WEB-01, WEB-02, WEB-03, WEB-04, WEB-05, WEB-06, WEB-07 |
| `tests/codexbot/test_web_api.py` | Backend route tests for authenticated search surfaces and bounded `around_offset`/`around_index` message windows. | WEB-03, WEB-04, WEB-05, WEB-06 |

---

## Wave 0 Requirements

Existing infrastructure covers Phase 5 after this audit:

- [x] `tests/codexbot/test_web_api.py` - message window behavior for `around_offset`/`around_index`.
- [x] `web-ui/src/api.ts` - TypeScript DTOs compile through `pnpm --dir web-ui build`.
- [x] `web-ui/src/components/SessionSearch.tsx` - frontend component compiles and is covered by static-contract tests.
- [x] `web-ui/src/components/ChatView.tsx` - search target loading and active-choice prompt preservation covered by static-contract tests.
- [x] `web-ui/src/styles.css` - desktop/mobile snippet clamp and highlight classes covered by static-contract tests.

---

## Manual-Only Verifications

None required for Nyquist compliance after adding `test_web_ui_search_contract.py`.

Optional live smoke remains useful after deployment:

| Behavior | Requirement | Why Optional | Test Instructions |
|----------|-------------|--------------|-------------------|
| Mobile sidebar closes after result selection while query state remains available when reopened | SRCH-01, WEB-03, WEB-07 | Requires authenticated live Web UI and real index data to inspect tactile drawer behavior | Open the deployed Web UI at mobile width, search, select a group and a hit, confirm chat becomes visible and search query remains when reopening the drawer |
| Temporary transcript highlight is visually noticeable and does not disrupt active choice prompts | WEB-04, WEB-05 | Source-level contracts are automated; visual perception is best checked live | Search for a known loaded and known older message, select each hit, confirm temporary highlight and active input-required prompt placement |

---

## Validation Audit 2026-05-25

| Metric | Count |
|--------|-------|
| Gaps found | 2 |
| Resolved | 2 |
| Escalated | 0 |

Resolved gaps:

1. Frontend search/sidebar behavior had build coverage but no automated contract tests. Added `tests/codexbot/test_web_ui_search_contract.py`.
2. Mobile snippet/highlight/active prompt preservation were manual-only. Added source-level static-contract tests and kept live smoke as optional deployment validation.

Commands run:

- `uv run pytest tests/codexbot/test_web_ui_search_contract.py -q` - 5 passed.
- `uv run pytest tests/codexbot/test_web_api.py tests/codexbot/test_web_ui_search_contract.py -q` - 51 passed.
- `pnpm --dir web-ui build` - passed with existing Vite large chunk warning.
- `uv run ruff check src/ tests/` - passed.
- `uv run ruff format --check src/ tests/` - passed after formatting `src/codexbot/web/api.py` and `tests/codexbot/test_web_ui_search_contract.py`.
- `uv run pyright src/codexbot/` - 0 errors.
- `/tmp/codexbot-venv/bin/pytest -q` - unavailable, path missing.
- `uv run pytest -q` - 566 passed, 2 warnings.

Note: One concurrent run of `uv run pytest -q` failed while `pnpm --dir web-ui build` was rewriting `web-ui/dist/assets`; rerunning after the frontend build completed passed. Do not run the full pytest suite concurrently with asset rebuilds.

---

## Validation Sign-Off

- [x] All tasks have automated verify commands or existing Wave 0 coverage.
- [x] Sampling continuity: no 3 consecutive tasks without automated verify.
- [x] Wave 0 covers all missing references.
- [x] No watch-mode flags.
- [x] Feedback latency target defined.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** audited 2026-05-25
