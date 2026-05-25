# Codi Session Search

## What This Is

Codi is a self-hosted bridge between Codex / Claude Code sessions running in
tmux and two front-ends: a browser Web UI and a Telegram bot. The v1.0 Session
Search milestone added fast local Web UI search across currently open Codex and
Claude sessions, including exact and meaning-based lookup, grouped session
results, snippet navigation, and operational visibility.

The search index is derived from the same transcript/session stream Codi already
uses for history and live updates. It stays rebuildable, local-first, and safe to
run without blocking normal Codi usage.

## Core Value

Users can quickly locate active sessions by meaning and exact terms, even when
many windows contain long histories. New messages become searchable soon after
turns complete, while the Web UI remains responsive during startup, backfill,
and ongoing indexing.

## Milestone Status

- **v1.0 Session Search:** shipped 2026-05-25.
- **Audit:** passed, with 41/41 v1 requirements satisfied and 6/6 phases
  verified.
- **Archive:** `.planning/milestones/v1.0-ROADMAP.md`,
  `.planning/milestones/v1.0-REQUIREMENTS.md`,
  `.planning/milestones/v1.0-MILESTONE-AUDIT.md`, and
  `.planning/milestones/v1.0-phases/`.
- **Current focus:** planning the next milestone.

## Validated Capabilities

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
- [x] Search uses authenticated backend search/status surfaces with stable
  provenance, typed readiness semantics, search-owned derived state under
  `CODEXBOT_DIR/search`, and no embedding/index imports on FastAPI request
  paths.
- [x] Codi starts a nonblocking local search worker path, backfills currently
  open Codex/Claude sessions through parser-level transcript entries, and
  atomically activates completed search generations.
- [x] New transcript activity is durably queued with idempotent row identity,
  leases, retries, watermarks, and restart recovery outside `monitor_state.json`.
- [x] Session search supports lexical, semantic, metadata, and hybrid result
  labels with ranked session groups and bounded snippets.
- [x] Search results open the owning tmux session by current `window_id`, fetch a
  bounded transcript window, and focus the matching message when coordinates can
  be loaded.
- [x] The Web UI shows compact search status, filters, grouped results, hit
  navigation, and accessible operational status details.
- [x] Worker failures, stale sessions, failed queue rows, semantic failures, and
  unavailable embedding paths degrade search without blocking chat, Telegram,
  terminal, WebSocket delivery, or session list updates.
- [x] Codi includes an opt-in local benchmark and documented fallback behavior
  for validating Qwen3-Embedding-0.6B or running lexical-only degraded search.

## Deferred Scope

Future milestones may extend search to:

- Closed or resumable historical Codex and Claude sessions.
- Advanced boolean, regex, and query-qualifier syntax.
- Current-session-only transcript find.
- Larger hit expansion within a session result.
- Commands, skills, GSD choices, and settings as separate non-transcript result
  sections.
- Admin controls for rebuilding, compacting, tuning, or diagnosing search
  indexes.
- Telegram topic-safe search commands.
- Decision, blocker, and task extraction from search results after retrieval
  quality is proven.
- Multi-user or hosted authorization semantics if Codi moves beyond local admin
  deployment.

## Constraints

- Preserve the invariant that session routing is keyed by tmux window IDs, not
  names.
- Treat transcript/session state as authoritative; the search index is derived
  and rebuildable.
- Do not block FastAPI startup, WebSocket delivery, Telegram delivery, terminal
  handling, or session-monitor polling on embedding or indexing work.
- Keep CPU and memory use appropriate for local Mac mini deployment.
- Message truncation remains a Telegram send-layer concern; search ingestion
  uses richer local transcript text where available.
- The Web UI should continue working while initial indexing status is
  incomplete or degraded.

## Key Decisions

| Decision | Outcome | Rationale |
| --- | --- | --- |
| V1 scope | Open sessions only | Matches the immediate Web UI switching workflow and keeps initial index bounded. |
| Runtime isolation | Search worker outside hot paths | Protects Codi's API/event loop from embedding latency and model memory use. |
| Retrieval | Hybrid lexical + semantic | Exact command/error matching and meaning-based lookup are both important for session search. |
| Index backend | LanceDB hybrid generation metadata plus lexical fallback | Provides local vector storage while preserving degraded search when semantic components are unavailable. |
| Embedding model | Qwen3-Embedding-0.6B candidate with opt-in benchmark validation | Small enough for local use while still plausible for code and multilingual technical text. |
| Live batching | 32 items or 60 seconds | Keeps new turns fresh without embedding every message synchronously. |
| Status contract | Missing/not-ready search is a typed normal response | Prevents the Web UI from confusing no matches with unavailable or still-building search. |
| Identity contract | Indexed row identity comes from transcript provenance plus chunk index | Keeps search rows stable across renames, cwd changes, pinning, and tmux window movement. |
| Activation contract | Search generations are built inactive and atomically activated | Prevents interrupted rebuilds from becoming active and keeps startup/rebuild rerunnable. |
| Degraded behavior | Search degrades to lexical-only or typed unavailable status | Keeps normal Codi session delivery independent from search worker health. |

## Evolution

The next milestone should start from the archived v1.0 state and choose a new
active scope rather than adding work to the closed v1 requirements file.

---

Last updated: 2026-05-25 after v1.0 Session Search milestone completion.
