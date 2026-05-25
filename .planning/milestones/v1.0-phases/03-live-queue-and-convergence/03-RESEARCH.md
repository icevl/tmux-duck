# Phase 3 Research: Live Queue and Convergence

**Phase:** 03-live-queue-and-convergence
**Researched:** 2026-05-22
**Domain:** Local durable queueing, transcript replay, and derived search-state convergence
**Confidence:** HIGH for local Codi architecture and state boundaries; MEDIUM for exact SQLite schema names until implementation chooses the smallest clean API.

## Research Question

What needs to be known to plan Phase 3 well?

Phase 3 must keep new Codex and Claude transcript activity from being lost while
initial backfill is running, then converge that activity into the derived search
generation without duplicate documents. It needs durable queue leases, retries,
dead-letter state, transcript watermarks, and stale-session handling, but it
must not implement semantic retrieval, LanceDB/Faiss ranking, browser search UX,
or historical closed-session search.

<user_constraints>
## User Constraints from CONTEXT.md

### Locked Decisions

- Live indexing queues useful parsed transcript entries, not whole completed
  turns.
- Queue creation attaches to `SessionMonitor` transcript events.
- Message delivery must continue when queue writes or drains are slow; search
  status reports lag/failure instead.
- Queue content matches Phase 2 broad useful-text backfill: user text,
  assistant text, meaningful tool/output text, and parser-exposed textual
  entries.
- Queue lifecycle identity is separate from transcript-derived search row
  identity.
- Search row identity comes from `TranscriptProvenance` and
  `SearchRowIdentity`, not mutable tmux window metadata.
- Live indexing reuses deterministic backfill chunking and performs idempotent
  upserts by stable row identity.
- Backfill/live overlap uses per-transcript watermarks plus idempotent upserts.
- Live batches converge into the same writable generation as backfill; no live
  overlay index in this phase.
- Restart recovery replays from the last safe transcript coordinate rather than
  skipping ahead.
- Live batches drain when 32 queue items are ready or 60 seconds pass since the
  previous flush.
- Queue processing uses bounded retries with persisted attempt counts, leases,
  last error, and dead-letter state.
- Queue lag and failures degrade search status only.
- Documents for closed tmux sessions are marked stale and hidden from normal v1
  results.

### the agent's Discretion

- Exact file names, SQLite table layout or JSONL structure, lease timeout,
  retry count, batch scheduler implementation, and status field factoring are
  implementation choices as long as the decisions above are preserved.

### Deferred Ideas

- Semantic retrieval, LanceDB/Faiss ranking, Web UI search experience, and
  historical closed-session search remain out of scope.
</user_constraints>

<architectural_responsibility_map>
## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|--------------|----------------|-----------|
| Durable live queue | Backend worker/storage | Transcript monitor | Queue rows, leases, attempts, and dead-letter state are local derived search state under `CODEXBOT_DIR/search`. |
| Queue producer | Transcript monitor listener | Search queue service | `SessionMonitor` already observes ordered parsed entries and can schedule nonblocking producer work. |
| Transcript replay/watermarks | Backend worker/storage | Session manager/parser | Durable watermarks require worker-owned scanning of transcript files, not monitor offsets in `monitor_state.json`. |
| Document convergence | Backend worker/storage | Search backfill document builder | Live documents must share Phase 2 document/chunk identity and generation artifacts. |
| Stale-session filtering | Search client/status layer | Session manager/tmux | Current open tmux window state determines which docs are routeable without changing row identity. |
</architectural_responsibility_map>

## Key Findings

### 1. Use SQLite for Queue State, Not Ad Hoc JSONL

This repo has no database server or ORM, but Python includes `sqlite3`.
Phase 3 needs atomic insert-or-ignore/upsert, leases, attempt counters, retry
selection, dead-letter state, and watermarks. Those are awkward and fragile in
append-only JSONL, especially when a worker crashes mid-batch.

Recommended local state layout:

```text
CODEXBOT_DIR/search/
├── generation.json
├── worker_status.json
├── generations/<generation_id>/
│   ├── documents.jsonl
│   └── manifest.json
└── queue.sqlite
```

Implementation implication:
- Add a dependency-free `codexbot.search.queue` module using stdlib `sqlite3`.
- Set `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=...`, and
  `PRAGMA foreign_keys=ON` during connection setup.
- Keep queue state under `search_dir()`, never `state.json` or
  `monitor_state.json`.
- Treat invalid/missing queue DB as degraded search state, not as an HTTP
  transport failure.

### 2. Split Queue Lifecycle Identity from Search Row Identity

