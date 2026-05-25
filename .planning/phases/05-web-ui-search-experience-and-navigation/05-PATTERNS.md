---
phase: 05
slug: web-ui-search-experience-and-navigation
status: complete
created: 2026-05-25
---

# Phase 05 - Pattern Map

## Purpose

Map the Phase 5 implementation files to existing Codi analogs so execution can extend current Web UI and request-path patterns without inventing a second navigation or search model.

## Source Artifacts

- `.planning/phases/05-web-ui-search-experience-and-navigation/05-CONTEXT.md`
- `.planning/phases/05-web-ui-search-experience-and-navigation/05-RESEARCH.md`
- `.planning/phases/05-web-ui-search-experience-and-navigation/05-UI-SPEC.md`
- `.planning/phases/05-web-ui-search-experience-and-navigation/05-VALIDATION.md`
- `AGENTS.md`

## Implementation File Map

| File | Role | Closest analogs | Concrete patterns to reuse |
| --- | --- | --- | --- |
| `web-ui/src/api.ts` | Frontend DTOs and authenticated request helpers for search/status and around-message queries | Existing `SessionSummary`, `SessionMessage`, `api.getMessages`, `api.listSessions` | Keep snake_case DTO fields matching backend JSON. Add helpers inside existing `api` object and keep `credentials: "include"` through `request<T>()`. |
| `web-ui/src/components/SessionSearch.tsx` | New sidebar-owned search UI child component | `Sidebar.tsx` session rows, menus, runtime icon, loading/empty states | Use compact rows, lucide icons, existing runtime display, no browser transcript indexing, callbacks for group and hit selection. |
| `web-ui/src/components/Sidebar.tsx` | Integration point that hosts search above the session list | Existing `sidebar-actions`, `.session-list`, `onSelect`, `onClose`, pinned/session ordering | Preserve drag/drop only when query is empty. Active query replaces session-list body with search results. |
| `web-ui/src/App.tsx` | Search result navigation coordinator | Existing `handleSelectSession`, `showToast`, `sidebarOpen`, `activeId`, `ChatView` prop wiring | Group clicks call current session selection path. Hit clicks set active session, close mobile drawer, and pass a nonce-backed target to `ChatView`. |
| `web-ui/src/components/ChatView.tsx` | Bounded history loading, scroll, and target highlight | Existing `messageTranscriptPosition`, `mergeAppendMessages`, `api.getMessages`, `pendingAnchorRef`, active choice prompt rendering | Add coordinate-based target matching. Fetch around target only when needed. Preserve active choice prompt at the bottom. |
| `web-ui/src/styles.css` | Sidebar search, result rows, status chips, hit highlight, mobile wrapping | Existing sidebar/session/message/mobile styles and CSS tokens | Use existing dark tokens, 6px control radius, compact rows, no horizontal overflow on mobile. |
| `src/codexbot/web/api.py` | Request-path message-window helper for exact hit navigation | Existing `/api/sessions/{window_id}/messages` before/after transcript filters | Add optional `around_offset` and `around_index` query params. Return a bounded slice containing the target when present. |
| `tests/codexbot/test_web_api.py` | Backend regression tests for message-window behavior | Existing `test_get_messages_filters_by_transcript_order`, search route tests | Add tests proving `around_*` includes the target, stays bounded, and preserves before/after behavior. |

## Data Flow

1. `SessionSearch` loads `api.getSearchStatus()` and debounced `api.searchSessions()`.
2. Search requests pass only bounded filters: `query`, `limit`, `hits_per_session`, `runtime`, `role`, `content_type`, `pinned`, and `recent_seconds`.
3. Group results use `SearchSessionResult.routing.window_id` to select the live session.
4. Hit results emit a `SearchHitTarget` with routing `window_id`, provenance `session_id`, `transcript_offset`, `transcript_index`, `chunk_index`, and a nonce.
5. `App.tsx` sets the active session and passes the latest target to `ChatView`.
6. `ChatView` first searches loaded messages by transcript coordinates, then calls `api.getMessages(windowId, { around_offset, around_index, limit })` if the target is missing.
7. Once the target is present, `ChatView` scrolls to the row and applies a temporary `Search hit` highlight.
8. If exact target loading fails, the owning session stays open and `showToast("Opened session. Exact hit is unavailable.", "error")` reports the fallback.

## Important Existing Constraints

- Routing is keyed by tmux `window_id`, not window names or runtime session IDs.
- The Web UI must not fetch, scan, or index full transcripts in the browser.
- Search is limited to open sessions for v1; show `Open sessions only`.
- Existing session list ordering and drag/drop must be unchanged when the query is empty.
- Active user-input choice prompts remain rendered at the bottom until answered.
- `pnpm --dir web-ui build` is the reliable frontend validation command.
- Backend verification follows `AGENTS.md`: `uv run ruff check src/ tests/`, `uv run pyright src/codexbot/`, and `/tmp/codexbot-venv/bin/pytest -q`.

## Landmines

- Do not use timestamps for exact hit navigation when transcript offsets exist; offsets/indexes are the ordering contract.
- Do not add a modal command palette or landing-page search screen.
- Do not let degraded/unavailable search render as a normal empty result set.
- Do not move active input-required prompts into historical message order.
- Do not add unbounded frontend history fetches to find a hit.
- Do not add third-party UI packages or shadcn components for this phase.
