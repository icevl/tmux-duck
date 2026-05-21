<!-- refreshed: 2026-05-21 -->
# Architecture

**Analysis Date:** 2026-05-21

## System Overview

```text
+-------------------------------------------------------------------+
|                         Frontend Channels                         |
+-------------------------------+-----------------------------------+
| Telegram topics               | Browser SPA                       |
| `src/codexbot/bot.py`         | `web-ui/src/App.tsx`              |
| `src/codexbot/handlers/`      | `web-ui/src/components/`          |
+---------------+---------------+-------------------+---------------+
                |                                   |
                v                                   v
+-------------------------------------------------------------------+
|                    Single Python Async Backend                     |
| `src/codexbot/main.py`                                             |
| `src/codexbot/bot.py` + `src/codexbot/web/server.py`               |
+---------------+-------------------+---------------+---------------+
                |                   |               |
                v                   v               v
+-------------------------------------------------------------------+
|                         Shared Domain Layer                        |
| `src/codexbot/session.py`                                          |
| `src/codexbot/tmux_manager.py`                                     |
| `src/codexbot/runtimes/`                                           |
+---------------+-------------------+---------------+---------------+
                |                   |               |
                v                   v               v
+-------------------------------------------------------------------+
|                    Event, Transcript, and Delivery                 |
| `src/codexbot/session_monitor.py`                                  |
| `src/codexbot/transcript_parser.py`                                |
| `src/codexbot/web/events.py`                                       |
| `src/codexbot/handlers/message_queue.py`                           |
+---------------+-------------------+---------------+---------------+
                |                   |               |
                v                   v               v
+-------------------------------------------------------------------+
|                         Runtime State Stores                       |
| tmux session/window/panes                                          |
| `~/.codexbot/state.json` and `~/.codexbot/monitor_state.json`      |
| `~/.codex/sessions`, `~/.claude/sessions`, `~/.claude/projects`    |
+-------------------------------------------------------------------+
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Process bootstrap | Enforce a single running backend, load configuration, connect to tmux, and start Telegram polling. | `src/codexbot/main.py` |
| Configuration | Read environment-driven settings, derive state paths, define runtime commands, and scrub sensitive variables before child agent startup. | `src/codexbot/config.py` |
| Telegram application | Own python-telegram-bot setup, command handlers, topic routing, runtime/session creation, and lifecycle hooks. | `src/codexbot/bot.py` |
| Web server lifecycle | Start and stop embedded Uvicorn, the WebSocket event bus, pane streaming, update checks, and monitor listener wiring. | `src/codexbot/web/server.py` |
| Web API | Expose authenticated REST and WebSocket endpoints for sessions, messages, terminal access, git metadata, runtime metadata, screenshots, uploads, and office state. | `src/codexbot/web/api.py` |
| Web event bus | Fan out monitor events and backend notifications to browser WebSocket subscribers. | `src/codexbot/web/events.py` |
| Pane streaming | Poll tmux panes while browser clients are subscribed and publish live terminal stream events. | `src/codexbot/web/streaming.py` |
| Session state hub | Persist tmux window metadata, map Telegram topics to windows, resolve runtime session IDs, load transcript history, and provide shared send APIs. | `src/codexbot/session.py` |
| tmux gateway | Create, list, rename, kill, capture, and send input to tmux windows using window IDs as stable routing keys. | `src/codexbot/tmux_manager.py` |
| Runtime adapters | Encapsulate Codex and Claude Code startup commands, session discovery hooks, and pane command matching. | `src/codexbot/runtimes/` |
| Transcript monitor | Poll runtime transcript JSONL files by byte offset, parse new entries, and dispatch `NewMessage` events. | `src/codexbot/session_monitor.py` |
| Monitor persistence | Persist per-runtime transcript file offsets and tracked session metadata. | `src/codexbot/monitor_state.py` |
| Transcript parsing | Normalize Codex and Claude transcript records into display-ready message/tool/completion entries. | `src/codexbot/transcript_parser.py` |
| Search contracts/state/provider | Define runtime-neutral search DTOs, reserve derived state under `CODEXBOT_DIR/search`, read active generation metadata, and return typed missing-index status/search responses without worker/model imports. | `src/codexbot/search/` |
| Terminal parsing | Parse Codex/Claude terminal chrome, status lines, bash output, and interactive UI prompts from tmux pane text. | `src/codexbot/terminal_parser.py` |
| Telegram delivery queue | Serialize per-user/topic Telegram sends, preserve ordering, coalesce status updates, and retry around flood waits. | `src/codexbot/handlers/message_queue.py` |
| Telegram UI helpers | Build directory, runtime, window, resume-session, history, interactive prompt, and response rendering flows. | `src/codexbot/handlers/` |
| Web SPA shell | Own authentication bootstrap, session list state, WebSocket wiring, resizable layout, and top-level command handlers. | `web-ui/src/App.tsx` |
| Web API client | Centralize typed REST requests and shared WebSocket event types for the React app. | `web-ui/src/api.ts` |
| Web event client | Maintain an auto-reconnecting browser WebSocket connection to `/api/ws`. | `web-ui/src/ws.ts` |
| Chat view | Render history, stream updates, composer input, slash/skill hints, uploads, git branch controls, and live message reconciliation. | `web-ui/src/components/ChatView.tsx` |
| Session sidebar | Render and reorder sessions, pin sessions, show runtime icons, and launch session management dialogs. | `web-ui/src/components/Sidebar.tsx` |
| Browser terminal | Connect xterm.js to the backend terminal WebSocket for attached tmux panes or persistent shell sessions. | `web-ui/src/components/TerminalPanel.tsx` |
| Git diff panel | Fetch and display repository diffs for the selected session cwd. | `web-ui/src/components/DiffPanel.tsx` |
| Office visualization | Render and edit the office scene backed by public assets and `/api/office/state`. | `web-ui/src/components/OfficePanel.tsx` |

## Pattern Overview

**Overall:** Single-process async bridge over tmux with two synchronized frontends and transcript-driven updates.

**Key Characteristics:**
- Use tmux windows as the durable execution unit. One Codi session maps to one tmux window, and routing uses tmux window IDs such as `@12`.
- Keep Telegram and browser UI paths on the same backend objects: `session_manager` in `src/codexbot/session.py`, `tmux_manager` in `src/codexbot/tmux_manager.py`, and `SessionMonitor` in `src/codexbot/session_monitor.py`.
- Treat runtime transcript JSONL files as the authoritative source for assistant/user/tool history and use `src/codexbot/transcript_parser.py` for both history and live monitor parsing.
- Hide runtime-specific behavior behind `AgentRuntime` implementations in `src/codexbot/runtimes/`.
- Deliver browser updates through `EventBus` in `src/codexbot/web/events.py` and Telegram updates through the ordered queue in `src/codexbot/handlers/message_queue.py`.

## Layers

**Bootstrap and Configuration:**
- Purpose: Start the singleton process and create the configured tmux session.
- Location: `src/codexbot/main.py`, `src/codexbot/config.py`, `src/codexbot/utils.py`
- Contains: CLI entrypoint, environment loading, state directory resolution, lock file handling, and process-level safety.
- Depends on: `python-dotenv`, `libtmux`, local filesystem state under `~/.codexbot/`.
- Used by: Every backend layer through the `config` singleton and `codexbot_dir()`.

**Transport and UI Ingress:**
- Purpose: Accept user commands from Telegram topics and browser HTTP/WebSocket clients.
- Location: `src/codexbot/bot.py`, `src/codexbot/handlers/`, `src/codexbot/web/api.py`, `web-ui/src/`
- Contains: Telegram command handlers, FastAPI route handlers, React UI actions, WebSocket terminal/event endpoints.
- Depends on: Shared session/tmux services, authentication helpers, Telegram allowlist, signed web cookies.
- Used by: Users through Telegram and the browser SPA.

**Session and tmux Domain:**
- Purpose: Represent windows, bindings, runtime session IDs, and pane I/O.
- Location: `src/codexbot/session.py`, `src/codexbot/tmux_manager.py`
- Contains: `WindowState`, topic bindings, window metadata, session discovery, tmux send/capture/window lifecycle operations.
- Depends on: `libtmux`, runtime adapters, persisted JSON state, transcript indexes.
- Used by: Telegram handlers, web API endpoints, monitor setup, pane streaming, terminal sockets.

**Runtime Adapter Layer:**
- Purpose: Keep Codex-specific and Claude-specific launch and session-discovery details out of UI code.
- Location: `src/codexbot/runtimes/base.py`, `src/codexbot/runtimes/codex.py`, `src/codexbot/runtimes/claude.py`, `src/codexbot/runtimes/__init__.py`
- Contains: `AgentRuntime` protocol, registry helpers, default runtime selection, command builders, pane command checks, startup prompt advancement.
- Depends on: `config`, process inspection, runtime transcript paths.
- Used by: `SessionManager` and `TmuxManager` when creating and resolving windows.

**Transcript and Event Layer:**
- Purpose: Convert runtime transcript files and terminal panes into normalized events for both frontends.
- Location: `src/codexbot/session_monitor.py`, `src/codexbot/monitor_state.py`, `src/codexbot/transcript_parser.py`, `src/codexbot/terminal_parser.py`
- Contains: byte-offset polling, transcript entry normalization, completion detection, UI/status parsing, monitor state persistence.
- Depends on: Runtime transcript directories, `session_manager`, `tmux_manager`, local JSON files.
- Used by: `handle_new_message()` in `src/codexbot/bot.py`, `EventBus` in `src/codexbot/web/events.py`, history endpoints in `src/codexbot/web/api.py`.

**Search Contract and Derived-State Layer:**
- Purpose: Define stable search provenance/status/request/response contracts and isolate search-owned derived metadata from authoritative session and monitor state.
- Location: `src/codexbot/search/contracts.py`, `src/codexbot/search/state.py`, `src/codexbot/search/client.py`
- Contains: Pydantic DTOs, `codexbot_dir() / "search"` namespace helpers, active generation metadata reads, and typed missing-index provider responses.
- Depends on: `pydantic`, `src/codexbot/utils.py`, optional JSON metadata under `$CODEXBOT_DIR/search/`.
- Used by: Future authenticated search/status API routes and later worker/index phases.

**Delivery Layer:**
- Purpose: Send parsed updates to external clients without breaking ordering or overloading Telegram.
- Location: `src/codexbot/handlers/message_queue.py`, `src/codexbot/telegram_sender.py`, `src/codexbot/web/events.py`, `src/codexbot/web/streaming.py`
- Contains: Telegram queue workers, status coalescing, content/completion tasks, WebSocket pub/sub, pane stream events.
- Depends on: Telegram bot API, FastAPI WebSocket connections, monitor events.
- Used by: Telegram topics and browser subscribers.

**Frontend Layer:**
- Purpose: Provide the browser SPA for sessions, chat, terminal, diffs, screenshots, skills, updates, and office visualization.
- Location: `web-ui/src/App.tsx`, `web-ui/src/api.ts`, `web-ui/src/ws.ts`, `web-ui/src/components/`
- Contains: React state, typed API client, reconnecting WebSocket client, panels, dialogs, message reconciliation, xterm terminal integration.
- Depends on: Backend HTTP endpoints, `/api/ws`, terminal WebSockets, localStorage.
- Used by: Browser users.

## Data Flow

### Browser Text Message Path

1. `ChatView` submits text through the typed client (`web-ui/src/components/ChatView.tsx`, `web-ui/src/api.ts`).
2. `POST /api/sessions/{window_id}/send` validates authentication and resolves the selected window (`src/codexbot/web/api.py`).
3. `SessionManager.send_to_window()` records special rebinding commands and delegates pane input (`src/codexbot/session.py`).
4. `TmuxManager.send_keys()` sends literal text and Enter to the target pane (`src/codexbot/tmux_manager.py`).
5. The runtime writes transcript records under `~/.codex/sessions` or `~/.claude/projects`, depending on the window runtime (`src/codexbot/config.py`, `src/codexbot/runtimes/`).
6. `SessionMonitor.check_for_updates()` reads new JSONL bytes and builds `NewMessage` objects (`src/codexbot/session_monitor.py`).
7. `EventBus.publish_message()` emits WebSocket events, and `ChatView` merges them into the visible message list (`src/codexbot/web/events.py`, `web-ui/src/components/ChatView.tsx`).
8. If the runtime session is bound to a Telegram topic, `handle_new_message()` also queues Telegram delivery (`src/codexbot/bot.py`, `src/codexbot/handlers/message_queue.py`).

### Telegram Topic Message Path

1. `text_handler()` receives a topic message and enforces the topic-only model (`src/codexbot/bot.py`).
2. If the topic is unbound, Telegram picker state is resolved through runtime/window/directory helpers (`src/codexbot/handlers/directory_browser.py`).
3. `_create_and_bind_window()` creates the tmux window, persists `WindowState`, detects the runtime session ID, primes monitor offsets, and binds the topic (`src/codexbot/bot.py`, `src/codexbot/session.py`).
4. Bound text is forwarded with `SessionManager.send_to_window()` and `TmuxManager.send_keys()` (`src/codexbot/session.py`, `src/codexbot/tmux_manager.py`).
5. Transcript monitor events flow back through `handle_new_message()` and the per-user/topic queue (`src/codexbot/session_monitor.py`, `src/codexbot/bot.py`, `src/codexbot/handlers/message_queue.py`).

### Session Creation Path

1. Browser creation starts in `NewSessionDialog` and calls `POST /api/sessions` (`web-ui/src/components/NewSessionDialog.tsx`, `web-ui/src/api.ts`).
2. `create_session()` validates cwd/runtime data, creates a tmux window, stores `WindowState`, and attempts session detection (`src/codexbot/web/api.py`).
3. Telegram creation follows `_create_and_bind_window()` and uses the same `TmuxManager.create_window()` and `SessionManager.set_window_state()` path (`src/codexbot/bot.py`, `src/codexbot/tmux_manager.py`, `src/codexbot/session.py`).
4. Both paths publish or trigger `sessions_changed` so browser sidebars refresh (`src/codexbot/web/api.py`, `src/codexbot/web/events.py`, `web-ui/src/App.tsx`).

### Transcript History Path

1. Browser history calls `GET /api/sessions/{window_id}/messages` (`web-ui/src/components/ChatView.tsx`, `web-ui/src/api.ts`).
2. `get_messages()` resolves the selected window and asks `SessionManager.get_history_snapshot()` for transcript data (`src/codexbot/web/api.py`, `src/codexbot/session.py`).
3. `SessionManager` locates transcript paths from indexed Codex and Claude sessions and reads JSONL entries (`src/codexbot/session.py`).
4. `TranscriptParser.parse_entries()` normalizes messages, tool calls, tool results, images, and completion markers (`src/codexbot/transcript_parser.py`).
5. `ChatView` caches history, sorts by transcript position, removes duplicates, and reconciles live events with fetched history (`web-ui/src/components/ChatView.tsx`).

### Browser Terminal Path

1. `TerminalPanel` opens `/api/sessions/{window_id}/term?mode=...` (`web-ui/src/components/TerminalPanel.tsx`).
2. `terminal_socket()` authenticates by cookie or query token, checks origin, and selects attach or persistent shell mode (`src/codexbot/web/api.py`).
3. Attach mode starts a grouped tmux client for the selected window; shell mode starts or reuses a persistent PTY-backed shell (`src/codexbot/web/api.py`).
4. WebSocket binary frames carry terminal input, resize operations, and output between xterm.js and the backend (`web-ui/src/components/TerminalPanel.tsx`, `src/codexbot/web/api.py`).

**State Management:**
- `SessionManager` is a module-level singleton in `src/codexbot/session.py`; it persists schema-versioned window/topic state to `~/.codexbot/state.json`.
- `MonitorState` in `src/codexbot/monitor_state.py` persists transcript offsets to `~/.codexbot/monitor_state.json`.
- Search derived metadata lives under `~/.codexbot/search` or `CODEXBOT_DIR/search` through `src/codexbot/search/state.py`; it is rebuildable and must not write to `state.json` or `monitor_state.json`.
- Telegram delivery state is module-level queue/worker maps keyed by `(user_id, thread_id)` in `src/codexbot/handlers/message_queue.py`.
- Browser layout and terminal preferences use localStorage in `web-ui/src/App.tsx` and `web-ui/src/components/TerminalPanel.tsx`.
- WebSocket subscribers and pane stream subscriptions are in-memory only in `src/codexbot/web/events.py` and `src/codexbot/web/streaming.py`.

## Key Abstractions

**`TmuxManager` and `TmuxWindow`:**
- Purpose: Provide an async-safe tmux facade and a normalized window record.
- Examples: `src/codexbot/tmux_manager.py`
- Pattern: Singleton service object with `asyncio.to_thread()` around blocking libtmux calls.

**`WindowState` and `SessionManager`:**
- Purpose: Bind tmux windows, runtime session IDs, cwd, display names, Telegram topics, and sort/pin metadata.
- Examples: `src/codexbot/session.py`
- Pattern: Dataclass state records plus a singleton manager persisted through atomic JSON writes.

**`AgentRuntime`:**
- Purpose: Define runtime-specific startup, resume, session discovery, and pane command behavior.
- Examples: `src/codexbot/runtimes/base.py`, `src/codexbot/runtimes/codex.py`, `src/codexbot/runtimes/claude.py`
- Pattern: Protocol and registry; add runtimes through `src/codexbot/runtimes/__init__.py`.

**`SessionMonitor` and `NewMessage`:**
- Purpose: Track transcript files and emit normalized updates to web and Telegram consumers.
- Examples: `src/codexbot/session_monitor.py`
- Pattern: Background polling service with listener callbacks and persisted byte offsets.

**`TranscriptParser` and parsed entry dataclasses:**
- Purpose: Share transcript normalization between live monitoring and history reads.
- Examples: `src/codexbot/transcript_parser.py`
- Pattern: Stateful parser that flattens runtime-specific JSONL records into canonical message entries.

**`EventBus`:**
- Purpose: Provide bounded in-process pub/sub for browser WebSocket updates.
- Examples: `src/codexbot/web/events.py`
- Pattern: Async subscriber queues with JSON-serializable events.

**`MessageTask` and Telegram queue workers:**
- Purpose: Preserve per-topic ordering and handle Telegram rate limits.
- Examples: `src/codexbot/handlers/message_queue.py`
- Pattern: Per-lane asyncio queues with worker tasks and pressure policy.

**`Authenticator`:**
- Purpose: Manage password login, signed cookies, optional TOTP, and WebSocket token validation.
- Examples: `src/codexbot/web/auth.py`
- Pattern: Shared web auth helper used by API routes and WebSocket endpoints.

**`EventStream` and `WsEvent`:**
- Purpose: Keep the browser connected to backend session, message, stream, skill, slash-command, and update notifications.
- Examples: `web-ui/src/ws.ts`, `web-ui/src/api.ts`
- Pattern: Typed event union plus auto-reconnecting client.

## Entry Points

**CLI Process:**
- Location: `src/codexbot/main.py`
- Triggers: `codexbot` console script from `pyproject.toml`
- Responsibilities: Load config, acquire `codexbot.lock`, connect to tmux, start Telegram polling, and run shutdown cleanup.

**Telegram Bot:**
- Location: `src/codexbot/bot.py`
- Triggers: `create_bot()` called by `src/codexbot/main.py`
- Responsibilities: Register commands and callbacks, enforce allowlist/topic routing, create/bind windows, start monitor and web server in `post_init()`.

**Web Server:**
- Location: `src/codexbot/web/server.py`
- Triggers: `start_web_server()` from Telegram `post_init()`
- Responsibilities: Create the FastAPI app, attach `EventBus`, start embedded Uvicorn, start pane streaming and update-check tasks.

**FastAPI Application:**
- Location: `src/codexbot/web/api.py`
- Triggers: `create_app()` from `src/codexbot/web/server.py`
- Responsibilities: Serve REST endpoints, WebSocket endpoints, the built SPA, and static fallback responses.

**React SPA:**
- Location: `web-ui/src/main.tsx`
- Triggers: Browser loads the bundled Vite application served from `web-ui/dist`
- Responsibilities: Mount `App`, bootstrap auth, fetch sessions, connect WebSocket events, and render the UI shell.

**Docker Runtime:**
- Location: `Dockerfile`, `docker-compose.yml`, `docker/entrypoint.sh`
- Triggers: Container deployment
- Responsibilities: Install backend/frontend runtime dependencies and launch the Python application.

**Operational Restart:**
- Location: `scripts/restart.sh`
- Triggers: Manual service restart from the repo
- Responsibilities: Restart the local Codi service using repository-specific operational assumptions.

## Architectural Constraints

- **Threading:** The backend is an asyncio application. Blocking libtmux operations in `src/codexbot/tmux_manager.py` run through `asyncio.to_thread()`. Uvicorn is embedded in the same process by `src/codexbot/web/server.py`. Terminal PTY bridging in `src/codexbot/web/api.py` uses event-loop readers and background tasks.
- **Global state:** Shared singletons and module-level state are intentional: `config` in `src/codexbot/config.py`, `tmux_manager` in `src/codexbot/tmux_manager.py`, `session_manager` in `src/codexbot/session.py`, queue maps in `src/codexbot/handlers/message_queue.py`, bot lifecycle globals in `src/codexbot/bot.py`, and web server handle state in `src/codexbot/web/server.py`.
- **Routing identity:** Route by tmux window ID everywhere. Do not use tmux window names, display names, Telegram topic names, cwd strings, or runtime session IDs as the primary routing key.
- **Telegram topics:** Telegram is topic-only. Unthreaded Telegram messages stop at the topic guidance path in `src/codexbot/bot.py`.
- **Transcript parsing:** Runtime transcript parsing belongs in `src/codexbot/transcript_parser.py`. Do not create separate ad hoc transcript parsers in web, Telegram, or tests.
- **Message truncation:** Apply Telegram message splitting/truncation only in the Telegram send path (`src/codexbot/telegram_sender.py`, `src/codexbot/handlers/message_queue.py`). Keep monitor, parser, session history, and web event payloads untruncated.
- **Child process environment:** Sensitive environment names are scrubbed in `src/codexbot/config.py` before launching agent runtimes. Keep secret handling centralized in configuration.
- **Circular imports:** Lower-level modules avoid importing the Telegram application layer. Use listener callbacks, local imports, or shared services instead of importing `src/codexbot/bot.py` from session, monitor, tmux, runtime, or web utility modules.

## Anti-Patterns

### Routing By Display Name

**What happens:** A caller chooses a target window by tmux name, display name, cwd, or Telegram topic label.
**Why it's wrong:** Names can be renamed or duplicated; the system contract uses tmux window IDs as stable identifiers.
**Do this instead:** Resolve and persist `window_id` through `TmuxWindow.window_id`, `WindowState.window_id`, and topic bindings in `src/codexbot/session.py`.

### Direct Telegram Sends From Monitor Code

**What happens:** Monitor or parser code calls Telegram send APIs directly.
**Why it's wrong:** It bypasses per-user ordering, status coalescing, retries, flood-wait handling, and safe markdown handling.
**Do this instead:** Emit `NewMessage` from `src/codexbot/session_monitor.py`, route through `handle_new_message()` in `src/codexbot/bot.py`, and enqueue through `src/codexbot/handlers/message_queue.py`.

### Runtime-Specific Branching In UI Handlers

**What happens:** Telegram handlers, web endpoints, or React code special-case Codex and Claude behavior.
**Why it's wrong:** Startup commands, resume flags, session discovery, and pane matching are runtime-layer concerns.
**Do this instead:** Add or change behavior through `AgentRuntime` implementations in `src/codexbot/runtimes/` and consume registry helpers from `src/codexbot/runtimes/__init__.py`.

### Independent Transcript Parsing

**What happens:** A route or frontend feature reads raw JSONL transcript entries and interprets them locally.
**Why it's wrong:** Codex and Claude emit multiple record shapes; live updates and history must normalize the same way to prevent duplicate, missing, or misordered messages.
**Do this instead:** Use `SessionManager.get_history_snapshot()` in `src/codexbot/session.py` or extend `TranscriptParser` in `src/codexbot/transcript_parser.py`.

### Web-Only Session State

**What happens:** Browser code keeps session metadata that is not reflected in `WindowState`.
**Why it's wrong:** Telegram and web share the same tmux windows, monitor offsets, runtime IDs, and sort/pin metadata.
**Do this instead:** Store durable session metadata through `SessionManager.set_window_state()` and expose it through `src/codexbot/web/api.py`.

## Error Handling

**Strategy:** Validate at transport boundaries, keep long-running background loops alive, and degrade individual delivery operations without stopping the shared backend.

**Patterns:**
- FastAPI routes in `src/codexbot/web/api.py` raise `HTTPException` for authentication failures, invalid windows, invalid directories, and unsupported operations.
- Telegram handlers in `src/codexbot/bot.py` check authorization, topic presence, binding state, and runtime/window availability before sending to tmux.
- `SessionMonitor` in `src/codexbot/session_monitor.py` tolerates partial transcript lines, stale sessions, missing files, and loop exceptions while persisting safe offsets.
- Telegram delivery in `src/codexbot/handlers/message_queue.py` retries around transient send failures and applies pressure policy to status messages only.
- File state writes use `atomic_write_json()` in `src/codexbot/utils.py` to avoid corrupting JSON state on process interruption.
- `SingleInstanceLock` in `src/codexbot/utils.py` prevents multiple backend processes from competing over the same tmux and state files.

## Cross-Cutting Concerns

**Logging:** Backend modules use Python `logging`, with named loggers in files such as `src/codexbot/bot.py`, `src/codexbot/session.py`, `src/codexbot/session_monitor.py`, `src/codexbot/web/api.py`, and `src/codexbot/handlers/message_queue.py`.

**Validation:** Backend validation lives at API/handler boundaries using Pydantic request models in `src/codexbot/web/api.py`, config validation in `src/codexbot/config.py`, path checks in `src/codexbot/tmux_manager.py`, and callback state helpers in `src/codexbot/handlers/`.

**Authentication:** Telegram access uses `ALLOWED_USERS` in `src/codexbot/config.py` and authorization checks in `src/codexbot/bot.py`. Web access uses password login, signed cookies, optional TOTP, WebSocket tokens, and origin checks in `src/codexbot/web/auth.py` and `src/codexbot/web/api.py`.

**Security Headers:** Web security headers and SPA serving rules are configured in `src/codexbot/web/api.py`.

**State Persistence:** Runtime state is stored outside the repo under `~/.codexbot/` by default. Source-controlled files such as `web-ui/public/office/state.json` are the exception and are accessed through `/api/office/state` in `src/codexbot/web/api.py`.

**External Process Boundaries:** Agent runtimes are tmux processes launched by `src/codexbot/tmux_manager.py`; git metadata is queried by subprocesses in `src/codexbot/web/api.py`; browser terminal sessions use PTY subprocesses in `src/codexbot/web/api.py`.

---

*Architecture analysis: 2026-05-21*
