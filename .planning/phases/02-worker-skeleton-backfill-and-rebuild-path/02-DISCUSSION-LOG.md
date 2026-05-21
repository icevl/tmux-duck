# Phase 2: Worker Skeleton, Backfill, and Rebuild Path - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-05-21
**Phase:** 2-Worker Skeleton, Backfill, and Rebuild Path
**Areas discussed:** Worker/backfill lifecycle, Open-session corpus, Rebuild/state ownership, Visible readiness

---

## Worker/backfill lifecycle

### What worker shape should Phase 2 establish for startup backfill?

| Option | Description | Selected |
|--------|-------------|----------|
| Worker CLI | Add a lightweight local worker entrypoint now, keeping model/index imports out of FastAPI and matching the project isolation decision. | yes |
| In-process task | Simpler startup integration, but it risks another migration when embeddings and LanceDB are added. | |
| Manual rebuild only | Lowest coupling now, but first-run async indexing would not happen automatically. | |

**User's choice:** Worker CLI
**Notes:** Phase 2 should establish the worker/process boundary before embeddings and index writes exist.

### When should Codi start the Phase 2 worker CLI?

| Option | Description | Selected |
|--------|-------------|----------|
| Auto with backend | Start it from backend lifecycle when web/search is enabled, so first-run backfill happens without extra operator steps. | yes |
| Explicit command | Require an operator to run the worker separately, useful for debugging but weaker for the first-run UX. | |
| Config gated | Start automatically only when a new enable flag is set, reducing surprise but making search easier to misconfigure. | |

**User's choice:** Auto with backend
**Notes:** First-run indexing should happen without a separate manual command.

### How much worker supervision belongs in Phase 2?

| Option | Description | Selected |
|--------|-------------|----------|
| Heartbeat only | Record worker state and failures under search state, but avoid restart loops until operational hardening. | yes |
| Restart backoff | More robust immediately, but pulls Phase 6 failure policy into this phase. | |
| No supervision | Simplest worker launch, but status cannot explain worker failures well. | |

**User's choice:** Heartbeat only
**Notes:** Record state and failures now; defer restart policy.

### What should trigger Phase 2 backfill/rebuild?

| Option | Description | Selected |
|--------|-------------|----------|
| Missing plus rebuild | Auto-backfill when no active search generation exists and provide an explicit rebuild path that creates a new generation. | yes |
| Every startup reconcile | Keeps state aggressively fresh, but can do unnecessary transcript scans before live queue semantics exist. | |
| Only missing index | Smallest first-run path, but does not satisfy the rebuild success criterion well. | |

**User's choice:** Missing plus rebuild
**Notes:** Rebuild should create a fresh generation instead of mutating active state in place.

---

## Open-session corpus

### How should Phase 2 discover sessions to backfill?

| Option | Description | Selected |
|--------|-------------|----------|
| Open windows | Enumerate current tmux-backed WindowState records, resolve each to its Codex/Claude transcript, and skip closed sessions. | yes |
| Monitor tracked | Use monitor_state tracked sessions, but that can include stale sessions outside the v1 open-session scope. | |
| Transcript scan | Glob Codex/Claude transcript directories directly, which risks indexing closed sessions too early. | |

**User's choice:** Open windows
**Notes:** The v1 corpus is open tmux-backed sessions only.

### What parser interface should the backfill path consume?

| Option | Description | Selected |
|--------|-------------|----------|
| ParsedEntry stream | Add a backend helper that yields ParsedEntry plus transcript source/offset/index, reusing TranscriptParser without depending on Web UI history DTOs. | yes |
| HistorySnapshot | Reuses an existing API-shaped cache, but couples indexing to browser history payload shape. | |
| Raw JSONL | Gives maximum control, but violates the existing transcript-parser boundary. | |

**User's choice:** ParsedEntry stream
**Notes:** Backfill should reuse parser logic while avoiding Web UI DTO coupling.

### Which parsed transcript entries should Phase 2 include in the backfill corpus?

| Option | Description | Selected |
|--------|-------------|----------|
| Text-bearing UI entries | Index user, assistant, tool_use, tool_result, local_command, and other displayed text entries; skip completion markers and image-only payloads. | |
| User/assistant only | Keeps the corpus smaller but misses tool calls, command output, and errors the user often searches for. | |
| Everything parsed | Maximizes recall but may add noisy completion/status entries and binary-adjacent image records. | yes |

**User's choice:** Everything parsed
**Notes:** Treat this as broad recall over every parsed text-bearing entry.

### How should Phase 2 represent long or non-standard parsed entries?

| Option | Description | Selected |
|--------|-------------|----------|
| Chunk text docs | Create one or more chunk documents per ParsedEntry, preserving chunk_index so long tool/output messages are ready for search. | yes |
| One doc per entry | Simpler backfill skeleton, but long outputs may need rework when retrieval arrives. | |
| Metadata only | Store provenance for unusual entries without indexing text, reducing noise but weakening the broad-corpus decision. | |

