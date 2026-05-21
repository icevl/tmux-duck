# Architecture Research

**Domain:** Local hybrid session search for Codi Web UI
**Researched:** 2026-05-21
**Confidence:** HIGH for Codi process boundaries and data flow; MEDIUM for final LanceDB tuning until implementation validation benchmarks the chosen embedding model and FTS maintenance cadence.

## Standard Architecture

### System Overview

```text
Browser Web UI
  |  debounced search/status requests
  v
Codi FastAPI process
  |-- existing /api/sessions, /api/ws, Telegram delivery, SessionMonitor
  |-- Search API proxy: no embedding/model work
  |-- Search ingest listener: offer-only, no disk/model work
  |-- Search queue writer: tiny async task, durable SQLite enqueue
  |-- Search worker supervisor: starts/restarts worker without awaiting readiness
  |
  +--> $CODEXBOT_DIR/search/search_queue.sqlite
       durable jobs, leases, retry state, index metadata

Separate local search worker process
  |-- owns embedding model runtime
  |-- owns LanceDB read/write connection
  |-- drains durable queue with live-priority batching
  |-- reads transcript JSONL for backfill/rebuild through shared parser
  |-- exposes local-only search/status control API
  |
  +--> $CODEXBOT_DIR/search/lancedb/
       chunks table, vector column, text column, FTS index, metadata fields

Runtime sources of truth
  |-- tmux windows and WindowState keyed by window_id such as @12
  |-- $CODEXBOT_DIR/state.json
  |-- $CODEXBOT_DIR/monitor_state.json
  |-- ~/.codex/sessions and ~/.claude/projects transcript JSONL
```

The search index should be treated as a derived cache, not application state. Transcript JSONL plus `WindowState` remain authoritative. If the worker, queue, or LanceDB directory is missing or corrupt, Codi should keep serving sessions, WebSocket events, Telegram topic delivery, terminal sockets, and monitor polling while search reports a degraded or indexing state.

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| `SessionMonitor` | Continue detecting live transcript messages and emitting `NewMessage` records. It should not know about embeddings or LanceDB. | Existing `src/codexbot/session_monitor.py`; add one extra listener. |
| Search ingest listener | Convert `NewMessage` into a lightweight indexing intent and return immediately. | `offer(msg)` into a bounded in-memory `asyncio.Queue` with `put_nowait`; drop counter/status on overflow. |
| Search queue writer | Persist offered live intents to a durable queue outside the monitor listener. | Background task in the main process; batch SQLite inserts via `asyncio.to_thread`; WAL mode. |
| Search queue DB | Preserve work across worker restarts and Codi restarts. | SQLite under `$CODEXBOT_DIR/search/search_queue.sqlite`; tables for jobs, leases, session index state, and metadata. |
| Search worker supervisor | Start and health-check the separate local worker without blocking API startup. | Main-process task started after normal web/monitor startup; restart with backoff; never required for core delivery. |
| Search worker process | Own model loading, batch embedding, LanceDB writes, LanceDB hybrid queries, retries, rebuilds, and optimize/maintenance. | `codexbot-search-worker` console entry or `python -m codexbot.search.worker`; local-only control API. |
| Search index store | Persist chunks, vectors, text, and filter metadata. | LanceDB table with `chunk_id`, `window_id`, `session_id`, `runtime`, `role`, `content_type`, `text`, `vector`, offsets, timestamps, generation, active flag. |
| Backfill planner | Enqueue bounded transcript backfill jobs for open sessions when DB is missing/stale or a session is first seen. | Main process emits session/backfill jobs; worker reads transcript bytes and checkpoints offsets. |
| FastAPI search routes | Authenticate browser search requests and proxy them to the worker with short timeouts. | New routes in `src/codexbot/web/api.py`; no model imports and no direct embedding. |
| React search UI | Debounced query input, grouped results, snippets, and indexing status. | Extend `web-ui/src/api.ts` and `Sidebar` or a dedicated search panel; never connect directly to worker. |

## Recommended Project Structure

