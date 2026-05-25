# Phase 5: Web UI Search Experience and Navigation - Research

**Researched:** 2026-05-22
**Status:** Complete

## Research Question

What needs to be known to plan Phase 5 well: adding a browser search workflow
over the existing local search API, showing honest index status, rendering
bounded grouped results in the sidebar, routing by current tmux `window_id`,
and loading/highlighting exact transcript hits without making the browser index
full histories.

## Source Notes

Primary local sources checked:

- `.planning/phases/05-web-ui-search-experience-and-navigation/05-CONTEXT.md`
- `.planning/REQUIREMENTS.md`
- `.planning/ROADMAP.md`
- `.planning/phases/04-lancedb-hybrid-retrieval-and-ranking/04-CONTEXT.md`
- `src/codexbot/search/contracts.py`
- `src/codexbot/search/client.py`
- `src/codexbot/search/retrieval.py`
- `src/codexbot/search/ranking.py`
- `src/codexbot/web/api.py`
- `web-ui/src/api.ts`
- `web-ui/src/App.tsx`
- `web-ui/src/components/Sidebar.tsx`
- `web-ui/src/components/ChatView.tsx`
- `web-ui/src/styles.css`
- `tests/codexbot/test_web_api.py`
- `AGENTS.md`

Relevant findings:

- `/api/search/status` and `/api/search` already exist behind Web UI auth and
  route through a dependency-light backend client.
- `SearchStatusResponse` already exposes `missing`, `building`, `partial`,
  `ready`, `stale`, `degraded`, and `unavailable` states, `available`, `scope`,
  `reason`, counters, generation, and index metadata.
- `SearchRequest` already supports bounded `limit` and `hits_per_session`, plus
  runtime, cwd, role, content type, status, window ID, session ID, pinned, and
  recent filters.
- `SearchResponse` already groups results by `SearchSessionResult`, and routing
  metadata includes current `window_id`, name, cwd, runtime, session ID, pinned,
  and sort order.
- Nested `SearchHit` objects already include snippet, score, outcomes, source
  order, timestamp, highlights, match labels, and transcript provenance.
- `ChatView` already uses transcript offsets/indexes for incremental history
  pagination and cache refresh; this is the right foundation for hit-level
  navigation.
- `Sidebar` currently owns session list layout, pinned ordering, drag/drop,
  mobile drawer close behavior, and notification controls. Search belongs here
  or in a child component owned by it.

## Codebase Findings

### Existing Search API Contract

The backend has the correct API shape for Phase 5. No new search endpoint is
required for the initial UI:

- `GET /api/search/status` returns status with open-session counters when tmux
  listing succeeds.
- `POST /api/search` accepts `SearchRequest` and returns grouped
  `SearchResponse`.
- Not-ready states are normal 200 responses with `outcome="not_ready"` rather
  than transport failures.
- Ready/degraded states can still be `available=true`, so the frontend should
  not disable search solely because `state !== "ready"`.

Plan implications:

- Add TypeScript DTOs in `web-ui/src/api.ts` mirroring the Python contract.
- Add `api.getSearchStatus()` and `api.searchSessions(request)` helpers.
- Keep API request/response handling in the existing `request<T>()` wrapper so
  auth errors and JSON parsing stay consistent.
- Avoid adding backend filtering logic in the browser; only pass selected quick
  filters through the backend contract.

### Existing Sidebar Surface

`Sidebar.tsx` is currently a focused session-list component:

- Props include sessions, active ID, busy/done state, select/new/logout/close,
  rename/pin/delete/reorder, and notification toggles.
- It derives `ordered` sessions locally with pinned-first and manual ordering.
- The normal content area is `.session-list`, a flex child with vertical
  scrolling.
- On mobile, the sidebar is a fixed drawer that opens with `.sidebar-open` and
  closes through `onClose`.

Plan implications:

- Prefer a `SessionSearchPanel` or `SidebarSearch` child component to keep
  `Sidebar.tsx` from becoming too large.
- Search input and status/scope chips should sit above the scrollable result
  list, likely in the existing `.sidebar-actions` area or a new adjacent block.
- When query text is active, replace the session list body with grouped results
  instead of trying to interleave result rows with session rows.
- Preserve drag/drop session list behavior when the query is empty.
- Group click can call `onSelect(windowId)`. Hit click needs a new callback
  that carries transcript target coordinates up to `App.tsx`.

### Existing App Routing And State

`App.tsx` owns the session selection and panel lifecycle:

- `activeId` is mirrored into `/t/<window_id>` URL routing.
- `sidebarOpen` controls the mobile drawer.
- `showToast` is app-level and can be reused for hit navigation fallback.
- `ChatView` is instantiated from `activeSession` and receives action props.

Plan implications:

- Add search target state in `App.tsx`, keyed by target `window_id` and a stable
  target token.
- A group click should call the same active session setter used by the normal
  session list.
- A hit click should set active session and then pass a target object into
  `ChatView` once the session is active.
- On narrow layouts, hit/group selection should close the sidebar after setting
  active session.
- Avoid creating new URL route formats for search hits in MVP; session routing
  by `/t/<window_id>` is already the stable pattern.

