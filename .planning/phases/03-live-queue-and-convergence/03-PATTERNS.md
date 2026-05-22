# Phase 03: Live Queue and Convergence - Pattern Map

**Mapped:** 2026-05-22
**Files analyzed:** 12
**Analogs found:** 12 / 12

## Scope Guard

Phase 3 is backend search-queue and convergence infrastructure only. The
executor must not add LanceDB, Faiss, embeddings, semantic/lexical retrieval,
browser search controls, result rendering, Telegram search commands, or
historical closed-session search.

Queue state, leases, retries, watermarks, stale-source state, and live drain
metadata belong under `CODEXBOT_DIR/search`. They must not write to
`state.json` or `monitor_state.json`.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/codexbot/search/contracts.py` | model | queue/status/document DTOs | existing search DTOs in same file | exact |
| `src/codexbot/search/state.py` | utility | file paths, atomic state | existing generation/status helpers | exact |
| `src/codexbot/search/queue.py` | storage service | SQLite queue, leases, watermarks | `src/codexbot/search/state.py` + `src/codexbot/utils.py` | role-match |
| `src/codexbot/search/backfill.py` | document builder | parsed entry to chunk docs | existing Phase 2 backfill helpers | exact |
| `src/codexbot/search/worker.py` | worker service | queue drain, document upsert | existing worker CLI commands | exact |
| `src/codexbot/search/supervisor.py` | lifecycle | nonblocking startup | existing search supervisor and web server task pattern | exact |
| `src/codexbot/search/client.py` | status provider | request-safe status | existing missing/building/unavailable provider | exact |
| `src/codexbot/session_monitor.py` | event producer | parsed transcript events | existing extra listener fan-out | exact |
| `src/codexbot/web/server.py` | lifecycle | listener/worker start-stop | existing EventBus and search supervisor wiring | exact |
| `src/codexbot/session.py` | source resolver | open windows to transcripts | Phase 2 parsed transcript helper | exact |
| `tests/codexbot/test_search_live_queue.py` | test | queue/replay/drain behavior | `tests/codexbot/test_search_backfill.py` and `test_search_worker.py` | role-match |
| `tests/codexbot/test_web_api.py` | test | status API contract | existing search status tests | exact |

## Pattern Assignments

### Search-Owned Durable Queue

**Analogs:** `src/codexbot/search/state.py`, `src/codexbot/utils.py`

Use `search_dir()` for all paths and keep queue durability under
`CODEXBOT_DIR/search`. JSON state helpers already use temp+fsync+rename; queue
state should use stdlib `sqlite3` to avoid ad hoc JSONL lease/retry mutation.

Apply to Phase 3:
- Add `queue.sqlite` path helper in `state.py`.
- Add `src/codexbot/search/queue.py` for schema initialization, enqueue,
  lease acquisition, completion/failure, retry/dead-letter, and watermark
  reads/writes.
- Configure SQLite with WAL and busy timeout on each connection.
- Do not add a database server, ORM, or non-stdlib dependency.

### Parser-Backed Document Construction

**Analog:** `src/codexbot/search/backfill.py`

Backfill already owns deterministic chunking and `SearchBackfillDocument`
construction. Live indexing must reuse this behavior rather than duplicating
parser/chunker logic.

Apply to Phase 3:
- Extract reusable helpers from private backfill functions where needed.
- Live queue rows should carry serialized `SearchBackfillDocument` values or a
  compatible shape.
- `SearchRowIdentity.from_provenance(..., chunk_index=N)` remains the single
  document identity source.

### Nonblocking Monitor Producer

**Analog:** `src/codexbot/session_monitor.py` extra listeners and
`src/codexbot/web/server.py` listener registration.

Extra listeners are awaited before the primary Telegram callback, so producer
work must be brief and failure-tolerant. Durable catch-up belongs to
watermark-based replay, not to blocking message delivery.

Apply to Phase 3:
- Attach a search live-queue listener from `start_web_server()` when a
  `SessionMonitor` exists.
- Listener should schedule queue persistence work and return quickly.
- Shutdown should remove the listener and cancel/await any owned background
  producer/drain tasks using the existing web server timeout style.

### Worker Drain and Status

**Analogs:** `src/codexbot/search/worker.py`,
`src/codexbot/search/supervisor.py`, `src/codexbot/search/client.py`

The worker already has a CLI/process boundary and status file. Extend that
boundary to drain queue batches and update status without importing retrieval
or embedding dependencies into request paths.

Apply to Phase 3:
- Add a `live-loop` worker command or equivalent function that drains ready
  queue rows.
- Flush when 32 rows are ready or 60 seconds have elapsed.
- Update `SearchCounters.queued_items` and `failed_items`, and expose recent
  queue errors as `degraded`/`unavailable` status depending on active
  generation state.

### Tests

**Analogs:** `tests/codexbot/test_search_backfill.py`,
`tests/codexbot/test_search_worker.py`, `tests/codexbot/test_search_state.py`,
`tests/codexbot/test_web_api.py`, `tests/codexbot/test_web_server.py`

Use `tmp_path`, `monkeypatch`, fake tmux/session managers, and direct queue
state calls. Do not use live tmux, real transcript roots, Telegram, Uvicorn, or
browser UI.

Recommended targeted lane:

```bash
uv run pytest tests/codexbot/test_search_live_queue.py tests/codexbot/test_search_state.py tests/codexbot/test_search_worker.py tests/codexbot/test_search_backfill.py tests/codexbot/test_session_monitor.py tests/codexbot/test_web_server.py tests/codexbot/test_web_api.py -q
```

## Pattern Map Complete

This map is sufficient for Phase 3 planning and execution.
