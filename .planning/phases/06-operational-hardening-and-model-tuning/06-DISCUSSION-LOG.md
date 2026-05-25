# Phase 6: Operational Hardening and Model Tuning - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-25
**Phase:** 6-Operational Hardening and Model Tuning
**Areas discussed:** Status UI, Degraded Search, Benchmarks, Queue Recovery

---

## Status UI

### Status Surface

| Option | Description | Selected |
|--------|-------------|----------|
| Search Panel | Extend the existing search sidebar status chip/details, reusing `/api/search/status` and `SessionSearch`. | ✓ |
| Ops Panel | Add a separate diagnostics panel/modal for richer operational detail, with more UI surface to maintain. | |
| API Only | Expose full status through authenticated API and keep the Web UI compact. | |

**User's choice:** Search Panel
**Notes:** The existing search sidebar is the preferred operational surface for Phase 6 status.

### Status Density

| Option | Description | Selected |
|--------|-------------|----------|
| Expandable | Keep the chip/counts compact, with heartbeat, queue lag, progress, and errors available on expand. | ✓ |
| Always Visible | Show all core metrics under the search box all the time for maximum transparency. | |
| Warnings Only | Show details only when indexing is degraded, failed, stale, or behind. | |

**User's choice:** Expandable
**Notes:** Default UI should stay quiet while preserving access to detailed operational state.

### Status Refresh

| Option | Description | Selected |
|--------|-------------|----------|
| Poll + Events | Poll `/api/search/status` on a modest interval and refresh immediately after search/session events. | ✓ |
| WebSocket Only | Publish status changes over the existing event bus, but rely on reconnect/history fallback for missed events. | |
| On Demand | Refresh only when opening/searching the panel, minimizing background work but making lag less visible. | |

**User's choice:** Poll + Events
**Notes:** Status refresh should be timely but must not put indexing/model work on message delivery paths.

### Recovery Actions

| Option | Description | Selected |
|--------|-------------|----------|
| Read-Only + Commands | Show safe status plus suggested local commands; avoids adding Web UI write controls to search ops. | ✓ |
| Retry Buttons | Add authenticated Web UI actions to retry failed queue items or rebuild the index. | |
| Read-Only Only | Report the problem and recent errors, but leave recovery outside the UI. | |

**User's choice:** Read-Only + Commands
**Notes:** Phase 6 should provide actionable local guidance without adding Web UI mutation controls.

---

## Degraded Search

### Semantic Unavailable

| Option | Description | Selected |
|--------|-------------|----------|
| Lexical Degraded | Return lexical/metadata results with an explicit degraded status; matches the existing fallback direction. | ✓ |
| Unavailable | Return no results until embeddings and LanceDB are fully ready. | |
| Last Good Only | Serve only the previous completed semantic generation, even if newer transcript data is not included. | |

**User's choice:** Lexical Degraded
**Notes:** Semantic failures should not make search useless when indexed text exists.

### First Generation Missing

| Option | Description | Selected |
|--------|-------------|----------|
| Status Only | Show indexing/backfill progress and no results; avoids request-time transcript scans on old sessions. | ✓ |
| Live Scan | Do a bounded lexical scan of active transcripts on each search request, with timeout and partial results. | |
| Hide Search | Disable the search box until initial indexing completes. | |

**User's choice:** Status Only
**Notes:** Before first generation, avoid expensive request-time history scans.

### Warning Prominence

| Option | Description | Selected |
|--------|-------------|----------|
| Inline Labels | Show a warning line/status chip and label result batches as lexical-only or partial without blocking use. | ✓ |
| Blocking Notice | Show a prominent panel before results so users must acknowledge degraded quality. | |
| Subtle Only | Keep only the status chip changed to Degraded, with no extra result-level labeling. | |

**User's choice:** Inline Labels
**Notes:** Degraded quality should be visible but should not block result use.

### Failure Boundary

| Option | Description | Selected |
|--------|-------------|----------|
| Isolate Search | Cap/timeout search work, keep chat/session/terminal/Telegram delivery unaffected, and surface degraded status. | ✓ |
| Pause Indexing | Stop live indexing until a rebuild succeeds, reducing load but allowing search freshness to drift. | |
| Retry Aggressively | Keep retrying failed search work immediately, favoring recovery speed over local resource stability. | |

**User's choice:** Isolate Search
**Notes:** Search degradation must not affect existing Codi delivery surfaces.

---

## Benchmarks