```text
src/codexbot/
+-- search/
|   +-- __init__.py
|   +-- models.py          # Queue item, chunk, result, status dataclasses/Pydantic models
|   +-- queue.py           # SQLite queue, leases, retry/backoff, dedupe keys
|   +-- ingest.py          # Main-process nonblocking monitor listener and queue writer task
|   +-- supervisor.py      # Worker process start/stop/health/backoff
|   +-- client.py          # Async local client used by FastAPI routes
|   +-- worker.py          # Worker entrypoint and local-only search/status API
|   +-- backfill.py        # Transcript backfill planner/reader using shared parser
|   +-- index_store.py     # LanceDB schema, upsert, hybrid query, FTS optimize
|   +-- embeddings.py      # Local embedding runtime wrapper and batching
|   +-- snippets.py        # Snippet extraction/highlighting from chunk text
+-- web/
|   +-- api.py             # Add /api/search and /api/search/status routes only
+-- session_monitor.py     # Add listener registration only; no search logic

tests/codexbot/search/
+-- test_queue.py
+-- test_ingest.py
+-- test_backfill.py
+-- test_index_store.py
+-- test_web_search_api.py

web-ui/src/
+-- api.ts                 # Search response/status types and client methods
+-- components/
    +-- Sidebar.tsx        # Search input/results, or pass through to:
    +-- SessionSearch.tsx  # Dedicated component if Sidebar becomes crowded
```

### Structure Rationale

- **`src/codexbot/search/`:** Keeps indexing and retrieval boundaries visible. The main backend can import `ingest`, `queue`, `client`, and `supervisor`, but it must not import `embeddings` or `index_store` in hot delivery paths.
- **`worker.py` as a separate entrypoint:** Embedding model load, vector search, and FTS maintenance belong outside the Telegram/FastAPI event loop.
- **SQLite queue plus LanceDB index:** SQLite is the durable control plane; LanceDB is the retrieval data plane. This avoids turning LanceDB into a job queue and gives clear retry/rebuild semantics.
- **Shared transcript parser:** Backfill and live indexing should consume normalized entries from `TranscriptParser` rather than parsing Codex and Claude JSONL again.

## Architectural Patterns

### Pattern 1: Derived Index With Transcript Authority

**What:** Index records are rebuildable projections of transcript entries and window/session metadata. Each indexed chunk must carry enough source coordinates to reconnect it to the UI: `window_id`, `session_id`, `runtime`, `transcript_path`, `transcript_offset`, `transcript_index`, `role`, `content_type`, `timestamp`, and `content_hash`.

**When to use:** Always for V1. Search scope is open sessions, and the source of truth is already local JSONL plus Codi state.

**Trade-offs:** Rebuilds are straightforward and failures are recoverable. The cost is more metadata bookkeeping and explicit stale-session filtering at query time.

**Example chunk identity:**

```python
chunk_id = sha256(
    f"{session_id}:{transcript_offset}:{transcript_index}:{role}:{content_hash}".encode()
).hexdigest()
```

### Pattern 2: Offer-Only Monitor Listener

**What:** The monitor listener must only create an indexing intent and place it on an in-memory queue. It must not await SQLite, LanceDB, model inference, or worker RPC.

**When to use:** Live `NewMessage` ingestion from `SessionMonitor.add_listener`.

**Trade-offs:** A short in-memory window can be lost if the main process dies before the queue writer flushes. That is acceptable because transcripts are authoritative and the backfill/reconcile pass repairs gaps.

**Example:**

```python
async def search_monitor_listener(msg: NewMessage) -> None:
    search_ingest.offer(msg)  # put_nowait + metrics only
```

### Pattern 3: Lease-Based Durable Queue

**What:** The main process writes pending jobs; the worker claims jobs with a lease, marks them complete, and retries failures with exponential backoff. Leases expire if the worker crashes.

**When to use:** Live messages, backfill slices, session removal, rebuild requests, and index maintenance jobs.

**Trade-offs:** Slightly more schema than a plain file spool, but it gives crash recovery and observability.

**Recommended job fields:**

```text
id, kind, priority, window_id, session_id, runtime, transcript_path,
transcript_offset, transcript_index, content_hash, payload_json,
status, attempts, available_at, leased_until, last_error, created_at, updated_at
```

Use a unique dedupe key for live message jobs: `(session_id, transcript_offset, transcript_index, content_hash)`. Jobs without offsets should include a deterministic hash over `(session_id, role, timestamp, text)`.

