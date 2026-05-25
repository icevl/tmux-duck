---
phase: 05-web-ui-search-experience-and-navigation
plan: "02"
subsystem: ui
tags: [react, fastapi, search, transcript-history, navigation]

requires:
  - phase: 05-web-ui-search-experience-and-navigation
    provides: "05-01 sidebar search result groups and hit target metadata"
provides:
  - "Bounded around-message history API using transcript_offset/transcript_index"
  - "Search hit routing from sidebar results into the active ChatView"
  - "Temporary visible Search hit highlight and centered scroll behavior"
affects: [web-ui, search, transcript-history]

tech-stack:
  added: []
  patterns:
    - "Search hit navigation is keyed by tmux window_id and transcript coordinates."
    - "ChatView fetches bounded around windows instead of full transcript history."

key-files:
  created:
    - .planning/phases/05-web-ui-search-experience-and-navigation/05-02-SUMMARY.md
  modified:
    - src/codexbot/web/api.py
    - tests/codexbot/test_web_api.py
    - web-ui/src/api.ts
    - web-ui/src/App.tsx
    - web-ui/src/components/ChatView.tsx
    - web-ui/src/styles.css

key-decisions:
  - "around_offset takes precedence over before/after pagination and returns only ordered transcript messages."
  - "Search hit effects wait for the owning session history load before fetching the bounded target window."

patterns-established:
  - "Use SearchHitTarget.target_id as a per-click nonce so clicking the same hit retriggers focus."
  - "Keep activeChoiceMessage bottom rendering separate from historical search highlighting."

requirements-completed: [WEB-03, WEB-04, WEB-05, WEB-06, WEB-07]

duration: 18min
completed: 2026-05-25T08:37:27Z
---

# Phase 05-02: Search Hit Navigation Summary

**Search hits now open the owning tmux session, fetch a bounded transcript window, and focus the matching message.**

## Performance

- **Duration:** 18 min
- **Started:** 2026-05-25T08:19:00Z
- **Completed:** 2026-05-25T08:37:27Z
- **Tasks:** 4
- **Files modified:** 6

## Accomplishments

- Added `around_offset` / `around_index` support to `/api/sessions/{window_id}/messages`.
- Routed nested search hit clicks through `App` into `ChatView` by current tmux `window_id`.
- Added bounded target loading, centered scroll, and temporary visible `Search hit` labeling.
- Preserved the existing active user-input prompt bottom rendering path.

## Task Commits

1. **Task 1: Bounded around-message API** - `acb6853` (feat)
2. **Tasks 2-4: Frontend hit target routing and highlight** - `0ec9c81` (feat)

## Files Created/Modified

- `src/codexbot/web/api.py` - Adds bounded around-window slicing by transcript coordinates.
- `tests/codexbot/test_web_api.py` - Covers around-window behavior and preserves after-offset behavior.
- `web-ui/src/api.ts` - Serializes `around_offset` and `around_index` for message history requests.
- `web-ui/src/App.tsx` - Stores search target state and fallback toast handling.
- `web-ui/src/components/ChatView.tsx` - Loads, merges, scrolls to, and labels exact hit messages.
- `web-ui/src/styles.css` - Styles the temporary highlighted row and visible label.

## Decisions Made

- `around_offset` ignores timestamp pagination because exact hit navigation is coordinate-based.
- `ChatView` waits until the selected session history has loaded before resolving a hit, avoiding races with session switching.
- The fallback path keeps the owning session open and uses the exact required toast copy.

## Deviations from Plan

None - plan executed as specified.

## Issues Encountered

None.

## Verification

- `uv run pytest tests/codexbot/test_web_api.py -q` - 46 passed.
- `uv run pyright src/codexbot/` - 0 errors.
- `pnpm --dir web-ui build` - passed with the existing Vite large chunk warning.
- `rg -n "around_offset" src/codexbot/web/api.py tests/codexbot/test_web_api.py web-ui/src/api.ts web-ui/src/components/ChatView.tsx` - all required surfaces present.
- `rg -n "activeChoiceMessage && \\(" web-ui/src/components/ChatView.tsx` - bottom-rendering branch present.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

05-03 can run final hardening and full validation over the completed search experience.

---
*Phase: 05-web-ui-search-experience-and-navigation*
*Completed: 2026-05-25*
