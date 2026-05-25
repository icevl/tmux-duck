# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — Session Search

**Shipped:** 2026-05-25
**Phases:** 6 | **Plans:** 18 | **Sessions:** multiple Codex/GSD sessions

### What Was Built

- Runtime-neutral search contracts with stable transcript provenance, typed
  readiness semantics, and import-light FastAPI request handlers.
- Search-owned derived state, nonblocking worker startup, parser-backed open
  session backfill, atomic generation activation, and rebuild recovery.
- Durable live transcript queue with idempotent rows, leases, retries,
  watermarks, batching, and stale-source filtering.
- Local hybrid retrieval through exact lexical search, LanceDB-backed semantic
  candidates, metadata filters, grouped session results, snippets, and degraded
  lexical-only behavior.
- Web UI search entry point, compact filters/status, grouped results, hit-level
  navigation, mobile-safe layout, and operational status details.
- Opt-in benchmark and validation path for local embedding defaults and fallback
  behavior.

### What Worked

- Keeping transcript provenance separate from current tmux routing avoided
  unstable row identity and made result navigation safer.
- Treating search as derived state kept worker failures isolated from existing
  WebSocket, Telegram, terminal, and monitor paths.
- Building the feature in vertical phases exposed readiness, backfill, live
  queue, retrieval, UI, and operations concerns before they were coupled.
- Phase validation caught missing Nyquist coverage before milestone close, which
  made the final audit mechanical instead of interpretive.

### What Was Inefficient

- The project document lagged behind implementation after early phases, so
  milestone close required a larger evolution pass.
- Some validation hardening happened after feature implementation rather than at
  the start of each phase, creating extra audit cleanup.
- Real target-host embedding benchmark data remains opt-in; the milestone ships
  the path and fallback behavior, not a captured target-host performance record.

### Patterns Established

- Search contracts live in lightweight modules that request handlers can import
  without loading embedding, LanceDB, or worker dependencies.
- Search storage resolves under `CODEXBOT_DIR/search` and remains outside
  authoritative monitor/session state.
- Worker status and queue state are durable enough to recover after process
  restart and truthful enough for the Web UI to distinguish missing, building,
  ready, degraded, stale, and unavailable states.
- Result navigation routes through mutable current `window_id` while snippets
  and hit identity come from stable transcript coordinates.

### Key Lessons

1. Preserve separate identities for transcript rows and live UI routing any time
   search results need to survive renames, cwd changes, pinning, or tmux window
   movement.
2. A local-first embedding feature needs degraded lexical behavior from the
   start; otherwise a missing model turns into a whole-product failure.
3. Archive-ready milestone docs should be updated at phase boundaries, not only
   during closeout.
4. UI search needs operational state alongside results; empty, building, stale,
   degraded, and unavailable are different user decisions.

### Cost Observations

- Model mix: mostly implementation and verification sessions; heavier planning
  was used for UI/AI contracts and milestone audit.
- Sessions: multiple GSD command sessions across six phases.
- Notable: 108 commits were created during the milestone window, with 18 plan
  summaries, 6 verification reports, and 6 validation reports archived.

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | multiple | 6 | Moved from no active-session search to archived, audited, local-first hybrid Web UI search. |

### Cumulative Quality

| Milestone | Tests | Coverage | Zero-Dep Additions |
|-----------|-------|----------|-------------------|
| v1.0 | Phase-level Ruff, Pyright, pytest, Web UI build, and focused regressions | 41/41 requirements verified | Search request contracts, queue state, retrieval fallback, UI navigation, status details |

### Top Lessons (Verified Across Milestones)

1. Keep derived local search/index state outside authoritative session and
   monitor state.
2. Make readiness and degraded states first-class UI/API concepts before adding
   expensive local model dependencies.