### Pattern 4: Worker-Owned Model And Search API

**What:** The worker owns both document embeddings and query embeddings. FastAPI calls a local-only worker endpoint and applies auth/session filtering around the response.

**When to use:** `/api/search`, `/api/search/status`, and rebuild/maintenance commands.

**Trade-offs:** Search availability depends on the worker, but normal Codi delivery does not. Query latency is isolated to the search request.

**Recommended control surface:**

```text
GET  /status
POST /search       {query, limit, window_ids?, session_ids?}
POST /rebuild      {scope: "open_sessions" | "session", session_id?}
POST /shutdown     local supervisor only
```

Prefer a Unix domain socket under `$CODEXBOT_DIR/search/worker.sock` on macOS/Linux. If a TCP fallback is needed, bind to `127.0.0.1` and require a generated token stored under `$CODEXBOT_DIR/search/worker_secret`.

### Pattern 5: Generation-Based Rebuild

**What:** Rebuild into a new generation instead of mutating the active generation in place. Search reads only `active_generation`; after successful backfill and index creation, atomically switch the metadata pointer.

**When to use:** Missing DB, schema change, embedding model change, corruption recovery, explicit rebuild.

**Trade-offs:** Uses extra disk during rebuild but prevents half-built search results from replacing a working index.

**Implementation shape:** `index_meta(active_generation)`, LanceDB rows with `generation`, and a cleanup job that removes old inactive generations after the swap.

## Data Flow

### Live Message Indexing Flow

```text
Runtime transcript JSONL append
  -> SessionMonitor reads new bytes and builds NewMessage
  -> existing EventBus listener publishes WebSocket message
  -> existing Telegram callback enqueues topic delivery
  -> search ingest listener offers IndexIntent and returns immediately
  -> search queue writer persists IndexIntent to SQLite
  -> worker claims live jobs before backfill jobs
  -> worker batches until 32 items or 60 seconds
  -> worker embeds batch and merge-upserts chunks into LanceDB
  -> worker updates queue/job/session index state
  -> worker periodically optimizes LanceDB FTS/index maintenance
  -> FastAPI/Web UI status can show queue depth and indexed-through offsets
```

Important: the 32-item/60-second rule should apply to embedding/index flushes, not to durable enqueue. Persisting the queue should happen promptly in small cheap batches so a worker restart does not lose live work.

### Initial Backfill Flow

```text
Codi startup
  -> main process starts normal SessionMonitor, status polling, FastAPI, WebSocket
  -> search supervisor starts worker asynchronously
  -> backfill planner enumerates open window states and transcript paths
  -> planner enqueues one backfill_session job per open session
  -> worker creates DB/schema if missing
  -> worker reads transcript JSONL through shared parser in bounded slices
  -> worker checkpoint: session_id -> last_indexed_offset
  -> worker yields between slices and prioritizes newer live jobs
  -> UI sees status=indexing and partial=true until backfill completes
```

Backfill should slice large transcripts by byte offset or parsed-entry count. A safe first target is 128-512 parsed text chunks per worker write transaction, then tune after local Mac mini profiling.

### Search Query Flow

```text
User types query in Web UI
  -> React debounces input
  -> GET /api/search?q=...&limit=...
  -> FastAPI authenticates user
  -> FastAPI collects live allowed window_ids from session_manager
  -> FastAPI calls local worker /search with query and allowed window_ids
  -> worker embeds query
  -> worker runs LanceDB hybrid search: vector query + text query + filters
  -> worker groups hits by session/window and extracts snippets
  -> FastAPI drops stale/non-live windows and returns result/status payload
  -> UI renders grouped sessions and snippets
  -> selecting a result opens the session by window_id
```

Do not let the browser talk to the worker directly. Keep web auth, live-window filtering, and routing keyed by tmux `window_id` in the main FastAPI process.

### Search Result Navigation Flow

V1 can select the session and show snippets. A stronger follow-up should add transcript-position navigation:

```text
Search hit with window_id + transcript_offset + transcript_index
  -> UI selects window_id
  -> ChatView requests messages around that transcript position
  -> backend reads transcript through existing history/parser path
  -> ChatView scrolls/highlights the matched message if loaded
```