Existing `SearchRowIdentity.from_provenance()` is already the correct document
identity. Queue processing still needs a separate row key for lease/retry
lifecycle. A good queue-row shape stores both:

- `queue_id`: deterministic lifecycle id, such as a hash of runtime,
  transcript source, transcript offset/index, role/content type, tool id, and
  chunk index.
- `identity_json`: serialized `SearchRowIdentity` for idempotent document
  upsert.
- `document_json`: serialized `SearchBackfillDocument` or compatible live
  document payload.
- `status`: `queued`, `leased`, `done`, or `failed`.
- `attempts`, `lease_owner`, `lease_expires_at`, `available_at`, `last_error`,
  `created_at`, `updated_at`.

Implementation implication:
- Queue insertion should use `INSERT OR IGNORE` or an equivalent upsert keyed by
  deterministic `queue_id`.
- Document convergence should upsert by `SearchRowIdentity`, not queue id.
- Retries should mutate queue lifecycle state only; they must not append
  duplicate documents.

### 3. Reuse Backfill Document Construction

Phase 2's `backfill.py` already converts parsed entries into
`SearchBackfillDocument` values with deterministic chunking and provenance.
Those helpers are currently private (`_chunk_text`, `_documents_for_entry`,
`_documents_for_source`), but Phase 3 needs exactly the same behavior.

Implementation implication:
- Extract or expose a small helper such as `documents_for_parsed_entry(...)`
  that accepts `ParsedTranscriptSession`/routing/provenance and produces the
  same chunk documents as backfill.
- Keep a single chunking implementation so live and rebuild produce identical
  `chunk_index` identities.
- Do not build a second parser or worker tailer that duplicates
  `TranscriptParser.parse_entries()`.

### 4. Producer Should Be Nonblocking but Recoverable

`SessionMonitor._monitor_loop()` awaits extra listeners before Telegram
delivery. A slow listener can therefore delay downstream message callbacks.
The queue producer should return quickly and record/degrade status on failure.
Durability is recovered by search-owned transcript watermarks and replay, not
by making the monitor block on heavy indexing.

Implementation implication:
- Add a search live-queue service with a listener method that schedules queue
  insertion through a lightweight background task or executor and catches
  errors.
- Persist queue insert failures as search status/recent error and rely on
  worker replay from transcript watermarks for eventual convergence.
- Start/stop the producer listener from the existing web server lifecycle,
  similar to how `EventBus` is attached to `SessionMonitor`.

### 5. Watermarks Must Be Search-Owned

`monitor_state.json` tracks delivery offsets and deliberately bootstraps to EOF
on restart to avoid replaying old bot messages. Search cannot reuse that state:
it needs to replay from the last safe searchable coordinate when queue state is
uncertain.

Implementation implication:
- Store watermarks in `queue.sqlite` keyed by runtime, session id when known,
  transcript source, and generation id or active writable generation.
- Watermarks should track last queued/completed transcript offset and parser
  index where available.
- Restart recovery should scan current open-session transcripts from the last
  safe watermark and enqueue missing parsed entries idempotently.
- If the watermark is invalid, reset to a conservative earlier coordinate
  rather than skipping to EOF.

### 6. Live Drain Loop Should Stay Worker-Owned

The existing worker CLI supports `initial-backfill` and `rebuild`. Phase 3 needs
ongoing queue draining. It can stay dependency-light in this phase because there
are no embeddings yet; later Phase 4 can replace the document write target with
real retrieval/index writes.

Implementation implication:
- Extend `codexbot-search-worker` with a `live-loop` command or equivalent
  worker function.
- The supervisor should start or schedule live queue draining without waiting
  for it during backend startup.
- The drain loop should flush when at least 32 queue rows are ready or 60
  seconds have elapsed since the previous flush.
- On shutdown/cancel, the worker should release or expire leases by timestamp
  rather than requiring explicit cleanup.

### 7. JSONL Documents Need Idempotent Upsert Semantics Until Retrieval Exists

Phase 2 writes `generations/<id>/documents.jsonl`. Since Phase 4 retrieval is
not present yet, Phase 3 can implement safe derived-document convergence by
rewriting that JSONL atomically from a dictionary keyed by serialized
`SearchRowIdentity`.

Implementation implication:
- Add a helper such as `upsert_generation_documents(generation_id, documents)`
  that reads existing JSONL rows, replaces rows by stable identity, writes a
  temporary file, fsyncs, and renames.
- Keep this helper scoped to Phase 3's derived artifact. Do not introduce
  LanceDB/Faiss in this phase.
- Update manifest counters after successful upsert batches so status reflects
  queued/failed/indexed counts.

