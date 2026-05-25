# Milestones

## v1.0 Session Search (Shipped: 2026-05-25)

**Phases completed:** 6 phases, 18 plans, 47 tasks

**Audit:** passed — 41/41 requirements, 6/6 phases, 6/6 integration flows, 6/6
E2E flows, Nyquist compliant.

**Archived artifacts:**

- `.planning/milestones/v1.0-ROADMAP.md`
- `.planning/milestones/v1.0-REQUIREMENTS.md`
- `.planning/milestones/v1.0-MILESTONE-AUDIT.md`
- `.planning/milestones/v1.0-phases/`

**Known deferred items:** closed/resumable session search, Telegram search,
advanced query syntax, current-session find, expanded hits, admin search
maintenance controls, and extracted decision/blocker/task summaries.

**Key accomplishments:**

- Runtime-neutral search contracts with stable transcript provenance, chunk-row identity, bounded request inputs, status lifecycle semantics, and import-boundary tests
- Search-owned derived state under CODEXBOT_DIR/search with safe typed missing-index status and not-ready search responses
- Authenticated FastAPI search/status surfaces with typed missing-index semantics and request-path import-boundary coverage
- Local search worker CLI boundary with search-owned worker status and nonblocking backend startup scheduling
- Parser-backed open-session search backfill with inactive generation artifacts
- Atomic search generation activation with local rebuild and built-but-unavailable status
- SQLite-backed live search queue with idempotent transcript row identity, leases, retries, watermarks, and safe status counters
- Live transcript producer and restart replay feed useful parsed transcript entries into the durable search queue without blocking message delivery
- Live queue worker converges queued transcript documents into generation JSONL with batching, retries, idempotent upsert, and stale-session filtering
- Exact-first lexical session retrieval with Phase 4 filters, snippets, labels, and safe degraded status
- Generation-owned LanceDB index metadata and lazy local embedding worker integration
- Hybrid session search with ready status, semantic candidate support, and lexical degraded fallback
- Sidebar search with bounded Web UI API contracts, compact status/filter controls, and grouped open-session result browsing
- Search hits now open the owning tmux session, fetch a bounded transcript window, and focus the matching message.
- The Web UI search flow passed mobile/layout, prompt-preservation, and full automated validation checks.
- Operational search status details now flow from typed backend contracts into an accessible expandable Web UI sidebar panel.
- Stale workers, failed queue rows, semantic errors, and worker launch failures now have regression coverage that keeps normal Codi paths usable.
- Opt-in local search benchmark with fake-provider tests, metrics-only status persistence, and documented Qwen fallback operations.

---
