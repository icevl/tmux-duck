# Phase 2 Research: Worker Skeleton, Backfill, and Rebuild Path

**Phase:** 02-worker-skeleton-backfill-and-rebuild-path
**Researched:** 2026-05-21
**Confidence:** HIGH for local architecture and tests; MEDIUM for exact worker
supervision filenames until implementation chooses the smallest clean API.

## Research Question

What needs to be known to plan Phase 2 well?

Phase 2 must prove that search-owned storage can be created and rebuilt
asynchronously from currently open Codex and Claude sessions while Codi's
existing Web UI, Telegram, terminal, WebSocket delivery, and monitor loops keep
working. It should establish the process/state/backfill boundary before
embedding models, LanceDB retrieval, live queue convergence, or Web UI search
UX are implemented.

## Key Findings

### 1. Use the Existing Web Lifecycle, but Keep the Worker Separate

The current web lifecycle starts background asyncio tasks in
`src/codexbot/web/server.py`: `server.serve()`, `stream_pane_loop()`, and
optional `update_poll_loop()`. Shutdown explicitly cancels and awaits tasks with
timeouts. This is the right attachment point for a small supervisor that starts
the search worker without blocking backend startup.

The worker should still have its own local CLI/process boundary. The backend
can launch or signal it, but model/index work in later phases must not import
into `src/codexbot/web/api.py` or request handlers. Phase 2 can keep the worker
implementation dependency-light and use the boundary to run backfill and write
state.

Implementation implication:
- Add a search worker entrypoint under the package, and expose it through
  `pyproject.toml [project.scripts]`, for example `codexbot-search-worker`.
- Add a small supervisor/client module under `src/codexbot/search/` that the
  web/server lifecycle can call.
- Keep request-path modules importing only `codexbot.search.client`,
  `contracts`, and lightweight state readers.

### 2. Backfill Should Enumerate Open Windows, then Resolve Transcripts

The v1 search corpus is currently open tmux-backed sessions only. Existing
session code already has the important pieces:

- `tmux_manager.list_windows()` returns open tmux windows and skips the main
  placeholder window.
- `SessionManager.resolve_session_for_window(window_id)` resolves current
  `WindowState` to a transcript-backed `CodexSession`.
- `SessionManager._refresh_sessions_index()` discovers Codex transcripts under
  `config.codex_sessions_path` and adds Claude transcript paths for currently
  bound Claude windows without scanning all Claude projects.
- `claude_transcript_path(session_id, cwd)` derives the Claude JSONL path from
  the known Claude session and cwd.

Implementation implication:
- Plan a public or search-owned helper that returns an open-session backfill
  source: current routing metadata, runtime, session id, transcript file, and
  parsed entries.
- Do not glob all `~/.codex/sessions` or `~/.claude/projects` as the v1 corpus;
  use the open-window/session resolution path.

### 3. Backfill Needs a Parser-Level Source, Not Web History DTOs

`SessionManager.get_history_snapshot()` is optimized for the Web UI. It returns
browser-ready message dictionaries and uses an in-memory history cache. That is
valuable for the UI, but search ingestion should not couple to that payload
shape.

The better source is the transcript parser layer:

- `SessionManager._read_transcript_entries()` reads JSONL entries and stamps
  `TranscriptParser.TRANSCRIPT_OFFSET_KEY`.
- `TranscriptParser.parse_entries()` returns `ParsedEntry` values with role,
  text, content type, tool identifiers, timestamp, transcript offset, and
  transcript index.
- `ParsedEntry` already normalizes Codex and Claude records and is shared by
  history and monitor paths.

Implementation implication:
- Add a backfill source helper that yields `ParsedEntry` plus
  `TranscriptProvenance`.
- Build one or more lightweight chunk documents per parsed text-bearing entry.
- Preserve `SearchRowIdentity.from_provenance(..., chunk_index=N)` semantics.

### 4. Generation State Should Be Atomic and Search-Owned

Phase 1 reserved `codexbot_dir() / "search"` and added an active generation
reader. Phase 2 should extend this namespace only. Existing state patterns use
`atomic_write_json()` from `src/codexbot/utils.py`, which writes temp+fsync and
renames within the same directory.

Implementation implication:
- Keep a root layout under `CODEXBOT_DIR/search`, for example:
  - `generation.json` for active generation metadata compatible with Phase 1.
  - `worker_status.json` for heartbeat/current task/recent error.
  - `generations/<generation_id>/manifest.json` for backfill counters and
    completion state.
  - `generations/<generation_id>/documents.jsonl` or an equivalent temporary
    stub artifact until LanceDB rows exist in Phase 4.
- Build new generations inactive, then atomically write active metadata after
  successful backfill.
- Treat incomplete generations as inactive; rerun idempotent backfill on next
  startup or explicit rebuild.
- Do not write search watermarks, worker state, or backfill status to
  `monitor_state.json` or `state.json`.

### 5. Status Should Reflect Building and Built-But-Unqueryable States

`src/codexbot/search/client.py` currently returns:

- `missing` when no active generation metadata exists.
- `unavailable` when active generation metadata exists but no query backend is
  implemented.

