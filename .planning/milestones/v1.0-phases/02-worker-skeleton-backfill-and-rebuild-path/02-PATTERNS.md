# Phase 02: Worker Skeleton, Backfill, and Rebuild Path - Pattern Map

**Mapped:** 2026-05-21
**Files analyzed:** 11
**Analogs found:** 11 / 11

## Scope Guard

Phase 2 is backend worker and backfill infrastructure only. The executor must
not add LanceDB, embeddings, semantic retrieval, lexical ranking, live durable
queue convergence, browser search controls, Web UI result rendering, or
Telegram search commands.

The worker process boundary should exist now, but request-path modules must keep
using only lightweight search contracts/state/client code. Runtime progress,
worker status, manifests, generation metadata, counters, and stub document
artifacts belong under `CODEXBOT_DIR/search`.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/codexbot/search/contracts.py` | model | transform, request-response | `src/codexbot/web/api.py` | role-match |
| `src/codexbot/search/state.py` | utility | file-I/O, config | `src/codexbot/utils.py` | exact |
| `src/codexbot/search/client.py` | service | request-response | `src/codexbot/web/update_checker.py` | role-match |
| `src/codexbot/search/worker.py` | service | file-I/O, subprocess, transform | `src/codexbot/web/update_checker.py` | role-match |
| `src/codexbot/search/supervisor.py` | lifecycle | subprocess, nonblocking startup | `src/codexbot/web/server.py` | role-match |
| `src/codexbot/search/backfill.py` | service | transcript-to-documents | `src/codexbot/session.py` | role-match |
| `src/codexbot/session.py` | domain helper | tmux-window to transcript parser | `src/codexbot/session.py` | exact |
| `src/codexbot/web/server.py` | lifecycle | background service startup/shutdown | `src/codexbot/web/server.py` | exact |
| `pyproject.toml` | config | CLI entrypoint | existing `[project.scripts] codexbot` | exact |
| `tests/codexbot/test_search_worker.py` | test | lifecycle, state, CLI | `tests/codexbot/test_web_server.py` | role-match |
| `tests/codexbot/test_search_backfill.py` | test | transcript parsing, chunking | `tests/codexbot/test_transcript_parser.py` | role-match |

## Pattern Assignments

### Search-Owned State Helpers

**Analog:** `src/codexbot/utils.py`

Use `codexbot_dir()` for the root and `atomic_write_json()` for JSON state
updates. Keep the Phase 1 pattern where missing, invalid, inactive, or stale
generation metadata is treated as absent rather than raising on request paths.

Apply to Phase 2:
- Extend `src/codexbot/search/state.py` with paths like `worker_status.json`,
  `generations/<generation_id>/manifest.json`, and a temporary
  `documents.jsonl` artifact.
- Keep all writes under `search_dir()`.
- Never write search progress into `state.json` or `monitor_state.json`.

### Worker Lifecycle

**Analog:** `src/codexbot/web/server.py`

The existing web lifecycle starts background tasks with `asyncio.create_task()`
and cancels/awaits them during shutdown. The search supervisor should follow the
same nonblocking lifecycle shape, but the worker itself must run behind a local
CLI/process boundary so later model/index dependencies stay outside the main
FastAPI/WebSocket/Telegram process.

Apply to Phase 2:
- Add a small `src/codexbot/search/supervisor.py` that can be called from
  `start_web_server()` and returns quickly.
- Add a worker entrypoint in `src/codexbot/search/worker.py` and expose it from
  `pyproject.toml`.
- Do not import worker modules from `src/codexbot/web/api.py`.

### Status Surface

**Analog:** `src/codexbot/search/client.py`

Phase 1 already returns typed missing/unavailable responses without transport
errors. Extend that provider to read worker/backfill state and generation
manifest counters, but keep it dependency-light and safe for request paths.

Apply to Phase 2:
- While worker backfill is active, `/api/search/status` should become
  `state="building"`, `available=false`, with open/indexed/chunk/failure
  counters when available.
- After backfill succeeds and an active generation exists, status should remain
  `state="unavailable"` and `available=false` until retrieval is implemented.
- Worker errors should be sanitized into status reason/counters; raw transcript
  text, secrets, local stack traces, and full transcript bodies must not appear.

### Open-Session Backfill Source

**Analog:** `src/codexbot/session.py`

The existing session layer already resolves current tmux windows to runtime
session ids and transcript paths. Backfill should add a reusable backend helper
around this parser-level source instead of consuming Web UI `HistorySnapshot`
payloads.

Apply to Phase 2:
- Enumerate current windows with `tmux_manager.list_windows()`.
- Resolve each window with `SessionManager.resolve_session_for_window()`.
- Parse transcript entries through `TranscriptParser.parse_entries()`.
- Emit only parsed text-bearing entries. Include user, assistant, thinking,
  tool use/result, local command, and any other parser-emitted textual entries.
- Preserve transcript offset/index and chunk index through
  `SearchRowIdentity.from_provenance(..., chunk_index=N)`.

### Tests

**Analogs:** `tests/codexbot/test_search_state.py`,
`tests/codexbot/test_web_api.py`, `tests/codexbot/test_transcript_parser.py`,
and `tests/codexbot/test_web_server.py`

Tests should use `tmp_path`, `monkeypatch`, and fake managers instead of live
tmux or real transcript directories. Keep targeted tests fast enough for the
Nyquist validation lane:

```bash
uv run pytest tests/codexbot/test_search_worker.py tests/codexbot/test_search_backfill.py tests/codexbot/test_search_state.py tests/codexbot/test_web_api.py -q
```

## Pattern Map Complete

This map is sufficient for Phase 2 planning and execution.
