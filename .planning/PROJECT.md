# Codi Session Search

## What This Is

Codi is a self-hosted bridge between Codex / Claude Code sessions running in
tmux and two front-ends: a browser Web UI and a Telegram bot. This project adds
fast local session search to the Web UI so users can find the right active
session and relevant message snippets across open Codex and Claude sessions.

The search index is derived from the same transcript/session stream Codi already
uses for history and live updates. It must stay rebuildable, local-first, and
safe to run on a Mac mini without blocking normal Codi usage.

## Core Value

Users can quickly locate active sessions by meaning and exact terms, even when
many windows contain long histories. New messages should become searchable
soon after turns complete, while the Web UI remains responsive during startup,
backfill, and ongoing indexing.

## Requirements

### Validated Existing Capabilities

- [x] Codi bridges Codex and Claude Code tmux sessions to the Web UI and
  Telegram bot.
- [x] One session maps to one tmux window, with routing keyed by tmux window ID.
- [x] The Web UI renders session lists, chat history, live WebSocket updates,
  terminal attach/shell views, slash hints, skill hints, and plan/input choices.
- [x] The backend exposes authenticated FastAPI endpoints and a WebSocket event
  bus shared by web and Telegram delivery paths.
- [x] `SessionMonitor` and runtime transcript parsers detect Codex/Claude
  activity from local transcript JSONL files.
- [x] Session and monitor state are persisted under the Codi state directory and
  can be rebuilt from runtime/session sources.
- [x] Validated in Phase 1: Codi exposes authenticated backend search/status
  surfaces with stable provenance, typed missing/unavailable readiness semantics,
  search-owned derived state under `CODEXBOT_DIR/search`, and no embedding/index
  imports on FastAPI request paths.
- [x] Validated in Phase 2: Codi starts a nonblocking local search worker path,
  backfills currently open Codex/Claude sessions through parser-level transcript
  entries, writes inactive search generation artifacts under
  `CODEXBOT_DIR/search`, and atomically activates completed generations while
  still reporting search as built but unavailable until retrieval exists.

### New Requirements

- [ ] Add Web UI session search with ranked sessions and matching snippets.
- [ ] Index all currently open sessions on first startup when no search DB
  exists.
- [ ] Build the initial index asynchronously so users can keep working while
  backfill runs.
- [ ] Queue new user, assistant, and useful tool/output text from both Codex and
  Claude sessions for indexing.
- [ ] Keep the derived index aligned with transcript state after initial backfill
  and ongoing queue drains.
- [ ] Support hybrid retrieval combining lexical search and semantic vector
  search.
- [ ] Use a local embedding runtime suitable for a Mac mini, starting with
  Qwen3-Embedding-0.6B unless implementation validation identifies a better
  small code/search embedding model.
- [ ] Run indexing in a separate local service or worker process so embedding
  work cannot stall the main Codi API/event loop.
- [ ] Batch live indexing instead of indexing every message synchronously:
  flush when 32 queued items accumulate or when 60 seconds pass, whichever
  happens first.
- [ ] Expose index/backfill status enough for the Web UI to avoid confusing
  users during initial indexing.

### Out Of Scope For V1

- [ ] Searching closed or archived sessions beyond the currently open tmux
  sessions.
- [ ] Cloud embedding APIs or remote search services.
- [ ] Replacing transcript JSONL files as the source of truth for history.
- [ ] Synchronous per-message embedding/index writes on the hot message path.
- [ ] Multi-user hosted search semantics beyond the existing local Codi
  deployment model.

## Context

The user requested search for the Web UI that indexes all open sessions and new
messages from both sides. Search should be hybrid, with BM25/lexical matching
plus semantic retrieval. Initial startup must tolerate a missing index database:
Codi should create it in the background, continue serving the UI, and enqueue
new messages while backfill is still running so the index converges.

Interactive choices made during project initialization:

- Result shape: sessions plus matching hits/snippets.
- Runtime shape: separate local service/worker, not hot-path indexing inside
  request handling.
- Corpus: all useful text from user, assistant, and relevant tool/output
  material.
- Search scope: open sessions for v1.
- Index backend: LanceDB hybrid search first, with alternatives only if it fails
  practical validation.
- Live batching: 32 queued elements or 60 seconds.

## Constraints

- Preserve the existing invariant that session routing is keyed by tmux window
  IDs, not names.
- Treat transcript/session state as authoritative; the search index is derived
  and rebuildable.
- Do not block FastAPI startup, WebSocket delivery, Telegram delivery, or
  session-monitor polling on embedding or indexing work.
- Keep CPU and memory use appropriate for local Mac mini deployment.
- Message truncation remains a Telegram send-layer concern; search ingestion
  should use the richer local transcript text where available.
- The Web UI should continue working while initial indexing status is incomplete.

## Key Decisions

| Decision | Choice | Rationale |
| --- | --- | --- |
| V1 scope | Open sessions only | Matches the immediate Web UI switching workflow and keeps initial index bounded. |
| Runtime isolation | Separate local service/worker | Protects Codi's API/event loop from embedding latency and model memory use. |
| Retrieval | Hybrid lexical + semantic | Exact command/error matching and meaning-based lookup are both important for session search. |
| Index backend | LanceDB hybrid first | Provides a local vector store with full-text/hybrid capabilities and simple persisted storage. |
| Embedding model | Qwen3-Embedding-0.6B candidate | Small enough for local use while likely strong for code and multilingual technical text. |
| Live batching | 32 items or 60 seconds | Keeps new turns fresh without embedding every message synchronously. |
| Phase 1 status contract | Missing/not-ready search is a typed 200 response, while active metadata without a query backend reports `unavailable` | Prevents the Web UI from treating a stubbed search backend as ready or confusing no matches with not-ready search. |
| Phase 1 identity contract | Indexed row identity comes from transcript provenance plus chunk index; tmux window fields remain mutable routing metadata | Keeps search rows stable across renames, cwd changes, pinning, and tmux window movement. |
| Phase 2 activation contract | Search generations are built inactive and only activated through an atomic metadata write after complete manifest and document artifacts exist | Prevents interrupted rebuilds from becoming active and keeps startup/rebuild rerunnable. |
| Phase 2 readiness contract | Completed backfill exposes generation metadata and counters but remains `available=false` until query retrieval is implemented | Keeps the Web UI from treating prepared corpus artifacts as a searchable index. |

## Evolution

Future milestones may extend search to closed/resumable sessions, expose richer
index diagnostics, support model/backend configuration from the Web UI, or add a
maintenance flow for rebuilding and compacting search indexes.

---

Last updated: 2026-05-21 after Phase 2 completion.