That likely requires extending `GET /api/sessions/{window_id}/messages` with `around_offset` and `around_index`, because the current endpoint pages before/after offsets but does not fetch a centered window around a hit.

### Session Removal/Rebinding Flow

```text
Session killed, rebound, or no longer open
  -> existing session state changes
  -> main process enqueues session_removed or session_seen/backfill job
  -> worker marks old rows inactive or deletes by session_id/window_id
  -> search endpoint filters results against current live window_ids anyway
```

Filtering at query time is mandatory. Queue-driven cleanup is useful for disk hygiene but must not be trusted as the only stale-result defense.

## State Management

```text
Authoritative state:
  $CODEXBOT_DIR/state.json
  $CODEXBOT_DIR/monitor_state.json
  Codex/Claude transcript JSONL files
  tmux windows, addressed by window_id

Search control state:
  $CODEXBOT_DIR/search/search_queue.sqlite
    queue_items
    session_index_state
    index_meta
    dead_letters

Search retrieval state:
  $CODEXBOT_DIR/search/lancedb/
    chunks table
    text FTS index
    vector index when worthwhile
```

`index_meta` should record `schema_version`, `embedding_model`, `embedding_dim`, `active_generation`, `worker_pid`, `last_heartbeat_at`, `last_successful_batch_at`, `last_error`, and coarse counts. The Web UI does not need internal details, but it does need enough status to distinguish "not ready", "indexing", "partial results", "ready", and "degraded".

## Backfill And Live Batching Strategy

1. **Startup should not wait for search.** Start search supervisor after normal Codi startup work is scheduled. If worker start fails, write status and keep Codi running.
2. **Durable enqueue should be fast.** The main process queue writer persists live intents quickly in small SQLite batches. It should not wait for the 60-second indexing batch window.
3. **Live jobs outrank backfill.** Worker scheduling should drain live `message_upsert` jobs first, then consume backfill slices. This keeps new turns searchable soon after completion even during first startup.
4. **Batch embedding exactly where it matters.** The worker flushes live embedding/index batches when 32 queued chunks accumulate or 60 seconds pass, whichever happens first.
5. **Backfill slices checkpoint often.** Store `last_indexed_offset` per `session_id` so a worker restart resumes without rereading the whole transcript.
6. **Use idempotent upserts.** LanceDB `merge_insert` by `chunk_id` is the right write shape for duplicates, retries, and rebuild overlap.
7. **Maintain FTS outside the hot path.** LanceDB docs say new rows require `table.optimize()` to fold them into the existing FTS index. Run optimize after batch thresholds or a maintenance interval, not after every message.

## Failure, Retry, And Rebuild Behavior

| Failure | Expected Behavior | Recovery |
|---------|-------------------|----------|
| Worker not running | `/api/search/status` reports unavailable; `/api/search` returns degraded/empty or 503. WebSocket, Telegram, monitor, and session APIs continue. | Supervisor restarts with backoff; queue accumulates. |
| Embedding model load fails | Worker stays degraded and does not claim new embedding jobs indefinitely. | Status exposes error; queued jobs remain pending for retry after config/model fix. |
| One queue job fails | Job attempt increments; `available_at` moves forward with backoff. | Retry up to a configured limit, then dead-letter with source metadata. |
| Worker crashes mid-batch | Leased jobs expire. | Next worker reclaims expired leases; idempotent chunk IDs prevent duplicates. |
| Queue DB temporarily locked | Main queue writer retries briefly without blocking monitor listener. | In-memory queue may back up; status shows enqueue lag. Backfill can repair any dropped live intents. |
| LanceDB FTS/vector maintenance slow | Worker marks maintenance busy; search can return partial/stale lexical state. | Run optimize/reindex in maintenance windows or after thresholds. |
| Index schema/model changes | Existing generation becomes stale. | Build new generation/table, create FTS index, optimize, then switch `active_generation`. |
| Corrupt search DB | Search disabled, core Codi unaffected. | Rename broken DB directory/file, create fresh generation, enqueue open-session rebuild. |
| Session deleted/rebound | Old results must not appear. | Query filters live window IDs; cleanup job marks/deletes stale rows. |

## Anti-Patterns

### Embedding In FastAPI Or Monitor Callbacks

