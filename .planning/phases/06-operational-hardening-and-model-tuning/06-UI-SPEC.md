---
phase: 6
slug: operational-hardening-and-model-tuning
status: approved
shadcn_initialized: false
preset: none
created: 2026-05-25
---

# Phase 6 - UI Design Contract

> Visual and interaction contract for the Phase 6 search operations hardening work.

---

## Design System

| Property | Value |
|----------|-------|
| Tool | none |
| Preset | not applicable |
| Component library | none |
| Icon library | lucide-react |
| Font | `Roboto` for UI text, `Roboto Mono` for terminal/code values |

This phase extends the existing Codi Web UI. Do not introduce shadcn, Radix,
Tailwind, a new design system, or a new global admin panel. Use
`web-ui/src/components/SessionSearch.tsx`, `web-ui/src/api.ts`, and
`web-ui/src/styles.css` as the design source of truth.

---

## Spacing Scale

Declared values must remain multiples of 4 where new CSS is added.

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | Icon gaps, status-value gaps, compact inline badges |
| sm | 8px | Sidebar search rows, details row gaps, state-panel internal gaps |
| md | 16px | Sidebar section rhythm, desktop expanded details spacing |
| lg | 24px | Empty-state breathing room only |
| xl | 32px | Not used in this phase |
| 2xl | 48px | Not used in this phase |
| 3xl | 64px | Not used in this phase |

Exceptions:
- Existing search input clear button remains `26px` square.
- Existing mobile search filters use `34px` minimum height.
- Existing result area height constraints remain `max-height: min(58vh, 620px)`
  on desktop and `max-height: calc(100dvh - 270px)` on mobile unless Phase 6
  status details require a smaller bounded value.

---

## Typography

| Role | Size | Weight | Line Height |
|------|------|--------|-------------|
| Body | 15px | 400 | 1.5 |
| Label | 12px | 400 or 600 for key state labels | 1.25 |
| Heading | 13px | 600 | 1.25 |
| Display | not used | not applicable | not applicable |

Typography rules:
- Keep all Phase 6 search status text compact. Do not add hero-scale or
  dashboard-scale headings inside the sidebar.
- Keep mobile search input text at `16px` to avoid browser zoom.
- Runtime/model IDs, queue counts, and commands may use the normal UI font
  unless they are command snippets, which should use `var(--font-mono)`.
- Do not use negative letter spacing or viewport-scaled font sizes.

---

## Color

| Role | Value | Usage |
|------|-------|-------|
| Dominant (60%) | `#15161a`, `#1a1c20` | Page background, sidebar base, search panel base |
| Secondary (30%) | `#22242a`, `#2a2c33`, `#1f2126` | Search controls, result groups, expanded details |
| Accent (10%) | `#a78bfa`, `#c4a8ff` | Scope chip, active filters, focus/highlight accents only |
| Destructive | `#ff6b8a` | Unavailable/error status only |
| Warning | `#ffb454` | Degraded, stale, building, lagging, or failed-queue warnings |
| Success | `#4ed4a0` | Ready/healthy status only |

Accent reserved for:
- `Open sessions only` scope chip.
- Active filter controls.
- Search-hit highlight marks.
- Link-styled local command text where it opens no destructive action.

Status colors:
- `Ready` uses success.
- `Indexing`, `Stale`, `Degraded`, queue lag, stale heartbeat, and lexical-only
  mode use warning.
- `Unavailable`, unrecoverable status read errors, and failed worker states use
  destructive.

Do not introduce a broad new color family for operations. The status surface
must remain in the existing charcoal UI with restrained state colors.

---

## Copywriting Contract

| Element | Copy |
|---------|------|
| Primary CTA | `Show details` |
| Collapse CTA | `Hide details` |
| Empty state heading | `Search status` |
| Empty state body | `Start a search to see session matches. Indexing status is shown here while Codi catches up.` |
| Building state | `Indexing` / `Results may be incomplete.` |
| Degraded state | `Degraded` / `Semantic search is not ready. Showing lexical results.` |
| Stale state | `Stale` / `Search is behind the latest session activity.` |
| Unavailable state | `Search unavailable` / `Keep working and try again after indexing recovers.` |
| Queue lag label | `Queue lag` |
| Worker heartbeat label | `Worker heartbeat` |
| Backfill progress label | `Backfill` |
| Recent errors label | `Recent errors` |
| Recovery heading | `Local recovery` |
| Recovery body | `Run the suggested command in the Codi project shell. Web UI recovery controls are intentionally read-only in this phase.` |
| Destructive confirmation | not applicable |

