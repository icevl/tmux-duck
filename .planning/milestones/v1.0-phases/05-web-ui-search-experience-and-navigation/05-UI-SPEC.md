---
phase: 05
slug: web-ui-search-experience-and-navigation
status: approved
shadcn_initialized: false
preset: none
created: 2026-05-25
---

# Phase 05 - UI Design Contract

## Summary

Phase 05 adds search to the Web UI so users can quickly find active sessions and jump to matched messages without losing the current tmux/window model. The search experience lives in the existing sidebar and keeps the chat surface focused on the selected session.

The first usable screen remains the Codi workspace. This phase must not introduce a landing page, modal-first search, browser-side indexing, or a second navigation model.

## User Outcomes

- Users can type a query in the sidebar and see grouped matches across open sessions.
- Users can open a matching session by clicking the session group row.
- Users can jump to a specific message hit by clicking the nested hit row.
- Users can see when results are complete, building, degraded, or unavailable without blocking normal work.
- Users on mobile can search, open a session, and return to chat without horizontal scrolling or extra setup.

## Existing Surface

Search is added to the current Web UI shell:

- `Sidebar` owns session discovery, pinned order, runtime badges, menus, and mobile drawer close behavior.
- `ChatView` owns history paging, message rendering, active choice prompts, slash and skill hints, and message scrolling.
- `api.ts` owns Web UI HTTP calls.
- Styling is centralized in `web-ui/src/styles.css` with dark charcoal tokens, restrained accent use, 6px control radius, and compact sidebar spacing.

## Design System

| Decision | Contract |
| --- | --- |
| UI framework | Existing custom React components and CSS modules in `web-ui/src`. |
| Component library | None. Do not add shadcn/ui for this phase. |
| Icon library | Use `lucide-react` for search, clear, filter, pin, runtime, status, and navigation controls. |
| Font | Use the existing body font stack from `styles.css`: Roboto, Segoe UI, Arial, sans-serif. |
| Mono font | Use the existing mono stack for tool names, offsets, and technical labels. |
| Shape | Reuse the existing 6px control radius. Cards are allowed only for repeated result items or state panels, not as nested page sections. |
| Density | Compact operational UI. Search must feel like a tool surface, not a marketing or editorial page. |

## Layout

### Sidebar Placement

The search entry appears in the sidebar action area below the header actions and above the session list.

Desktop:

- Keep the existing 280px sidebar width.
- Search input spans the available sidebar width.
- Filter chips wrap inside the sidebar column.
- Active query replaces the session list with the search result list.
- Empty query shows the normal ordered session list.

Mobile:

- Keep the existing drawer width rule: `min(86vw, 320px)`.
- Search input and filter chips remain inside the drawer.
- Selecting a session group or message hit closes the drawer after navigation.
- Result snippets wrap to the drawer width; no row may require horizontal scroll.

### Result List

The result list is vertically scrollable inside the existing sidebar body area. Search must not resize the chat header, message stream, composer, or terminal controls.

Result hierarchy:

1. Session group row.
2. Nested message hit rows for that session.
3. Compact state or empty panel when there are no renderable results.

Pinned sessions stay visually identifiable in search results, but search relevance controls result order while the active query is present.

## Interaction Contract

### Search Input

- Placeholder: `Search open sessions`
- Use a `Search` icon inside or immediately next to the input.
- Show an `X` icon button to clear only when the query is non-empty.
- Debounce requests so typing stays responsive.
- Submitting with Enter opens the top result if one is focused or selected.
- Escape clears the query. On mobile, Escape may also close the drawer if the query is already empty.

### Filters

Filters are compact chips or segmented controls below the search input.

Required filters:

- Runtime: `All`, `Codex`, `Claude`
- Role/type: `All`, `User`, `Agent`, `Tool`
- `Pinned`
- Recent window: `Any`, `1h`, `24h`, `7d`

Rules:

- Keep `All` selected by default.
- Show active filters with the existing accent color and strong text contrast.
- Avoid a separate advanced filter drawer in this phase.
- Filter rows may wrap, but must not push the result list below the visible mobile viewport.

### Search Status

Show a compact status chip near the search input or result header.

States:

| Backend state | Label | Visual |
| --- | --- | --- |
| Ready and complete | `Ready` | `--ok` text or subtle border. |
| Index building | `Indexing` | `--warn` text or subtle border. |
| Degraded search | `Degraded` | `--warn` text and muted helper copy. |
| Unavailable | `Unavailable` | `--danger` text and muted helper copy. |
| Searching | `Searching...` | spinner icon and muted text. |

Status copy must be concise. It should explain result completeness, not the internals of BM25, embeddings, or queues.

### Result Groups

Session group row content:

- Session title or fallback window name.
- Runtime badge: Codex or Claude.
- Pinned indicator when applicable.
- Compact metadata: current working directory basename, activity time, and hit count.

Click behavior:

- Clicking the group row opens the owning session using the current `routing.window_id`.
- The normal session list remains unchanged when the query is cleared.
- If the session cannot be opened, show a concise inline or toast error.

### Message Hits

Nested hit row content:

- Role/type label: `User`, `Agent`, `Tool`, or `System`.
- Short timestamp when available.
- Matched snippet with highlighted terms.
- Optional tool name or command label for tool output hits.

Click behavior:

- Clicking a hit opens the owning session and requests history around `transcript_offset` when available.
- If `transcript_offset` is missing, fall back to `transcript_index`.
- If neither can be resolved, open the owning session and show `Opened session. Exact hit is unavailable.`
- Highlight the target row in `ChatView` for 3 to 5 seconds with an accent-left border and subtle background.
- The highlight must not reorder messages or move active input-required prompts.

### Active User Input Prompts

If the agent is waiting for user input, that prompt remains active at the bottom of the message stream. Search navigation may scroll to a historical hit, but it must not render the prompt above older messages or deactivate existing choices.

### Loading And Empty States

No query:

- Show the normal session list.

Searching:

- Show `Searching...` in the result area with a small spinner.

No matches:

- Heading: `No matches`
- Body: `Try different terms or filters.`

Indexing:

- Label: `Indexing`
- Body: `Results may be incomplete.`

Unavailable:

- Heading: `Search unavailable`
- Body: `Keep working and try again after indexing recovers.`

Errors must not block creating sessions, switching sessions, sending chat input, terminal controls, or notifications.

## Spacing Scale

New search UI should use these values unless aligning directly with an existing local control:

| Token | px | Usage |
| --- | ---: | --- |
| `space-1` | 4 | Icon gaps, tight labels, highlight padding. |
| `space-2` | 8 | Button gaps, result row inner gaps. |
| `space-3` | 12 | Sidebar search padding, chip groups. |
| `space-4` | 16 | Section separation inside sidebar. |
| `space-6` | 24 | Empty state vertical padding. |
| `space-8` | 32 | Large empty state padding only. |

Existing 6px radii and existing 14px or 18px local paddings may be reused where the search UI touches existing sidebar or message components.

## Typography

| Role | Size | Weight | Line height | Usage |
| --- | ---: | ---: | ---: | --- |
| Body | 15px | 400 | 1.5 | Existing app body and result snippets. |
| Control | 13px | 500 | 1.3 | Chips, badges, compact buttons. |
| Label | 12px | 500 | 1.25 | Runtime, role, status, and hit metadata. |
| Heading | 15px | 600 | 1.25 | Result group title and empty state heading. |
| Mono | 12px | 400 | 1.25 | Tool names, offsets, short command labels. |

Rules:

- Do not use viewport-scaled font sizes.
- Letter spacing remains `0`.
- Long paths and command labels must wrap or ellipsize without overlapping adjacent controls.
- Keep hero-scale typography out of the sidebar.

## Color

Reuse existing tokens from `styles.css`.

| Role | Token or value | Usage |
| --- | --- | --- |
| App background | `--bg-0` `#15161a` | Main shell. |
| Sidebar surface | `--bg-1` `#1a1c20` | Sidebar base. |
| Result surface | `--bg-2` `#22242a` | Result rows and selected filter controls. |
| Raised surface | `--bg-elevated` `#1f2126` | State panels and popovers. |
| Border | `--border` / `--border-strong` | Row separators, focus rings, grouped sections. |
| Primary text | `--text-0` `#ececef` | Titles and important labels. |
| Secondary text | `--text-1` `#c4c4c9` | Snippets and metadata. |
| Muted text | `--text-2` `#8b8b93` | Empty states and helper copy. |
| Accent | `--accent` `#a78bfa` | Focus ring, active filter, matched term, transient hit highlight. |
| Success | `--ok` `#4ed4a0` | Ready status only. |
| Warning | `--warn` `#ffb454` | Indexing or degraded status. |
| Danger | `--danger` `#ff6b8a` | Unavailable or failed search. |