Phase 2 should add state-aware reads for worker/backfill metadata:

- During initial backfill: `state="building"`, `available=false`, counters
  populated from the backfill manifest/status.
- After successful backfill but before retrieval exists: `state="unavailable"`,
  `available=false`, active generation and counters present.
- On worker/backfill error: status reason should summarize the failure without
  exposing raw transcript content, secret values, or local exception stacks.

Implementation implication:
- Extend `SearchCounters` or status construction enough to report
  `open_sessions`, `indexed_sessions`, `indexed_chunks`, and `failed_items`.
- Leave live queue lag/leases/retries to Phase 3.
- Keep `/api/search` returning typed `not_ready` empty results until retrieval
  exists.

### 6. This Phase Is Backend/Worker, Not Web UI Search UX

The roadmap success criteria mention Web UI because existing frontends must keep
working while backfill runs. The Phase 2 context explicitly excludes browser
search experience, result rendering, Web UI search controls, and hit navigation.
The plan should therefore not modify `web-ui/src/*` or require a UI design
contract. It should verify the backend status surface and startup behavior that
future UI work will consume.

## Suggested Plan Shape

Because Phase 2 is MVP mode, plans should still deliver observable slices
instead of pure horizontal layers:

1. **Slice 1: worker lifecycle and status skeleton**
   - Add dependency-light search worker state/status models and a worker CLI
     that can mark heartbeat/building/failure states.
   - Start or schedule the worker from backend lifecycle without waiting for
     backfill.
   - `/api/search/status` can show building/unavailable state.

2. **Slice 2: open-session backfill corpus**
   - Add parser-backed backfill source over open tmux windows.
   - Convert parsed text-bearing entries into chunk documents with provenance.
   - Cover Codex and Claude transcript resolution paths with fixtures.

3. **Slice 3: generation rebuild and recovery**
   - Build inactive generation manifests/documents, activate only on success.
   - Add explicit local rebuild command.
   - Treat interrupted generations as inactive and rerunnable.

These can be three PLAN.md files in waves 1, 2, and 3. The first plan creates
the status/lifecycle surface; the second makes backfill real; the third locks
rebuild semantics and recovery.

## Validation Architecture

Phase 2 should use the existing Python test stack. No browser build is required
unless implementation unexpectedly touches `web-ui/`.

Recommended automated verification:

- `uv run pytest tests/codexbot/test_search_state.py tests/codexbot/test_web_api.py tests/codexbot/test_web_server.py -q`
- `uv run pytest tests/codexbot/test_search_backfill.py tests/codexbot/test_search_worker.py -q`
- `uv run pytest tests/codexbot/test_search_contracts.py tests/codexbot/test_transcript_parser.py tests/codexbot/test_session.py -q`
- `uv run ruff check src/ tests/`
- `uv run ruff format --check src/ tests/`
- `uv run pyright src/codexbot/`
- `/tmp/codexbot-venv/bin/pytest -q`

Required test coverage:

- Missing generation triggers nonblocking worker startup/backfill scheduling.
- Worker/backfill status lives under `CODEXBOT_DIR/search` and never mutates
  `monitor_state.json`.
- `/api/search/status` reports `building` while a backfill manifest is active.
- Completed backfill reports active generation metadata but still
  `available=false`/`unavailable` before retrieval exists.
- Open-session backfill enumerates current tmux windows and skips closed or
  unresolved sessions.
- Backfill uses `TranscriptParser.parse_entries()` and includes user,
  assistant, tool use/result, local command, thinking, and other text-bearing
  entries.
- Long text entries produce multiple chunk documents with stable
  `chunk_index`.
- Interrupted/incomplete generations are not active and can be rebuilt.

## Risks And Mitigations

| Risk | Mitigation |
|------|------------|
| Worker startup blocks existing web/bot startup | Supervisor must schedule/launch and return quickly; tests should assert backend start does not await full backfill. |
| Search starts scanning all historical transcripts | Backfill source must start from current tmux/window state and resolved session transcripts only. |
| Backfill duplicates future live-queue responsibilities | Keep live queue leases/retries/watermarks out of this phase; use generation manifest counters only. |
| Active generation becomes half-written | Build inactive generation data and activate with atomic `generation.json` write only after success. |
| Status leaks local paths or transcript text | Status reason should be sanitized; tests should assert no raw transcript body, secrets, or stack traces. |
| Heavy search dependencies enter request path | Preserve AST import-boundary tests and add worker modules to disallowed imports from `web/api.py`. |

## Planning Inputs To Preserve

- Phase requirements: `CORP-01`, `CORP-02`, `INDX-01`, `INDX-02`,
  `INDX-03`, `INDX-08`.
- Phase 1 decisions: row identity comes from transcript provenance/chunk index;
  `window_id` is mutable routing metadata; request handlers stay import-light;
  search state is under `CODEXBOT_DIR/search`.
- Phase 2 discussion decisions D-01 through D-16 from
  `02-CONTEXT.md`.

## RESEARCH COMPLETE

Research is sufficient to plan Phase 2.
