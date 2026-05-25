# Phase 5: Web UI Search Experience and Navigation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-05-22
**Phase:** 5-Web UI Search Experience and Navigation
**Areas discussed:** Search Surface, Result Nav, Status Filters

---

## Search Surface

### Entry Point

| Option | Description | Selected |
|--------|-------------|----------|
| Sidebar Search | Add search above the session list in `Sidebar`, keeping the active chat and draft input untouched. | yes |
| Command Overlay | Open a global modal/palette from the app shell, giving more result space but adding a new interaction pattern. | |
| Chat Header | Add a search control to the active chat toolbar, close to transcript work but less clearly global across sessions. | |

**User's choice:** Sidebar Search
**Notes:** Search starts from the existing sidebar workflow so selecting or
typing in search does not disturb the active chat.

### Results Layout

| Option | Description | Selected |
|--------|-------------|----------|
| Replace List | Use the session-list area for grouped search results while typing, which fits desktop and mobile drawer layouts cleanly. | yes |
| Inline Strip | Show a compact result strip above normal sessions, preserving the list but leaving little room for snippets. | |
| Search Tab | Add a List/Search toggle in the sidebar, making modes explicit but adding one more control. | |

**User's choice:** Replace List
**Notes:** Active query state owns the session-list area and can show grouped
sessions plus nested snippets.

### Query Trigger

| Option | Description | Selected |
|--------|-------------|----------|
| Debounced Live | Search after a short debounce once the query has meaningful text, matching `WEB-07` without extra user action. | yes |
| Enter Only | Only search when the user presses Enter, minimizing backend requests but feeling slower for session switching. | |
| Hybrid | Run live after a longer pause and immediately on Enter, balancing responsiveness with fewer requests. | |

**User's choice:** Debounced Live
**Notes:** Backend result limits and debounce behavior should keep the browser
responsive with long histories.

### Post-open State

| Option | Description | Selected |
|--------|-------------|----------|
| Keep Query | Keep results available for more hops, and close the sidebar only on mobile so the selected chat is visible. | yes |
| Clear Query | Return to the normal session list immediately after opening a result, simplest but worse for comparing hits. | |
| Stay Open | Keep the query and drawer open everywhere, good for scanning but blocks the chat on mobile. | |

**User's choice:** Keep Query
**Notes:** Preserve search context for comparing hits while making mobile
navigation show the selected chat.

---

## Result Nav

### Group Click

| Option | Description | Selected |
|--------|-------------|----------|
| Open Session | Clicking the group header switches to its `window_id`; individual hit rows handle exact scroll/highlight. | yes |
| Open First Hit | Clicking anywhere in a group jumps to the top-ranked hit, faster but easier to trigger accidentally. | |
| Expand Only | Group click only expands/collapses hits, requiring a separate action to open the session. | |

**User's choice:** Open Session
**Notes:** Session-group navigation and nested hit navigation should remain
separate affordances.

### Hit Loading

| Option | Description | Selected |
|--------|-------------|----------|
| Load Around Hit | Use `transcript_offset`/`transcript_index` to fetch a bounded message window, then scroll and highlight. | yes |
| Loaded Only | Scroll only if the hit already exists in the current `ChatView` cache, otherwise just open the session. | |
| Open Session | Always open the owning session without attempting exact hit loading in the MVP. | |

**User's choice:** Load Around Hit
**Notes:** Hit navigation should use existing transcript coordinates and avoid
full transcript loads.

### Hit Highlight

| Option | Description | Selected |
|--------|-------------|----------|
| Temporary Pulse | Scroll the target message into view and apply a short-lived message-level highlight with a search-hit label. | yes |
| Sticky Focus | Keep a persistent highlighted state until the user clears or selects another search result. | |
| Scroll Only | Just scroll to the target message, avoiding extra visual state but making the hit easier to miss. | |

**User's choice:** Temporary Pulse
**Notes:** A short-lived message-level highlight is enough for MVP transcript
focus.

### Fallback

| Option | Description | Selected |
|--------|-------------|----------|
| Session Fallback | Open the owning session by current `window_id` and show a concise toast explaining exact hit navigation was unavailable. | yes |
| Stay Results | Keep the user in search results and show an inline error, avoiding a session switch without exact positioning. | |
| Retry History | Try additional history loads before falling back, more complete but riskier for long transcripts. | |

**User's choice:** Session Fallback
**Notes:** Exact hit failure should not block useful routing to the owning open
session.

---

## Status Filters

### Status Visibility

| Option | Description | Selected |
|--------|-------------|----------|
| Compact Chip | Show a small state chip near the search box, with reason/counters available when degraded, building, or unavailable. | yes |
| Full Banner | Always show a status banner above results, clearer but more visually heavy in the sidebar. | |
| Errors Only | Hide status when ready and only show messages for building, degraded, or unavailable states. | |

**User's choice:** Compact Chip
**Notes:** Status should be visible but not consume the sidebar.

### MVP Filters

| Option | Description | Selected |
|--------|-------------|----------|
| Quick Filters | Expose runtime, role/content type, pinned, and recent activity; keep cwd/window/session advanced fields out of the main UI. | yes |
| All Filters | Expose every backend `SearchRequest` filter, powerful but dense for a sidebar workflow. | |
| Runtime Only | Start with only Codex/Claude filtering, simplest but underuses the Phase 4 contract. | |

**User's choice:** Quick Filters
**Notes:** Use practical filters in the first Web UI surface instead of
displaying the full backend contract.

### Empty States

| Option | Description | Selected |
|--------|-------------|----------|
| State Panels | Use distinct compact panels for no matches, building/partial, degraded, unavailable, and stale states. | yes |
| Generic Empty | Show one simple empty message for everything, easy but violates the no-matches distinction. | |
| Disable Search | Prevent searching until ready, clear but blocks lexical/degraded fallback results. | |

**User's choice:** State Panels
**Notes:** No matches must be visually distinct from not-ready or unavailable
search.

### Scope Cue

| Option | Description | Selected |
|--------|-------------|----------|
| Scope Chip | Always show an `Open sessions only` chip in the search header/results area, backed by status counters when available. | yes |
| Status Text | Mention scope only inside status/empty-state copy, less clutter but easier to miss. | |
| Result Metadata | Only imply scope through result session metadata and current `window_id`, minimal but not explicit. | |

**User's choice:** Scope Chip
**Notes:** The open-session v1 boundary should be persistently visible.

---

## the agent's Discretion

No user decisions were delegated to the agent during discussion. Implementation
details remain flexible where they preserve the captured context.

## Deferred Ideas

None.