Accent use must be sparse. Do not turn every result row into a purple surface; reserve accent for active, selected, focused, or matched elements.

## Copywriting Contract

Required exact strings:

| Context | Copy |
| --- | --- |
| Search placeholder | `Search open sessions` |
| Default scope chip | `Open sessions only` |
| Loading label | `Searching...` |
| No matches heading | `No matches` |
| No matches body | `Try different terms or filters.` |
| Indexing label | `Indexing` |
| Indexing body | `Results may be incomplete.` |
| Degraded label | `Degraded` |
| Unavailable heading | `Search unavailable` |
| Unavailable body | `Keep working and try again after indexing recovers.` |
| Hit fallback toast | `Opened session. Exact hit is unavailable.` |
| Highlight label | `Search hit` |

Do not add explanatory in-app copy about embeddings, BM25, LanceDB, queue sizes, index tables, or backend architecture.

## Accessibility

- Search input has an accessible name of `Search open sessions`.
- Icon-only buttons have explicit `aria-label` values.
- Status chip text is readable without color.
- Result groups and hit rows are keyboard reachable.
- Focus outlines use existing border and accent tokens.
- Hit highlighting is accompanied by the visible `Search hit` label, not color alone.
- Touch targets for result rows, chips, and clear buttons are at least 38px tall where practical.

## Responsive Rules

- At widths under 760px, search remains inside the sidebar drawer.
- Chips wrap into multiple rows instead of shrinking text below readable sizes.
- The result list keeps vertical scroll; the page body must not horizontally scroll.
- Snippets clamp to 2 lines on mobile and 3 lines on desktop.
- Long session names, cwd labels, and tool names use ellipsis after available width is exhausted.
- The mobile drawer closes after successful result selection.

## Data And Navigation Contract

Frontend DTOs should mirror backend search responses without inventing browser-only source-of-truth state.

Expected backend calls:

- `GET /api/search/status`
- `POST /api/search`

Expected navigation payload:

- `session_id` or `window_id` for session selection.
- `transcript_offset` preferred for precise hit navigation.
- `transcript_index` fallback for older or partial index records.
- `message_id` or stable client key if available after history hydration.

`ChatView` may request a bounded history window around the target hit. Search navigation must preserve existing history paging and message ordering rules.

## Integration Boundaries

In scope:

- Sidebar search input, filters, status, and result list.
- API client DTOs for search status and session search.
- Session opening from group rows.
- Message-hit navigation and transient target highlighting.
- Mobile drawer behavior after selection.

Out of scope:

- Search across closed or archived sessions.
- Telegram search UI.
- Browser-side full-text or vector indexing.
- Global command palette.
- New design system or shadcn registry adoption.
- Changes to tmux routing semantics.

## Registry Safety

No external UI registry is used in this phase.

| Check | Result |
| --- | --- |
| shadcn initialized | No |
| shadcn components added | None |
| Third-party UI packages added | None |
| Icon package changes | None; reuse existing `lucide-react`. |

## Validation Checklist

| Dimension | Verdict | Notes |
| --- | --- | --- |
| Layout | PASS | Search is placed in the existing sidebar and does not compete with chat. |
| Interaction | PASS | Query, filters, grouped results, and hit navigation have concrete behaviors. |
| Mobile | PASS | Drawer width, wrapping, scroll, and selection behavior are specified. |
| Visual system | PASS | Existing dark tokens, radius, typography, and icon style are reused. |
| Copy | PASS | Required user-facing strings are short and implementation-ready. |
| Accessibility | PASS | Keyboard, labels, status text, and non-color hit indication are covered. |

## Checker Sign-Off

Approval: approved

Checked on: 2026-05-25

Findings:

- No blocking layout issues.
- No copywriting blockers.
- No registry or dependency risk.
- No color or typography mismatch with the existing Web UI.