**What people do:** Import the embedding model in `web/api.py`, call LanceDB from `/api/search`, or await indexing directly inside `SessionMonitor.add_listener`.

**Why it is wrong:** Model load and inference can stall the same event loop that serves WebSocket events, terminal sockets, Telegram delivery callbacks, and monitor polling.

**Do this instead:** Main FastAPI proxies search requests to the worker and uses only short async I/O with timeouts.

### Treating Search As Source Of Truth

**What people do:** Store session identity, message order, or transcript text only in the search DB.

**Why it is wrong:** The index is allowed to be deleted and rebuilt. It must not become required for history, routing, or delivery.

**Do this instead:** Store source coordinates and reconstruct from transcript JSONL when needed.

### Multiple LanceDB Writers

**What people do:** Let the main process, backfill task, and worker all write to LanceDB.

**Why it is wrong:** It makes locking, FTS maintenance, generation swaps, and retry semantics hard to reason about.

**Do this instead:** Worker is the single LanceDB writer. The main process writes only the SQLite queue/control plane.

### Independent Transcript Parsing

**What people do:** Reimplement Codex/Claude JSONL parsing inside the worker or frontend.

**Why it is wrong:** The repo already has runtime-specific transcript normalization. A second parser will drift and produce duplicate/missing/misordered chunks.

**Do this instead:** Worker backfill imports and uses `TranscriptParser`; live indexing consumes normalized `NewMessage` payloads.

### Searching By Session Name

**What people do:** Return or filter by display names, tmux names, or cwd strings as primary identity.

**Why it is wrong:** Codi's invariant is routing by tmux `window_id`; names and cwd values can change or duplicate.

**Do this instead:** Every result carries `window_id`; `session_id` is secondary source identity.

## Integration Points

### External And Local Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| LanceDB | Worker-only embedded DB connection under `$CODEXBOT_DIR/search/lancedb/`. | Official docs support local path connections, FTS index creation, hybrid search with vector/text queries, `merge_insert`, and `optimize()` for incremental FTS/index maintenance. |
| SQLite | Main writer plus worker reader/claimer with WAL. | Use as the durable job/control plane, not for vector retrieval. |
| Embedding runtime | Worker-owned local model wrapper. | Keep pluggable; Qwen3-Embedding-0.6B is the project candidate, but implementation should validate memory, latency, embedding dimension, and packaging on the target Mac mini. |
| FastAPI | Authenticated proxy routes in the existing app. | Do not use FastAPI `BackgroundTasks` for long-lived indexing; worker is separate. |
| React Web UI | Typed API client plus search component. | Use debounced REST for queries; WebSocket may carry status-change events later. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `SessionMonitor` -> search ingest | Extra listener, offer-only | Must return immediately and tolerate overflow. |
| search ingest -> queue DB | Background writer task | Use small durable batches and `asyncio.to_thread` for SQLite writes. |
| main process -> worker | Supervisor and local-only client | Short timeouts; worker readiness is optional. |
| worker -> LanceDB | Direct single-writer connection | Owns all index writes, hybrid reads, and optimize/reindex. |
| FastAPI -> Web UI | `/api/search`, `/api/search/status` | Results include status so the UI can label partial/degraded results. |
| search results -> ChatView | `window_id` selection, optional offset navigation | Add centered history fetch in a later phase if hit jumping is required. |

## Suggested Build Order

1. **Search Control Plane**
   - Add `src/codexbot/search/models.py`, `queue.py`, and status models.
   - Implement SQLite queue with dedupe, leases, retries, dead letters, and metadata.
   - Add `/api/search/status` returning `disabled/not_ready/indexing/ready/degraded`.
   - This phase proves persistence and observability without model risk.

2. **Nonblocking Live Enqueue**
   - Add `search.ingest` listener and queue writer.
   - Register the listener after existing EventBus listener and without changing Telegram delivery.
   - Unit-test that listener overflow and queue write failures do not block monitor dispatch.

3. **Worker Skeleton And Backfill**
   - Add supervisor, worker process, local status API, and transcript backfill jobs.
   - Worker reads open-session transcripts through `TranscriptParser`, writes deterministic chunks without embeddings first, and checkpoints offsets.
   - This phase validates process ownership and rebuild behavior.

