# Roadmap: Codi Session Search

## Milestones

- [x] **v1.0 Session Search** — open-session hybrid search for the Web UI
  shipped 2026-05-25.

## Phases

<details>
<summary>v1.0 Session Search — shipped 2026-05-25</summary>

- [x] **Phase 1: Search Contract and Status Surface** — 3/3 plans completed
  2026-05-21.
- [x] **Phase 2: Worker Skeleton, Backfill, and Rebuild Path** — 3/3 plans
  completed 2026-05-21.
- [x] **Phase 3: Live Queue and Convergence** — 3/3 plans completed
  2026-05-22.
- [x] **Phase 4: LanceDB Hybrid Retrieval and Ranking** — 3/3 plans completed
  2026-05-22.
- [x] **Phase 5: Web UI Search Experience and Navigation** — 3/3 plans
  completed 2026-05-25.
- [x] **Phase 6: Operational Hardening and Model Tuning** — 3/3 plans
  completed 2026-05-25.

Archived details:

- `.planning/milestones/v1.0-ROADMAP.md`
- `.planning/milestones/v1.0-REQUIREMENTS.md`
- `.planning/milestones/v1.0-MILESTONE-AUDIT.md`
- `.planning/milestones/v1.0-phases/`

</details>

## Backlog

Deferred from v1.0:

- Closed or resumable historical Codex and Claude session search.
- Advanced boolean, regex, and query-qualifier syntax.
- Current-session-only transcript find mode.
- More hit expansion within grouped session results.
- Commands, skills, GSD choices, and settings as separate non-transcript result
  sections.
- Admin/status controls to rebuild, compact, diagnose, or tune search indexes.
- Telegram topic-safe search commands.
- Decision, blocker, and task extraction from search results after retrieval
  quality is proven.
- Multi-user or shared-host authorization semantics if Codi moves beyond local
  admin deployment.

## Next Milestone

Start the next milestone with `$gsd-new-milestone` so new requirements and a new
roadmap are created from the current shipped baseline.
