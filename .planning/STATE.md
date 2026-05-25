---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: planning
stopped_at: Phase 5 UI-SPEC approved
last_updated: "2026-05-25T08:10:33.383Z"
last_activity: 2026-05-22
progress:
  total_phases: 6
  completed_phases: 4
  total_plans: 12
  completed_plans: 12
  percent: 67
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-21)

**Core value:** Users can quickly locate active sessions by meaning and exact terms while Codi stays responsive during startup, backfill, and ongoing indexing.
**Current focus:** Phase 5 — web ui search experience and navigation

## Current Position

Phase: 5
Plan: Not started
Status: Ready to plan
Last activity: 2026-05-22

Progress: [█████████░] 92%

## Performance Metrics

**Velocity:**

- Total plans completed: 12
- Average duration: n/a
- Total execution time: 0.0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 3 | - | - |
| 02 | 3 | - | - |
| 03 | 3 | - | - |
| 04 | 3 | - | - |

**Recent Trend:**

- Last 5 plans: none
- Trend: n/a

*Updated after each plan completion*
| Phase 01 P01 | 6min | 2 tasks | 3 files |
| Phase 01 P02 | 6min | 2 tasks | 5 files |
| Phase 01 P03 | 4min | 2 tasks | 2 files |
| Phase 02 P01 | 24 min | 2 tasks | 12 files |
| Phase 02 P02 | 10 min | 2 tasks | 8 files |
| Phase 02 P03 | 7 min | 2 tasks | 8 files |
| Phase 04 P01 | 11min | 2 tasks | 9 files |
| Phase 04 P02 | 26min | 2 tasks | 8 files |
| Phase 04 P03 | 21min | 2 tasks | 11 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Milestone]: v1 scope is currently open tmux-backed Codex and Claude sessions only.
- [Milestone]: Search index is derived and rebuildable from transcript/session state.
- [Milestone]: Search worker owns embedding, indexing, LanceDB writes, backfill, search, and maintenance outside the main Codi hot path.
- [Milestone]: LanceDB hybrid retrieval and Qwen3-Embedding-0.6B are the starting choices, pending implementation validation.
- [Milestone]: Live indexing batches flush at 32 queued items or 60 seconds.
- [Phase 01]: SearchRowIdentity derives from transcript provenance and chunk index while routing/display metadata lives in SearchRoutingMetadata.
- [Phase 01]: Search contracts stay import-light and avoid worker, retrieval, index, embedding, and model dependencies on request-path modules.
- [Phase 01]: Search-owned runtime state resolves only under codexbot_dir() / 'search' and never writes monitor_state.json. — Keeps derived search metadata isolated from Codi authoritative session and monitor state.
- [Phase 01]: Missing-index status/search responses are typed normal responses with outcome not_ready and no transcript, secret, or local path leakage. — Lets Web/API callers distinguish not-ready search from transport failures or empty matching results.
- [Phase 01]: SearchResponse echoes total_results, limit, hits_per_session, and outcome for provider/API consumers. — Aligns the committed contract with the approved plan 01-02 and plan 01-03 response shape.
- [Phase 01]: Search API routes use existing Web UI auth and return typed 200 missing/not-ready responses for first-run search state. — Keeps search status as a normal authenticated API contract while indexing is absent.
- [Phase 01]: Search status derives open-session counters from current tmux windows at request time and omits counters if tmux listing fails. — Keeps routing/status tied to live tmux state without exposing local tmux errors.
- [Phase 01]: FastAPI search handlers import only lightweight search contracts/provider stubs, keeping model and index dependencies outside request handling. — Preserves OPS-02 hot-path isolation for future worker and retrieval phases.

### Pending Todos

None yet.

### Blockers/Concerns

- Phase 4 and Phase 6 need implementation validation for LanceDB APIs, Qwen3 performance, chunk sizing, vector dimensions, and degraded fallback selection.

## Deferred Items

Items acknowledged and carried forward from previous milestone close:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| v2 | Closed or resumable historical session search | Deferred | Project initialization |
| v2 | Telegram search parity | Deferred | Project initialization |
| v2 | Advanced boolean, regex, and query-qualifier syntax | Deferred | Project initialization |
| v2 | Web UI backend/model tuning controls | Deferred | Project initialization |

## Session Continuity

Last session: 2026-05-25T08:10:33.377Z
Stopped at: Phase 5 UI-SPEC approved
Resume file: .planning/phases/05-web-ui-search-experience-and-navigation/05-UI-SPEC.md