**User's choice:** Chunk text docs
**Notes:** Preserve chunk identity now so retrieval can index long messages later.

---

## Rebuild/state ownership

### How should Phase 2 structure rebuildable search generations?

| Option | Description | Selected |
|--------|-------------|----------|
| Atomic generations | Build into a new generation directory and only mark it active when backfill succeeds, matching the Phase 1 generation metadata contract. | yes |
| In-place rebuild | Simpler filesystem layout, but search/status can see half-written state. | |
| Single append store | Avoids swaps, but makes rebuild and stale cleanup harder. | |

**User's choice:** Atomic generations
**Notes:** Avoid exposing half-written active state.

### What explicit rebuild interface should Phase 2 expose?

| Option | Description | Selected |
|--------|-------------|----------|
| Worker CLI command | Provide a local rebuild command/path for development and operations, while Web UI controls stay out of Phase 2. | yes |
| Authenticated API | Useful for future Web UI controls, but pulls product surface work before search results exist. | |
| Internal only | Keeps implementation private, but makes rebuild harder to verify manually. | |

**User's choice:** Worker CLI command
**Notes:** Rebuild is local/operator-facing in this phase.

### Where should Phase 2 persist worker and backfill metadata?

| Option | Description | Selected |
|--------|-------------|----------|
| Search namespace | Store worker status, backfill manifest, and generation metadata under CODEXBOT_DIR/search only. | yes |
| Monitor state | Convenient for offsets, but explicitly violates the Phase 1 search-state boundary. | |
| Repo files | Easy to inspect in development, but wrong for runtime-derived local state. | |

**User's choice:** Search namespace
**Notes:** Search runtime state must not write monitor or session authoritative state.

### How should Phase 2 recover if the process stops during an initial backfill or rebuild?

| Option | Description | Selected |
|--------|-------------|----------|
| Restart generation | Treat incomplete generations as inactive and start a fresh idempotent backfill on next startup or rebuild command. | yes |
| Resume watermarks | More efficient for huge histories, but overlaps Phase 3 queue/watermark persistence work. | |
| Expose partial | Fastest to show some data, but users may mistake incomplete state for ready search. | |

**User's choice:** Restart generation
**Notes:** Fine-grained resume belongs to the later live queue/convergence phase.

---

## Visible readiness

### What should `/api/search/status` report while Phase 2 backfill is running?

| Option | Description | Selected |
|--------|-------------|----------|
| Building state | Return state=building with progress counters and available=false, so clients can distinguish first-run work from missing search. | yes |
| Still missing | Keeps the current stub simple, but hides that backfill is already underway. | |
| Unavailable only | Accurate about no query backend, but too vague for startup/backfill progress. | |

**User's choice:** Building state
**Notes:** Status should show that backfill is underway.

### Which counters should Phase 2 populate now?

| Option | Description | Selected |
|--------|-------------|----------|
| Backfill counters | Populate open_sessions, indexed_sessions, indexed_chunks, failed_items, and current generation data; leave live queue lag for Phase 3. | yes |
| All counters | Makes the API look complete, but queue counters would be placeholders before live queue exists. | |
| Only generation | Minimal status, but users cannot tell whether initial indexing is progressing. | |

**User's choice:** Backfill counters
**Notes:** Queue-specific metrics are deferred.

### How should completed Phase 2 backfill report before retrieval exists?

| Option | Description | Selected |
|--------|-------------|----------|
| Unavailable with generation | Show active generation/counters but keep available=false because the query backend is not implemented until retrieval phase. | yes |
| Ready false positive | Would communicate the index exists, but can mislead clients into sending real searches. | |
| Partial forever | Avoids claiming readiness, but hides that backfill succeeded. | |

**User's choice:** Unavailable with generation
**Notes:** Do not report real query readiness until retrieval exists.

### How should Phase 2 surface worker or backfill errors?

| Option | Description | Selected |
|--------|-------------|----------|
| Status reason | Persist recent error summaries under search state and expose them through status reason/counters without breaking other Codi features. | yes |
| Raise API errors | Makes failures loud, but turns search degradation into transport failures. | |
| Logs only | Simplest, but Web UI and operators cannot see why search is not progressing. | |

**User's choice:** Status reason
**Notes:** Search degradation must not break existing Codi surfaces.

---

## the agent's Discretion

No explicit "you decide" choices were selected. Exact module names, file names,
helper boundaries, chunk sizes, and test factoring remain implementation
details constrained by CONTEXT.md.

## Deferred Ideas

- Worker restart/backoff supervision.
- Durable live queue, queue lag, leases, retries, dead letters, and resumable
  watermarks.
- LanceDB, embeddings, hybrid retrieval, and query ranking.
- Web UI search/rebuild controls and hit navigation.
