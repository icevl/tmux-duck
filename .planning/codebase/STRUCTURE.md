# Codebase Structure

**Analysis Date:** 2026-05-21

## Directory Layout

```text
codi/
|-- AGENTS.md                         # Repository-specific agent instructions and design constraints
|-- README.md                         # Product overview and setup guidance
|-- pyproject.toml                    # Python package, dependencies, scripts, ruff, pyright, pytest
|-- Dockerfile                        # Container build
|-- docker-compose.yml                # Container orchestration entry
|-- docker/
|   `-- entrypoint.sh                 # Container startup helper
|-- scripts/
|   |-- restart.sh                    # Local restart helper
|   |-- install_macos_launchd.sh      # macOS service installer
|   |-- uninstall_macos_launchd.sh    # macOS service remover
|   `-- git-hooks/pre-push           # Local git hook helper
|-- src/
|   `-- codexbot/
|       |-- main.py                   # Python process entrypoint
|       |-- bot.py                    # Telegram application and lifecycle wiring
|       |-- config.py                 # Environment-backed configuration
|       |-- session.py                # Window/session/topic state manager
|       |-- tmux_manager.py           # tmux integration
|       |-- session_monitor.py        # Transcript polling and event dispatch
|       |-- monitor_state.py          # Monitor offset persistence
|       |-- transcript_parser.py      # Codex/Claude transcript normalization
|       |-- terminal_parser.py        # Terminal UI/status parsing
|       |-- handlers/                 # Telegram delivery and interaction helpers
|       |-- runtimes/                 # Codex and Claude runtime adapters
|       |-- web/                      # FastAPI app, auth, events, streaming
|       `-- fonts/                    # Fonts used by screenshot rendering
|-- web-ui/
|   |-- package.json                  # Frontend dependencies and scripts
|   |-- vite.config.ts                # Vite configuration
|   |-- tsconfig.json                 # TypeScript configuration
|   |-- src/                          # React SPA source
|   `-- public/office/                # Office scene assets and persisted state
|-- tests/
|   |-- codexbot/                     # Backend unit tests
|   `-- integration/                  # Integration tests
|-- .github/workflows/                # GitHub Actions workflows
`-- .planning/codebase/               # Generated GSD codebase maps
```

## Directory Purposes

**Repository Root:**
- Purpose: Project-level documentation, packaging, service scripts, and deployment files.
- Contains: `AGENTS.md`, `README.md`, `pyproject.toml`, `Dockerfile`, `docker-compose.yml`, `LICENSE`.
- Key files: `pyproject.toml`, `README.md`, `AGENTS.md`.

**`src/codexbot/`:**
- Purpose: Python backend package for tmux orchestration, Telegram integration, web API hosting, transcript monitoring, and runtime coordination.
- Contains: Core services, parser modules, screenshot/transcription helpers, runtime adapters, Telegram handler helpers, and web server modules.
- Key files: `src/codexbot/main.py`, `src/codexbot/bot.py`, `src/codexbot/session.py`, `src/codexbot/tmux_manager.py`, `src/codexbot/session_monitor.py`.

**`src/codexbot/handlers/`:**
- Purpose: Telegram-specific UI, message delivery, callback, history, status, and interactive prompt helpers.
- Contains: Queue workers, message sender wrappers, response builders, directory/window/runtime pickers, interactive UI rendering, and cleanup helpers.
- Key files: `src/codexbot/handlers/message_queue.py`, `src/codexbot/handlers/directory_browser.py`, `src/codexbot/handlers/interactive_ui.py`, `src/codexbot/handlers/history.py`, `src/codexbot/handlers/status_polling.py`.

**`src/codexbot/runtimes/`:**
- Purpose: Encapsulate agent-runtime differences so Codex and Claude Code can share session, tmux, web, and Telegram flows.
- Contains: Runtime protocol, runtime registry, Codex adapter, Claude adapter.
- Key files: `src/codexbot/runtimes/base.py`, `src/codexbot/runtimes/__init__.py`, `src/codexbot/runtimes/codex.py`, `src/codexbot/runtimes/claude.py`.

**`src/codexbot/web/`:**
- Purpose: Browser channel backend: FastAPI application, web authentication, WebSocket event bus, pane streaming, screenshots, and update checks.
- Contains: API routes, auth helper, event bus, server lifecycle, pane stream polling, screenshot helper, update checker.
- Key files: `src/codexbot/web/api.py`, `src/codexbot/web/auth.py`, `src/codexbot/web/events.py`, `src/codexbot/web/server.py`, `src/codexbot/web/streaming.py`.

**`src/codexbot/fonts/`:**
- Purpose: Font assets used for screenshot rendering and monospace/CJK/symbol coverage.
- Contains: JetBrains Mono, Noto Sans Mono CJK, Symbola fonts, and font licenses.
- Key files: `src/codexbot/fonts/JetBrainsMono-Regular.ttf`, `src/codexbot/fonts/NotoSansMonoCJKsc-Regular.otf`, `src/codexbot/fonts/Symbola.ttf`.

**`web-ui/src/`:**
- Purpose: React browser application for session management, chat, terminal, diffs, screenshots, skills, updates, and office visualization.
- Contains: Top-level app shell, API client, WebSocket client, CSS, and UI components.
- Key files: `web-ui/src/App.tsx`, `web-ui/src/api.ts`, `web-ui/src/ws.ts`, `web-ui/src/main.tsx`, `web-ui/src/styles.css`.

**`web-ui/src/components/`:**
- Purpose: Browser UI panels, dialogs, modals, markdown rendering, notifications, and feature surfaces.
- Contains: Chat, sidebar, terminal, diff, login, screenshot, skills, update banner, toast, rename/confirm/new-session dialogs, office panel.
- Key files: `web-ui/src/components/ChatView.tsx`, `web-ui/src/components/Sidebar.tsx`, `web-ui/src/components/TerminalPanel.tsx`, `web-ui/src/components/DiffPanel.tsx`, `web-ui/src/components/NewSessionDialog.tsx`.

**`web-ui/src/components/office/`:**
- Purpose: Office scene editor and rendering engine used by `OfficePanel`.
- Contains: Asset catalog, scene engine, and editor UI.
- Key files: `web-ui/src/components/office/engine.ts`, `web-ui/src/components/office/catalog.ts`, `web-ui/src/components/office/Editor.tsx`.

**`web-ui/public/office/`:**
- Purpose: Static office visualization assets and editable office state served by the web app.
- Contains: Room image, furniture image, character images, license, and `state.json`.
- Key files: `web-ui/public/office/room.png`, `web-ui/public/office/furniture.png`, `web-ui/public/office/state.json`.

**`tests/codexbot/`:**
- Purpose: Unit tests for backend services, parsers, Telegram helpers, web API/auth/events/server/streaming, and utility modules.
- Contains: `test_*.py` files mirroring backend modules and a backend test `conftest.py`.
- Key files: `tests/codexbot/test_session.py`, `tests/codexbot/test_session_monitor.py`, `tests/codexbot/test_transcript_parser.py`, `tests/codexbot/test_web_api.py`.

**`tests/codexbot/handlers/`:**
- Purpose: Unit tests for Telegram handler helper modules.
- Contains: Handler-specific `test_*.py` files.
- Key files: `tests/codexbot/handlers/test_message_queue.py`, `tests/codexbot/handlers/test_interactive_ui.py`, `tests/codexbot/handlers/test_status_polling.py`.

**`tests/integration/`:**
- Purpose: Integration tests for configuration and monitor-state behavior.
- Contains: Integration-level `test_*.py` files.
- Key files: `tests/integration/test_config_integration.py`, `tests/integration/test_monitor_state_integration.py`.

**`scripts/`:**
- Purpose: Local operational helpers and git hook support.
- Contains: Restart script, macOS launchd install/uninstall scripts, and pre-push hook helper.
- Key files: `scripts/restart.sh`, `scripts/install_macos_launchd.sh`, `scripts/uninstall_macos_launchd.sh`, `scripts/git-hooks/pre-push`.

**`docker/`:**
- Purpose: Container startup support.
- Contains: Entrypoint script.
- Key files: `docker/entrypoint.sh`.

**`.github/workflows/`:**
- Purpose: GitHub Actions automation.
- Contains: CI/check workflow and Claude-related workflow definitions.
- Key files: `.github/workflows/check.yml`, `.github/workflows/claude.yml`, `.github/workflows/claude-code-review.yml`.

**`.planning/codebase/`:**
- Purpose: Generated GSD codebase maps consumed by planning and execution agents.
- Contains: Architecture, structure, stack, integration, convention, testing, and concern documents when generated.
- Key files: `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/STRUCTURE.md`.

## Key File Locations

**Entry Points:**
- `src/codexbot/main.py`: Python CLI entrypoint used by the `codexbot` console script.
- `src/codexbot/bot.py`: Telegram application factory, command registration, and backend lifecycle hooks.
- `src/codexbot/web/server.py`: Embedded web server startup/shutdown.
- `src/codexbot/web/api.py`: FastAPI app factory, REST endpoints, event WebSocket, terminal WebSocket, and SPA static serving.
- `web-ui/src/main.tsx`: React app mount point.
- `Dockerfile`: Container build entry.
- `docker/entrypoint.sh`: Container runtime entrypoint.
- `scripts/restart.sh`: Local operational restart entry.

**Configuration:**
- `pyproject.toml`: Backend package metadata, dependencies, console script, pytest, pyright, and ruff configuration.
- `web-ui/package.json`: Frontend dependencies, scripts, and package manager declaration.
- `web-ui/vite.config.ts`: Vite build/dev configuration.
- `web-ui/tsconfig.json`: TypeScript compiler configuration.
- `src/codexbot/config.py`: Runtime configuration and environment variable interpretation.
- `AGENTS.md`: Repository-specific agent constraints.

**Core Logic:**
- `src/codexbot/session.py`: Durable window/session/topic state, session ID discovery, and history loading.
- `src/codexbot/tmux_manager.py`: tmux session/window/pane operations.
- `src/codexbot/session_monitor.py`: Transcript monitoring and event dispatch.
- `src/codexbot/transcript_parser.py`: Shared transcript normalization.
- `src/codexbot/terminal_parser.py`: Terminal status, command, and interactive UI parsing.
- `src/codexbot/runtimes/base.py`: Runtime adapter contract.
- `src/codexbot/runtimes/codex.py`: Codex adapter.
- `src/codexbot/runtimes/claude.py`: Claude Code adapter.
- `src/codexbot/handlers/message_queue.py`: Ordered Telegram queue.
- `src/codexbot/web/events.py`: Browser event bus.
- `src/codexbot/web/streaming.py`: Live tmux pane stream publisher.
- `web-ui/src/App.tsx`: Browser app shell.
- `web-ui/src/components/ChatView.tsx`: Browser chat/history/composer surface.
- `web-ui/src/components/TerminalPanel.tsx`: Browser terminal surface.
- `web-ui/src/components/Sidebar.tsx`: Browser session navigation.

**Testing:**
- `tests/codexbot/test_session.py`: Session state and binding behavior.
- `tests/codexbot/test_session_monitor.py`: Monitor behavior.
- `tests/codexbot/test_transcript_parser.py`: Transcript normalization behavior.
- `tests/codexbot/test_terminal_parser.py`: Terminal parser behavior.
- `tests/codexbot/test_web_api.py`: FastAPI route behavior.
- `tests/codexbot/test_web_events.py`: Web event behavior.
- `tests/codexbot/test_web_streaming.py`: Pane streaming behavior.
- `tests/codexbot/handlers/test_message_queue.py`: Telegram queue behavior.
- `tests/integration/test_config_integration.py`: Config integration behavior.

## Naming Conventions

**Files:**
- Backend modules use lowercase snake_case: `src/codexbot/session_monitor.py`, `src/codexbot/terminal_parser.py`, `src/codexbot/skill_hints.py`.
- Backend tests use `test_*.py` and mirror source module names: `tests/codexbot/test_session_monitor.py`, `tests/codexbot/test_web_api.py`.
- React components use PascalCase `.tsx`: `web-ui/src/components/ChatView.tsx`, `web-ui/src/components/TerminalPanel.tsx`.
- Frontend non-component helpers use lowercase `.ts`: `web-ui/src/api.ts`, `web-ui/src/ws.ts`.
- Runtime adapters are named by runtime key: `src/codexbot/runtimes/codex.py`, `src/codexbot/runtimes/claude.py`.

**Directories:**
- Backend feature groups use lowercase names: `src/codexbot/handlers/`, `src/codexbot/runtimes/`, `src/codexbot/web/`.
- Frontend reusable UI lives in `web-ui/src/components/`.
- Frontend domain-specific office code lives in `web-ui/src/components/office/`.
- Tests are split by backend unit tests under `tests/codexbot/` and integration tests under `tests/integration/`.

**Symbols:**
- Python classes use PascalCase: `SessionManager`, `WindowState`, `TmuxManager`, `TranscriptParser`.
- Python functions and variables use snake_case: `get_window_for_thread`, `send_to_window`, `refresh_window_session_if_stale`.
- Shared Python singleton instances use lowercase module globals: `config`, `session_manager`, `tmux_manager`.
- React components use PascalCase exports: `ChatView`, `Sidebar`, `TerminalPanel`.
- Frontend types use PascalCase: `SessionInfo`, `SessionMessage`, `WsEvent`.

## Where to Add New Code

**New Telegram Command or Topic Flow:**
- Primary code: `src/codexbot/bot.py`
- Helper UI/state code: `src/codexbot/handlers/`
- Tests: `tests/codexbot/test_*.py` or `tests/codexbot/handlers/test_*.py`
- Use `session_manager` and `tmux_manager` instead of storing independent routing state.

**New Web REST Endpoint:**
- Backend route: `src/codexbot/web/api.py`
- Frontend client method/type: `web-ui/src/api.ts`
- Calling UI: `web-ui/src/App.tsx` or `web-ui/src/components/`
- Tests: `tests/codexbot/test_web_api.py`

**New Browser WebSocket Event:**
- Publisher: `src/codexbot/web/events.py` or the owning backend service.
- Event type: `web-ui/src/api.ts`
- Subscriber: `web-ui/src/App.tsx`, `web-ui/src/components/ChatView.tsx`, or the relevant component.
- Tests: `tests/codexbot/test_web_events.py` plus focused frontend validation when available.

**New Agent Runtime:**
- Adapter implementation: `src/codexbot/runtimes/<runtime>.py`
- Contract: `src/codexbot/runtimes/base.py`
- Registry: `src/codexbot/runtimes/__init__.py`
- Terminal chrome parsing if needed: `src/codexbot/terminal_parser.py`
- Session detection tests: `tests/codexbot/test_session.py` and runtime-specific tests under `tests/codexbot/`.

**New Session Metadata:**
- Durable model: `WindowState` in `src/codexbot/session.py`
- Persistence/migration: `_save_state()` and `_load_state()` in `src/codexbot/session.py`
- Web API response/request types: `src/codexbot/web/api.py`
- Frontend types and rendering: `web-ui/src/api.ts`, `web-ui/src/App.tsx`, `web-ui/src/components/Sidebar.tsx`
- Tests: `tests/codexbot/test_session.py`, `tests/codexbot/test_web_api.py`

**New Transcript Record or Display Type:**
- Parser: `src/codexbot/transcript_parser.py`
- Live monitor integration: `src/codexbot/session_monitor.py`
- History access: `src/codexbot/session.py`
- Telegram rendering: `src/codexbot/handlers/response_builder.py`, `src/codexbot/handlers/message_queue.py`
- Browser rendering: `web-ui/src/components/ChatView.tsx`, `web-ui/src/components/Markdown.tsx`
- Tests: `tests/codexbot/test_transcript_parser.py`, `tests/codexbot/test_session_monitor.py`

**New Terminal Status or Interactive UI Pattern:**
- Parser: `src/codexbot/terminal_parser.py`
- Telegram interactive handling: `src/codexbot/handlers/interactive_ui.py`
- Status polling: `src/codexbot/handlers/status_polling.py`
- Tests: `tests/codexbot/test_terminal_parser.py`, `tests/codexbot/handlers/test_interactive_ui.py`, `tests/codexbot/handlers/test_status_polling.py`

**New React Panel or Dialog:**
- Component: `web-ui/src/components/<Name>.tsx`
- Top-level placement/state: `web-ui/src/App.tsx`
- API calls/types: `web-ui/src/api.ts`
- Styling: `web-ui/src/styles.css`

**New Office Visualization Behavior:**
- Engine/catalog/editor: `web-ui/src/components/office/`
- Panel integration: `web-ui/src/components/OfficePanel.tsx`
- Assets/state: `web-ui/public/office/`
- Persistence endpoint: `src/codexbot/web/api.py`

**Shared Backend Utility:**
- Cross-cutting helper: `src/codexbot/utils.py`
- Domain-specific helper: keep it near the owning module, such as `src/codexbot/handlers/` for Telegram helpers or `src/codexbot/web/` for web helpers.
- Tests: matching `tests/codexbot/test_*.py`.

**Operational Script:**
- Local developer/service scripts: `scripts/`
- Container startup scripts: `docker/`
- CI workflow: `.github/workflows/`

## Special Directories

**`.planning/codebase/`:**
- Purpose: Generated codebase mapping documents for GSD planning/execution.
- Generated: Yes
- Committed: Yes, when planning artifacts are tracked for the project.

**`.venv/`:**
- Purpose: Local Python virtual environment.
- Generated: Yes
- Committed: No

**`web-ui/node_modules/`:**
- Purpose: Local frontend dependency install tree.
- Generated: Yes
- Committed: No

**`web-ui/dist/`:**
- Purpose: Vite production build served by `src/codexbot/web/api.py` when present.
- Generated: Yes
- Committed: Not detected in the current source listing.

**`.pytest_cache/` and `.ruff_cache/`:**
- Purpose: Local test/lint caches.
- Generated: Yes
- Committed: No

**`src/codexbot/fonts/`:**
- Purpose: Runtime font assets for screenshots.
- Generated: No
- Committed: Yes

**`web-ui/public/office/`:**
- Purpose: Static office scene assets plus editable `state.json`.
- Generated: No
- Committed: Yes

**Runtime State Outside The Repo:**
- Purpose: Codi process state and runtime transcripts.
- Generated: Yes
- Committed: No
- Locations: `~/.codexbot/state.json`, `~/.codexbot/monitor_state.json`, `~/.codexbot/web_ui_secret`, `~/.codexbot/web_ui_totp_secret`, `~/.codex/sessions`, `~/.claude/sessions`, `~/.claude/projects`.

---

*Structure analysis: 2026-05-21*
