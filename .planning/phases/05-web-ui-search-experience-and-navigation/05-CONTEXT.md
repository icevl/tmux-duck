# Phase 5: Web UI Search Experience and Navigation - Context

**Gathered:** 2026-05-22
**Status:** Ready for planning

<domain>
## Phase Boundary

This phase adds the browser-side search workflow over the already-built local
open-session search API. Users should be able to start search from the existing
Web UI session workflow, understand index readiness, inspect grouped session
results and snippets, narrow results with lightweight filters, and navigate
safely to matching currently open Codex or Claude sessions.

This phase does not expand the corpus beyond open tmux-backed sessions, add
Telegram search, add closed-session or resumable history search, add admin
rebuild/model controls, or move ranking/filtering into the browser. The browser
must consume bounded backend responses and route by current tmux `window_id`.

</domain>

<decisions>
## Implementation Decisions

### Search Surface

- **D-01:** The search entry point should live in the sidebar above the existing
  session list. Starting a search must not change the active session or clear
  draft input in the active chat composer.
- **D-02:** While a query is active, the sidebar session-list area should be
  replaced by grouped search results. This gives enough space for session groups
  and nested snippets without introducing a new global modal or tab pattern.
- **D-03:** Search requests should run as debounced live interactions once the
  query has meaningful text. The UI should keep payloads capped through the
  backend `limit` and `hits_per_session` contract, not by loading full
  transcripts locally.
- **D-04:** After the user opens a result, keep the query and results available
  so they can inspect multiple hits. On mobile, close the sidebar after opening
  a result so the selected chat is visible.

### Result Navigation

- **D-05:** Clicking a result group/header should switch to the owning session by
  current `routing.window_id`. Individual nested hit rows are responsible for
  exact message navigation.
- **D-06:** Selecting a nested hit should use `transcript_offset` and
  `transcript_index` when available to load a bounded message window around the
  target, then scroll to the matching message. It must not force the browser to
  load or index the whole transcript.
- **D-07:** The selected transcript message should receive a short-lived,
  message-level highlight with a search-hit label after navigation. Exact
  snippet highlights remain part of the result display; transcript rendering can
  start with message-level focus.
- **D-08:** If exact hit navigation cannot load the target coordinates, the UI
  should still open the owning session and show a concise toast or inline notice
  that exact hit navigation was unavailable. Search clicks must not route to
  dead sessions or mutate session state.

### Status And Filters

- **D-09:** The search surface should show index readiness as a compact status
  chip near the search input/results header. When the state is not cleanly
  ready, expose reason/counter details without dominating the sidebar.
- **D-10:** Phase 5 should expose quick filters only: runtime, role/content
  type, pinned state, and recent activity. Keep cwd/project path, window ID,
  runtime session ID, and other exact backend fields out of the main MVP UI
  unless needed later.
- **D-11:** The results area should render distinct compact panels for no
  matches, building/partial, degraded, stale, and unavailable states. Users must
  be able to distinguish an empty successful result from search that is not
  ready or unavailable.
- **D-12:** The UI should always show an explicit `Open sessions only` scope
  chip or equivalent compact cue in the search header/results area. When
  counters are available, tie this cue to open/indexed session counts.

### the agent's Discretion

No business-level decisions were delegated to the agent. Downstream agents may
choose exact component names, debounce timing, query length threshold, mobile
breakpoint handling, highlight duration, filter chip labels, and state-copy
wording where those choices preserve the decisions above and follow existing
Codi Web UI patterns.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project And Scope

- `.planning/PROJECT.md` - Project value, open-session v1 scope, local-first
  constraints, Web UI workflow expectations, and prior initialization choices.
- `.planning/REQUIREMENTS.md` - Phase 5 mapped requirements: `SRCH-01`,
  `SRCH-03`, and `WEB-01` through `WEB-07`.
- `.planning/ROADMAP.md` - Phase 5 goal, dependencies, success criteria, and
  UI hint.
- `.planning/STATE.md` - Current project position and carried decisions.

### Prior Phase Context

- `.planning/phases/01-search-contract-and-status-surface/01-CONTEXT.md` -
  Stable provenance, lifecycle status vocabulary, request-path API boundary,
  and search-owned state namespace.
- `.planning/phases/02-worker-skeleton-backfill-and-rebuild-path/02-CONTEXT.md`
  - Worker/backfill lifecycle, parser-backed open-session corpus, and visible
  readiness semantics.
- `.planning/phases/03-live-queue-and-convergence/03-CONTEXT.md` - Live queue
  lag/failure status, stale-source hiding, watermarks, idempotent upserts, and
  32/60 batching.
- `.planning/phases/04-lancedb-hybrid-retrieval-and-ranking/04-CONTEXT.md` -
  Grouped routeable results, nested snippets, highlight spans, match labels,
  full backend filter contract, degraded lexical fallback, and Phase 5
  out-of-scope boundaries.

### Codebase Maps

- `.planning/codebase/STRUCTURE.md` - Frontend/backend file ownership and where
  Web API routes, API client types, React components, and tests belong.