### 8. Stale Sessions Should Be a Routing Filter First

Closed sessions should not be returned as normal routeable v1 results.
Retrieval is not implemented yet, but Phase 3 can add stale metadata and helper
functions now so future search reads have a clear filter.

Implementation implication:
- Add stale document metadata or a separate `stale_sources` table keyed by
  transcript source/session id.
- Build helper(s) that compare indexed document routing/session metadata with
  current `tmux_manager.list_windows()` and `SessionManager` state.
- Status can report stale counts or degraded/stale state where useful, but the
  normal API should still be typed and safe.

## Suggested Plan Shape

1. **Slice 1: durable queue and status state**
   - Add queue contracts and SQLite state helpers.
   - Lock leasing/retry/dead-letter/watermark behavior in tests.
   - Extend status counters/reason for queue lag and failures.

2. **Slice 2: live producer and transcript replay**
   - Reuse backfill document builders for live parsed entries.
   - Attach a nonblocking producer to `SessionMonitor`.
   - Add worker-owned replay from search watermarks for recovery.

3. **Slice 3: worker drain, idempotent upsert, and stale-session filtering**
   - Add live drain loop with 32-item/60-second flush rules.
   - Upsert live docs into the current generation atomically.
   - Add stale-source marking/filter helpers and status tests.

These can be three MVP-style backend slices in waves 1, 2, and 3. Each slice
creates an observable capability without adding Web UI search UX.

## Validation Architecture

Phase 3 should use the existing Python test stack. No frontend build is required
unless implementation unexpectedly touches `web-ui/`.

Recommended targeted verification:

- `uv run pytest tests/codexbot/test_search_live_queue.py tests/codexbot/test_search_state.py tests/codexbot/test_search_worker.py -q`
- `uv run pytest tests/codexbot/test_search_backfill.py tests/codexbot/test_session_monitor.py tests/codexbot/test_web_server.py -q`
- `uv run pytest tests/codexbot/test_web_api.py tests/codexbot/test_search_contracts.py -q`

Full repo verification remains:

- `uv run ruff check src/ tests/`
- `uv run ruff format --check src/ tests/`
- `uv run pyright src/codexbot/`
- `/tmp/codexbot-venv/bin/pytest -q`

Required test coverage:

- Queue DB and watermarks live under `CODEXBOT_DIR/search` and never mutate
  `monitor_state.json`.
- Inserting the same transcript-derived item twice creates one queue row and
  one search document identity.
- Leasing selects ready rows, marks lease owner/expiry, retries expired leases,
  increments attempts, and moves exhausted rows to failed/dead-letter state.
- Queue lag, failed item counts, and recent errors degrade search status without
  breaking `/api/search/status` or `/api/search`.
- Monitor listener returns without blocking delivery when queue persistence
  fails; the failure is visible through search status.
- Replay from transcript watermarks enqueues missed parsed entries after
  restart and does not skip ahead.
- Live batches flush at 32 ready rows or after the 60-second timer.
- Live document upsert rewrites/replaces by `SearchRowIdentity` and does not
  append duplicates.
- Closed tmux sessions are marked stale/hidden for normal v1 result routing.

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Monitor listener slows message delivery | Keep listener nonblocking; record failure/lag and rely on watermark replay. |
| Queue state diverges from transcript source | Store transcript watermarks under search state and replay from safe coordinates on restart. |
| Duplicate live/backfill documents | Use deterministic queue ids and idempotent document upserts by `SearchRowIdentity`. |
| JSONL upsert becomes expensive | Accept atomic rewrite for v1 active-session scope; Phase 4 can replace target with LanceDB writes. |
| Dead-letter rows hide permanent bugs | Surface failed count/recent error in status and keep rows inspectable/requeueable. |
| Stale documents route to dead tmux windows | Compare result routing against current tmux/session state and hide stale sources by default. |
| Heavy retrieval dependencies enter hot paths | Keep Phase 3 dependency-free beyond stdlib `sqlite3` and existing modules. |

## Planning Inputs to Preserve

- Phase requirements: `CORP-05`, `INDX-04`, `INDX-05`, `INDX-06`, `INDX-07`.
- Phase 1 decisions: row identity comes from transcript provenance/chunk index;
  window id is mutable routing metadata; request handlers stay import-light;
  search state is under `CODEXBOT_DIR/search`.
- Phase 2 decisions: backfill uses parser-level entries, current open sessions,
  deterministic chunking, inactive/active generation manifests, and
  built-but-unavailable status before retrieval.
- Phase 3 context decisions D-01 through D-17.

## RESEARCH COMPLETE

Research is sufficient to plan Phase 3.