4. **LanceDB Hybrid Indexing**
   - Add embedding wrapper, LanceDB table schema, merge-upsert, FTS index creation, hybrid search, and optimize cadence.
   - Validate local Mac mini latency/memory and tune chunk sizes/batch limits.
   - Search endpoint can return backend results before the full UI is polished.

5. **Web UI Search Flow**
   - Add debounced search input/results with status labels and grouped session snippets.
   - Selecting a result opens the session by `window_id`.
   - Add transcript-position jump only after result shape and history paging are stable.

6. **Rebuild And Maintenance UX**
   - Add explicit rebuild trigger, stale generation cleanup, corrupt DB recovery, and richer status display.
   - This depends on the worker, queue, and status protocol being stable.

**Phase dependencies:**
- Queue/status must precede worker indexing.
- Nonblocking live enqueue must precede live embedding.
- Backfill must precede reliable query UX because first startup can have no DB.
- Hybrid search should precede polished UI ranking, otherwise UI code will bake in placeholder ranking assumptions.
- Rebuild UX should come after generation metadata is implemented.

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Single local user, dozens of open sessions | Recommended architecture is sufficient. Keep worker low priority and search optional. |
| Hundreds of open sessions or very large transcripts | Increase backfill slice granularity, expose queue/backfill ETA, tune LanceDB optimize cadence, and consider per-session rebuild controls. |
| Multi-user hosted deployment | Out of V1 scope. Would need per-user authorization filters, stronger worker auth, resource quotas, and likely a real service supervisor. |

### Scaling Priorities

1. **First bottleneck:** Embedding throughput and model memory. Fix with batching, smaller model choice, and live-priority scheduling before changing the Codi delivery architecture.
2. **Second bottleneck:** FTS/vector maintenance after many updates. Fix with explicit optimize/reindex thresholds and generation rebuilds.
3. **Third bottleneck:** UI result navigation for deep history. Fix with transcript-position paging rather than loading full histories.

## Verification Implications

- Unit-test the queue with real `tmp_path` SQLite files, lease expiry, retries, dedupe, and dead-letter behavior.
- Unit-test the monitor listener to prove it calls only `offer()` and returns when the in-memory queue is full.
- Unit-test backfill with fixture Codex and Claude JSONL entries through `TranscriptParser`.
- FastAPI tests should patch the search client, not start the worker or model.
- Worker/index-store tests can use a temporary LanceDB directory and a fake deterministic embedder before testing the real embedding runtime.
- Frontend validation remains `pnpm --dir web-ui build`; there is no current frontend test runner.

## Sources

- `.planning/PROJECT.md` - project requirements, V1 scope, LanceDB-first and worker-process decisions.
- `.planning/codebase/ARCHITECTURE.md` - existing Codi process boundaries, EventBus, SessionMonitor, and Web UI architecture.
- `.planning/codebase/INTEGRATIONS.md` - local state paths, transcript sources, FastAPI/WebSocket surface, and absence of an existing DB server.
- `.planning/codebase/TESTING.md` - pytest/FastAPI/frontend verification patterns.
- `src/codexbot/session_monitor.py` - current listener fan-out, monitor loop, and `NewMessage` source fields.
- `src/codexbot/web/events.py` - WebSocket EventBus delivery shape.
- `src/codexbot/web/api.py` - existing authenticated FastAPI/session/history endpoints.
- `src/codexbot/session.py` - `WindowState`, session resolution, transcript history cache, and shared transcript parser usage.
- LanceDB hybrid search docs via Context7: https://docs.lancedb.com/search/hybrid-search
- LanceDB full-text search docs via Context7: https://docs.lancedb.com/search/full-text-search
- LanceDB update/upsert docs via Context7: https://docs.lancedb.com/tables/update
- LanceDB quickstart/local connection docs via Context7: https://docs.lancedb.com/quickstart
- LanceDB reindex/optimize docs via Context7: https://docs.lancedb.com/indexing/reindexing
- FastAPI background task docs via Context7: https://fastapi.tiangolo.com/tutorial/background-tasks/ - background tasks exist for after-response work, but this architecture intentionally uses a separate worker for long-lived indexing.

---
*Architecture research for: Codi Web UI session search*
*Researched: 2026-05-21*