- `.planning/codebase/CONVENTIONS.md` - React/TypeScript style, component
  naming, strict TypeScript expectations, and frontend validation command.
- `.planning/codebase/STACK.md` - FastAPI, React/Vite, strict TS,
  `lucide-react`, and verification commands.
- `AGENTS.md` - Repository constraints: one session per tmux window, routing by
  tmux `window_id`, WebSocket event bus, multi-runtime adapters, and common
  check commands.

### Implementation Surfaces

- `src/codexbot/search/contracts.py` - Search status states, request filters,
  grouped response DTOs, routing metadata, nested hits, transcript coordinates,
  highlights, match labels, and result bounds.
- `src/codexbot/search/client.py` - Dependency-light search/status provider
  used by the request path.
- `src/codexbot/web/api.py` - Authenticated `/api/search/status` and
  `/api/search` endpoints plus existing session/message APIs.
- `web-ui/src/api.ts` - API client and TypeScript DTO surface to extend with
  search status/request/response types.
- `web-ui/src/App.tsx` - App-level active session, sidebar state, toast, and
  `ChatView` prop wiring needed for search-result navigation.
- `web-ui/src/components/Sidebar.tsx` - Existing session list, pinned ordering,
  mobile drawer, notifications, and session actions where the search surface
  should be added.
- `web-ui/src/components/ChatView.tsx` - Message cache, transcript
  offset/index pagination, scroll handling, active choice prompts, and message
  rendering target for hit focus/highlight.
- `web-ui/src/styles.css` - Existing responsive sidebar/chat styling and mobile
  overlay breakpoints.
- `tests/codexbot/test_web_api.py` and `tests/codexbot/test_search_*.py` -
  Existing backend API/search regression surface.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `/api/search/status` and `/api/search` already exist and return typed search
  status/results through lightweight request-path imports.
- `SearchRequest` already supports bounded `limit`, bounded
  `hits_per_session`, runtime, cwd, role, content type, status, window ID,
  session ID, pinned, and recent filters.
- `SearchResponse` already groups results under `SearchSessionResult`, and each
  result carries `SearchRoutingMetadata.window_id` for direct Web UI routing.
- `SearchHit` already carries snippet, score, outcomes, source order,
  timestamp, match labels, highlight spans, and transcript provenance.
- `ChatView` already uses transcript offsets/indexes for incremental history
  refreshes and has a bounded history cache. Exact hit navigation should extend
  that model instead of adding browser-side transcript indexing.
- `Sidebar` already owns session ordering, pinned state, mobile close behavior,
  and the visible session list, making it the natural surface for open-session
  search results.

### Established Patterns

- The Web UI uses React components under `web-ui/src/components`, shared API
  types in `web-ui/src/api.ts`, and CSS in `web-ui/src/styles.css`.
- Frontend actions that affect session selection should flow through `App.tsx`
  because it owns `activeId`, `sidebarOpen`, `showToast`, and `ChatView` prop
  wiring.
- Routing is keyed by current tmux `window_id`; names and runtime session IDs
  are display/provenance metadata only.
- Browser code must consume bounded backend results. It should not fetch, scan,
  or index every transcript locally to implement global search.
- Search status should be rendered as normal authenticated API state, not as a
  transport error, so missing/building/unavailable/degraded states can produce
  user-readable UI.

### Integration Points

- Add search status/request/response interfaces and API helpers to
  `web-ui/src/api.ts`.
- Add sidebar search input, debounced query state, quick filters, compact status
  chip, scope chip, state panels, grouped results, and nested hit rows in or
  below `Sidebar`.
- Lift result navigation state through `App.tsx`: group clicks set the active
  `window_id`; hit clicks pass a transcript target into `ChatView` and close the
  sidebar on mobile.
- Extend `ChatView` with a focused search target API that can load a bounded
  window around `transcript_offset`/`transcript_index`, scroll to the matching
  message, and apply a temporary message-level highlight.
- Add focused tests for search/status API type handling where needed, and use
  `pnpm --dir web-ui build` for frontend validation.

</code_context>

<specifics>
## Specific Ideas

User-selected specifics from discussion:

- Search starts in the sidebar above the session list.
- Active queries replace the normal session list with grouped results.
- Requests are debounced live searches with capped backend payloads.
- Query/results remain available after opening a result; mobile closes the
  drawer so the selected chat is visible.
- Result group/header click opens the owning session by `window_id`.
- Nested hit click loads around transcript coordinates, scrolls to the message,
  and applies a temporary message-level highlight.
- Exact hit navigation failure falls back to opening the owning session with a
  concise notice.
- Status appears as a compact chip with details for degraded/building/error
  states.
- MVP filters are runtime, role/content type, pinned, and recent activity.
- Empty/state panels must distinguish no matches from building, degraded,
  stale, and unavailable search.
- An `Open sessions only` scope cue should be persistently visible in the
  search context.

</specifics>

<deferred>
## Deferred Ideas

None - discussion stayed within Phase 5 scope.

</deferred>

---

*Phase: 5-Web UI Search Experience and Navigation*
*Context gathered: 2026-05-22*