### Existing ChatView History And Scroll Model

`ChatView.tsx` already has the critical mechanics:

- `api.getMessages(windowId, { before_offset, after_offset, limit })` supports
  offset/index pagination.
- `messageTranscriptPosition()` normalizes message transcript coordinates.
- `mergeAppendMessages()` and `latestTranscriptPosition()` support cache
  refresh and ordered merges.
- `scrollerRef`, `messagesListRef`, `pendingAnchorRef`, and `scheduleBottomSnap`
  already own scroll positioning.
- Each rendered message row has `data-msg-key` using an internal `_clientId`.

The missing piece is a durable way to map a search hit's provenance to a loaded
message row.

Plan implications:

- Add a search target type containing `windowId`, optional `sessionId`,
  `transcript_offset`, `transcript_index`, `chunk_index`, source order, and an
  ephemeral `targetId`/nonce.
- Add a message target key helper based on transcript coordinates, not
  `_clientId`.
- If the target message is loaded, find its row and scroll it into view.
- If not loaded, call `api.getMessages` with a bounded window around the target.
  Existing API supports `after_offset` and `before_offset`, but it does not
  currently provide a centered "around" query. The simplest MVP is two bounded
  calls: older-or-equal side through `before_offset` and newer side through
  `after_offset`, or a backend helper query if planning chooses to add one.
- Do not use timestamps for exact hit navigation when transcript offsets exist;
  offsets/indexes are already the ordering fix used by recent Web UI work.
- Add a temporary `focusedSearchTarget` or `highlightedSearchKey` state and CSS
  class on matching `messages-row` or bubble. Clear it after a short timer or on
  session switch.

### Current Message API Limitation

`GET /api/sessions/{window_id}/messages` returns the last `limit` messages after
applying before/after filters:

- `before_offset` returns messages before the cutoff, then takes the last
  `limit`, which is useful for loading earlier history.
- `after_offset` returns messages after the cutoff, then takes the last
  `limit`, which is useful for catch-up but can skip the target itself.
- There is no direct `around_offset` or inclusive lookup.

Plan implications:

- The plan should explicitly decide whether to add backend `around_offset` /
  `around_index` support or implement a frontend two-call workaround.
- A backend `around_*` query is the cleaner Phase 5 task if exact hit navigation
  is a success criterion: it can return a bounded window containing the target,
  avoid race-prone two-call merging, and keep browser behavior simple.
- If adding `around_*`, tests should verify the target coordinate appears in the
  returned payload when present and that the response remains bounded.

### Status, Scope, And Filter UX

The status contract is richer than the MVP UI should expose:

- Required visible states: missing, building, partial, ready, stale, degraded,
  unavailable.
- Distinguish successful no matches from not-ready/unavailable/degraded states.
- Persistent `Open sessions only` scope cue is required by SRCH-03.
- MVP quick filters from context: runtime, role/content type, pinned, recent
  activity.

Plan implications:

- Use compact chips and small segmented controls, not a card-heavy layout.
- Status chip should be visible near the search input/results header.
- State panels should be compact, deterministic, and keyed from
  `SearchResponse.outcome`, `status.available`, `status.state`, and
  `results.length`.
- Runtime filter values can be derived from `sessions` or fixed to
  Codex/Claude; role/content type can be a small curated set matching parser
  output used in existing transcripts.
- Recent filter should map to `recent_seconds`, for example all/recent hour/day
  options, without a date picker in MVP.

### Testing And Validation

Backend tests exist for authenticated search routes and typed payloads. There
is no dedicated frontend unit test harness in the repo; the reliable frontend
validation lane is `pnpm --dir web-ui build`.

Plan implications:

- Add backend tests for any new message API target-window behavior if the plan
  adds `around_offset`/`around_index`.
- Add TypeScript-level confidence through `pnpm --dir web-ui build`.
- Use Playwright/browser smoke where practical for the actual UX, especially
  mobile sidebar search and hit navigation, but do not make this a blocker if
  no local server is running in the plan context.
- Keep Python checks aligned with `AGENTS.md`: `uv run ruff check src/ tests/`,
  `uv run pyright src/codexbot/`, and `/tmp/codexbot-venv/bin/pytest -q`.

## Recommended Architecture

### Frontend API Types

Extend `web-ui/src/api.ts` with:

- `SearchIndexState`
- `SearchStatusResponse`
- `SearchCounters`
- `SearchRoutingMetadata`
- `SearchHighlight`
- `SearchHit`
- `SearchSessionResult`
- `SearchRequest`
- `SearchResponse`
- `api.getSearchStatus()`
- `api.searchSessions(request)`

Keep field names snake_case to match the backend JSON and avoid manual
transform layers.

### Sidebar Search Component

Add a focused child component owned by `Sidebar`, such as:

- `web-ui/src/components/SessionSearch.tsx`

Responsibilities:

- Own query text, debounce timer, status load, search request state, and quick
  filter state.
- Render search input, compact status chip, `Open sessions only` chip, quick
  filters, state-specific panels, grouped results, and nested hit buttons.
- Notify parent through callbacks:
  - `onOpenResult(windowId)`
  - `onOpenHit(target)`