### Benchmark Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Fixtures + Smoke | Use real Codi transcript fixtures plus the existing smoke index path to measure embedding, upsert, query, and degraded fallback. | ✓ |
| Full Corpus | Benchmark all currently open session history, closer to reality but slow and noisy on local machines. | |
| Smoke Only | Keep a tiny one-row smoke path; fast but too weak to tune batch/chunk/model defaults. | |

**User's choice:** Fixtures + Smoke
**Notes:** Benchmark should be representative without sweeping the full live corpus.

### Benchmark Thresholds

| Option | Description | Selected |
|--------|-------------|----------|
| Configurable Baseline | Record measured defaults and warn/fail against configurable thresholds instead of hard-coding one machine profile. | ✓ |
| Fixed Gates | Set concrete limits for memory, throughput, and query latency directly in tests/scripts. | |
| Report Only | Generate metrics but never fail validation from performance numbers. | |

**User's choice:** Configurable Baseline
**Notes:** Thresholds should be local-machine friendly and configurable.

### Model Policy

| Option | Description | Selected |
|--------|-------------|----------|
| Lexical Fallback | Keep Qwen3 as default, document env overrides, and run lexical-only degraded search if semantic validation fails. | ✓ |
| Smaller Model | Automatically fall back to a smaller embedding model after benchmark failure, adding another model path to validate. | |
| Block Search | Mark search unavailable until Qwen3 works, preserving quality but losing lexical utility. | |

**User's choice:** Lexical Fallback
**Notes:** Qwen3 remains the semantic default, but validation failure should not block lexical search.

### Benchmark Command

| Option | Description | Selected |
|--------|-------------|----------|
| Opt-In Command | Add a documented local command/script with fixture metrics; keep normal tests dependency-light. | ✓ |
| Normal Checks | Run the benchmark as part of the standard test/check suite, even if it loads model/index dependencies. | |
| Manual Notes | Document ad-hoc commands only, with no first-class benchmark entry point. | |

**User's choice:** Opt-In Command
**Notes:** The benchmark should be first-class but not part of normal lightweight checks.

---

## Queue Recovery

### Heartbeat Handling

| Option | Description | Selected |
|--------|-------------|----------|
| Degraded Status | Mark search/indexing degraded or stale, show last heartbeat/error, and leave chat/session/terminal delivery untouched. | ✓ |
| Auto Restart | Try to restart the worker automatically when heartbeat is stale, with more moving parts to guard. | |
| Ignore It | Keep search status based only on generation/index files and avoid heartbeat-based alerts. | |

**User's choice:** Degraded Status
**Notes:** Stale heartbeat is a search signal, not a global service failure.

### Failed Queue Items

| Option | Description | Selected |
|--------|-------------|----------|
| Dead-Letter | Use bounded retries, keep failed items inspectable in status, and continue processing later items. | ✓ |
| Retry Forever | Keep retrying until success, maximizing eventual indexing but risking stuck lag. | |
| Drop Silently | Remove failed items after retry limit, reducing noise but hiding lost indexing work. | |

**User's choice:** Dead-Letter
**Notes:** Repeated failures should be visible and should not block later queue items.

### Work Priority

| Option | Description | Selected |
|--------|-------------|----------|
| Live Freshness | Prefer new active-session turns after the initial generation exists, so current Web UI search catches up quickly. | ✓ |
| Backfill First | Finish historical completeness before processing new messages, making fresh sessions lag longer. | |
| Strict FIFO | Process exactly in queue order, simpler but less tuned for active session use. | |

**User's choice:** Live Freshness
**Notes:** Active-session freshness matters more than perfect historical completeness after initial generation.

### Process Boundary

| Option | Description | Selected |
|--------|-------------|----------|
| Worker Boundary | Keep model/index work in the search worker path where possible; backend request paths only read status/results and degrade safely. | ✓ |
| Backend Loop | Keep live draining inside the backend process for simpler coordination, accepting model-stack risk in the web process. | |
| Manual Worker | Only index when a local command is run, minimizing background load but losing automatic freshness. | |

**User's choice:** Worker Boundary
**Notes:** Expensive model and index work should stay out of backend request paths where possible.

## the agent's Discretion

- Exact status polling interval, heartbeat stale threshold, benchmark metric output format, and fixture layout are left to implementation judgment within the constraints captured in CONTEXT.md.

## Deferred Ideas

- Web UI backend/model tuning mutation controls.
- Closed or resumable historical session search.
- Telegram search parity.
- Advanced boolean, regex, and query-qualifier syntax.