Copy rules:
- Use operational labels that name the problem and the local next step.
- Do not explain what search is or how Codi works inside the UI.
- Do not include long paragraphs in the sidebar. Details rows should be short,
  scannable, and clipped/wrapped without overflowing the sidebar.
- If a command is shown, it must be copyable as text and must not execute from
  the browser.

---

## Interaction Contract

### Search Status Placement

- Keep Phase 6 status inside the existing `SessionSearch` area.
- The compact row keeps the current status chip, `Open sessions only` scope
  chip, and indexed/open count.
- Add a `Show details` / `Hide details` control in the compact status/meta area.
- Expanded details appear below the compact meta row and above quick filters.
- Do not create a separate dashboard, modal, tab, or full-width page section.

### Expanded Details

The expanded details area must support these rows when data is available:

- Worker heartbeat: last heartbeat time, freshness, and worker state.
- Queue lag: queued, leased, failed/dead-letter item counts, and oldest queued
  age.
- Backfill progress: indexed/open sessions and indexed chunks. If the backend
  exposes total/backfilled counts later, render them here without changing the
  top-level search layout.
- Recent errors: sanitized error text only. Do not expose local paths, secrets,
  tracebacks, or raw model exception dumps.
- Model/index: model ID, vector dimension, and table name may be shown in a
  compact details row when available.
- Local recovery: read-only suggested commands such as
  `python -m codexbot.search.worker live-drain-once`,
  `python -m codexbot.search.worker rebuild`, or a benchmark command once
  Phase 6 defines it.

Expanded details must be bounded and scroll-safe:
- The details block may wrap text but must not force the sidebar wider.
- Long command strings use `overflow-wrap: anywhere`.
- Mobile details must remain reachable inside the existing sidebar drawer.

### Degraded Search Results

- If lexical results are shown because semantic search is unavailable, keep
  results usable and label the batch inline.
- Use copy: `Semantic search is not ready. Showing lexical results.`
- Add a compact `Lexical` or `Lexical-only` match label when the backend marks
  result outcomes accordingly.
- Do not block users with an acknowledgement gate before showing degraded
  results.

### Refresh Behavior

- Poll `/api/search/status` on a modest interval while the search panel is
  mounted or active.
- Refresh status immediately after relevant search responses and session/search
  events when existing app event wiring makes that available.
- Polling failures should update the status surface but must not clear existing
  results unless the active search response is replaced.

### Mobile Contract

- The search status details live inside the existing mobile sidebar drawer.
- Minimum tap target for `Show details`, filters, and result rows is 34px on
  mobile.
- Details rows and commands must wrap; no horizontal scrolling in the sidebar.
- Opening a result keeps the existing Phase 5 behavior: close the mobile drawer
  so the selected chat is visible.
- Expanded details must not cover the chat composer or terminal controls.

### Accessibility Contract

- Use a real `<button>` for the details toggle.
- The details region must have an accessible label, e.g. `Search status details`.
- The toggle must expose expanded/collapsed state with `aria-expanded`.
- Preserve existing `aria-live="polite"` behavior for result/status panels.
- Status color must never be the only signal; visible state text is required.

---

## Registry Safety

| Registry | Blocks Used | Safety Gate |
|----------|-------------|-------------|
| shadcn official | none | not required |
| third-party registry | none | not allowed for this phase |

---

## Checker Sign-Off

- [x] Dimension 1 Copywriting: PASS
- [x] Dimension 2 Visuals: PASS
- [x] Dimension 3 Color: PASS
- [x] Dimension 4 Typography: PASS
- [x] Dimension 5 Spacing: PASS
- [x] Dimension 6 Registry Safety: PASS

**Approval:** approved 2026-05-25

---

## Implementation References

- `.planning/phases/06-operational-hardening-and-model-tuning/06-CONTEXT.md`
- `.planning/phases/05-web-ui-search-experience-and-navigation/05-CONTEXT.md`
- `web-ui/src/components/SessionSearch.tsx`
- `web-ui/src/api.ts`
- `web-ui/src/styles.css`
- `src/codexbot/web/api.py`
- `src/codexbot/search/contracts.py`