- Never mutate normal session ordering or pinned state.

### Navigation Target Flow

Recommended flow:

1. `SessionSearch` emits `SearchHitTarget` with routing window ID and transcript
   coordinates.
2. `App.tsx` sets `activeId` to the target window and stores the latest target.
3. `ChatView` receives `searchTarget`.
4. `ChatView` waits until its `session.window_id` matches the target, then tries
   to find a loaded message with matching transcript coordinates.
5. If absent, `ChatView` fetches a bounded around-window from the message API.
6. Once found, `ChatView` scrolls the row into view and applies a temporary
   highlight class.
7. On failure, `ChatView` or `App.tsx` shows a toast and leaves the owning
   session open.

### Backend Message Window

Prefer adding optional `around_offset` and `around_index` query params to
`GET /api/sessions/{window_id}/messages`:

- Validate `around_offset >= 0`, `around_index >= 0`.
- Find the first message whose `(transcript_offset, transcript_index)` is
  greater than or equal to the target.
- Return a bounded slice around that index, with the target row included when
  present.
- Preserve existing before/after behavior for history prepends and catch-up.
- Keep `limit` bounded by the existing `le=2000` API guard.

This backend helper keeps Web UI hit navigation precise without adding a new
endpoint.

### Styling

Use existing restrained operational styling:

- 6-8px radius, compact chips/buttons, muted borders, and dense rows.
- Avoid full-page hero/modal patterns and decorative gradients.
- Keep sidebar search responsive within `width: min(86vw, 320px)` on mobile.
- Ensure nested snippets wrap and cannot resize fixed controls unexpectedly.
- Use `lucide-react` icons for search/filter/alert/arrow affordances where
  helpful.

## Plan Implications

Recommended plan split:

1. Frontend search contracts and sidebar search surface:
   - TypeScript DTOs/API helpers.
   - Sidebar search child component.
   - Debounced search, status/scope chips, quick filters, grouped results, and
     state panels.
   - Requirements: `SRCH-01`, `SRCH-03`, `WEB-01`, `WEB-02`, `WEB-06`,
     `WEB-07`.

2. Exact hit navigation and bounded history loading:
   - Search target flow through `App.tsx`.
   - Optional backend `around_offset`/`around_index` support.
   - `ChatView` target loading, scroll, temporary highlight, and fallback toast.
   - Requirements: `WEB-03`, `WEB-04`, `WEB-05`, `WEB-06`.

3. Responsive polish, accessibility, and verification:
   - Mobile drawer close behavior after selection.
   - Keyboard/ARIA behavior for search results and filters.
   - State-copy polish, snippet highlight rendering, empty/degraded/stale
     panels.
   - Build/tests and manual smoke guidance.
   - Requirements: all Phase 5 requirements as final cross-check.

## Validation Architecture

### Test Dimensions

1. Search API typing and request construction
   - `api.ts` exposes typed search helpers.
   - Search requests include bounded `limit` and `hits_per_session`.
   - Quick filters map to backend fields without browser-side transcript
     filtering.

2. Sidebar search behavior
   - Search starts from sidebar without changing `activeId` or `ChatView`
     draft state.
   - Active query replaces the normal session list with grouped results.
   - No-match, building, degraded, stale, and unavailable states render
     different UI states.
   - `Open sessions only` is visible in the search context.

3. Result routing
   - Group/header click opens the owning session by `routing.window_id`.
   - Hit click opens the owning session and passes transcript coordinates to
     `ChatView`.
   - Mobile drawer closes after group/hit selection.

4. Bounded hit navigation
   - Exact hit navigation loads only a bounded message window.
   - Target row scrolls into view and receives a temporary highlight.
   - Failed or missing coordinates fall back to opening the session with a
     notice.

5. Backend message window if added
   - `around_offset`/`around_index` returns a bounded payload containing the
     target when the target exists.
   - Existing before/after pagination behavior remains unchanged.

6. Regression safety
   - Existing session list ordering, pinned sessions, drag/drop, notifications,
     slash hints, skill hints, and active choice prompts continue to work.
   - `pnpm --dir web-ui build` passes.
   - Backend checks pass for any API changes.

## Risks And Mitigations

- **Risk:** `Sidebar.tsx` becomes too large.
  **Mitigation:** Put search-specific state and rendering in a child component,
  leaving `Sidebar` as the shell and session-list owner.

- **Risk:** Hit navigation misses the target because current message API only
  supports before/after windows.
  **Mitigation:** Plan a backend `around_offset`/`around_index` extension or
  explicitly test any frontend two-call approach.

- **Risk:** Search status is interpreted as transport failure.
  **Mitigation:** Treat not-ready/degraded/unavailable as normal search states
  and render state panels from the typed response.

- **Risk:** Mobile search results obscure the selected chat after opening.
  **Mitigation:** Close the sidebar drawer after selection on narrow layouts
  while preserving query state for reopening.

- **Risk:** Browser loads too much transcript text for exact hit navigation.
  **Mitigation:** Use backend-bounded message windows and existing history
  cache merge logic; do not implement browser-side global transcript scanning.

## RESEARCH COMPLETE
