---
phase: 05
slug: web-ui-search-experience-and-navigation
status: draft
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-22
---

# Phase 05 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x with pytest-asyncio; Vite TypeScript build |
| **Config file** | `pyproject.toml`, `web-ui/tsconfig.json`, `web-ui/vite.config.ts` |
| **Quick run command** | `pnpm --dir web-ui build` |
| **Full suite command** | `uv run ruff check src/ tests/ && uv run pyright src/codexbot/ && /tmp/codexbot-venv/bin/pytest -q && pnpm --dir web-ui build` |
| **Estimated runtime** | ~30-180 seconds for targeted lanes; full suite may take several minutes |

---

## Sampling Rate

- **After every frontend task commit:** Run `pnpm --dir web-ui build`.
- **After every backend API task commit:** Run the targeted pytest command named
  in the plan plus `uv run pyright src/codexbot/`.
- **After every plan wave:** Run all Phase 5 targeted checks:
  `uv run pytest tests/codexbot/test_web_api.py -q && pnpm --dir web-ui build`.
- **Before `$gsd-verify-work`:** Run
  `uv run ruff check src/ tests/ && uv run pyright src/codexbot/ && /tmp/codexbot-venv/bin/pytest -q && pnpm --dir web-ui build`.
- **Max feedback latency:** 180 seconds for targeted lanes; full suite may take
  longer on constrained local machines.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | SRCH-01, SRCH-03, WEB-01, WEB-02, WEB-06, WEB-07 | T-05-01 / T-05-02 | Search UI consumes authenticated bounded backend responses and does not browser-index full transcripts | type/build | `pnpm --dir web-ui build` | yes | pending |
| 05-01-02 | 01 | 1 | SRCH-03, WEB-01, WEB-02, WEB-07 | T-05-01 / T-05-03 | Status, scope, filter, and empty-state rendering distinguish not-ready/degraded/unavailable from no matches | type/build | `pnpm --dir web-ui build` | yes | pending |
| 05-02-01 | 02 | 2 | WEB-03, WEB-04, WEB-05, WEB-06 | T-05-04 / T-05-05 | Result clicks route only by current tmux window ID and bounded transcript coordinates | unit/build | `uv run pytest tests/codexbot/test_web_api.py -q && pnpm --dir web-ui build` | yes | pending |
| 05-02-02 | 02 | 2 | WEB-04, WEB-05, WEB-06 | T-05-05 / T-05-06 | Exact hit navigation loads bounded message windows, highlights a target, and falls back safely | unit/build | `uv run pytest tests/codexbot/test_web_api.py -q && pnpm --dir web-ui build` | yes | pending |
| 05-03-01 | 03 | 3 | SRCH-01, SRCH-03, WEB-01, WEB-02, WEB-03, WEB-04, WEB-05, WEB-06, WEB-07 | T-05-01 / T-05-07 | Responsive/mobile UI preserves active chat/draft input and closes the drawer after selection | build/manual smoke | `pnpm --dir web-ui build` | yes | pending |
| 05-03-02 | 03 | 3 | SRCH-01, SRCH-03, WEB-01, WEB-02, WEB-03, WEB-04, WEB-05, WEB-06, WEB-07 | T-05-08 / T-05-09 | Final regression checks preserve existing session list, chat, choices, slash/skill hints, and Web API behavior | full | `uv run ruff check src/ tests/ && uv run pyright src/codexbot/ && /tmp/codexbot-venv/bin/pytest -q && pnpm --dir web-ui build` | yes | pending |

---

## Wave 0 Requirements

Existing infrastructure covers Phase 5. Add or extend focused tests during
execution:

- [ ] `tests/codexbot/test_web_api.py` - message window behavior if
  `around_offset`/`around_index` is added.
- [ ] `web-ui/src/api.ts` - TypeScript DTOs compile through
  `pnpm --dir web-ui build`.
- [ ] `web-ui/src/components/SessionSearch.tsx` or equivalent - frontend
  component compiles and remains bounded to backend search responses.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Mobile sidebar closes after result selection while query state remains available when reopened | SRCH-01, WEB-03, WEB-07 | No frontend e2e test harness is established in this repo | Start the dev server, open the Web UI at mobile width, search, select a group and a hit, confirm chat becomes visible and search query is preserved when reopening the drawer |
| Temporary transcript highlight is visible and does not disrupt active choice prompts | WEB-04, WEB-05 | Requires visual confirmation of scroll/focus behavior | Search for a known loaded and known older message, select each hit, confirm a temporary message highlight and active input-required prompt placement still behave correctly |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify commands or existing Wave 0 coverage
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency target defined
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
