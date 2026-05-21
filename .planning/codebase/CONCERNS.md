# Codebase Concerns

**Analysis Date:** 2026-05-21

## Tech Debt

**Large orchestration modules:**
- Issue: Core behavior is concentrated in large files that mix transport handling, lifecycle orchestration, state mutation, and UI-specific edge cases.
- Files: `src/codexbot/bot.py` (4681 lines), `src/codexbot/web/api.py` (1676 lines), `src/codexbot/handlers/message_queue.py` (1414 lines), `src/codexbot/session.py` (1295 lines), `web-ui/src/components/ChatView.tsx` (2782 lines)
- Impact: Small changes to routing, lifecycle, or session state have broad regression risk across Telegram, web, tmux, and transcript monitoring.
- Fix approach: Split by ownership boundary. Keep `src/codexbot/bot.py` as Telegram handler registration and delegate topic binding, screenshot actions, runtime picker flow, and command forwarding into focused modules under `src/codexbot/handlers/`. Split `src/codexbot/web/api.py` into route modules for auth, sessions, terminal, git, update, and office state.

**Channel configuration contract mismatch:**
- Issue: `docker/entrypoint.sh` allows either Telegram credentials or `WEB_UI_PASSWORD`, but `src/codexbot/config.py` hard-requires `TELEGRAM_BOT_TOKEN` and `ALLOWED_USERS` before web settings are useful.
- Files: `docker/entrypoint.sh:4`, `src/codexbot/config.py:112`, `src/codexbot/config.py:219`, `src/codexbot/main.py:31`, `tests/conftest.py:1`
- Impact: Web-only deployments cannot start through the Python entrypoint despite the Docker entrypoint and README describing web as an independent channel. Tests also work around this with forced Telegram env vars.
- Fix approach: Make channel requirements conditional in `Config`: Telegram requires both `TELEGRAM_BOT_TOKEN` and `ALLOWED_USERS`; web requires `WEB_UI_PASSWORD`; at least one channel must be enabled. Split Telegram bot construction from web-server startup in `src/codexbot/main.py`.

**Codex-centered resume indexing:**
- Issue: Resume discovery is runtime-agnostic at the API boundary but only lists sessions through `session_manager.list_sessions_for_directory()`, whose docstring and implementation are Codex-oriented. Telegram explicitly skips the picker for Claude.
- Files: `src/codexbot/web/api.py:1308`, `src/codexbot/session.py:947`, `src/codexbot/bot.py:3344`, `web-ui/src/components/NewSessionDialog.tsx:53`, `web-ui/src/components/NewSessionDialog.tsx:153`
- Impact: Claude Code sessions are created and detected, but historical Claude resume does not have a first-class picker path. The web dialog fetches resume options before runtime selection and submits a row with the default `runtime` state.
- Fix approach: Add `runtime` to `/api/resume-sessions`, select runtime before resume lookup in `web-ui/src/components/NewSessionDialog.tsx`, and implement Claude history indexing under `config.claude_projects_path` beside the existing Codex index in `src/codexbot/session.py`.

**Private dependency APIs:**
- Issue: Markdown conversion imports private `telegramify_markdown` symbols and pins below `0.6` because the imported internals changed.
- Files: `src/codexbot/markdown_v2.py:15`, `src/codexbot/markdown_v2.py:167`, `pyproject.toml:14`
- Impact: Telegram formatting is blocked on an old dependency surface; any security or compatibility update in `telegramify-markdown` requires local renderer changes first.
- Fix approach: Replace private imports with a local MarkdownV2 renderer for the subset Codi needs, or vendor the tiny rendering path used by `src/codexbot/markdown_v2.py` with tests in `tests/codexbot/test_markdown_v2.py`.

**Runtime state lives in module globals:**
- Issue: Queue workers, Telegram status tracking, tool message IDs, interactive prompt state, update status, and event subscribers are held in process-global dictionaries.
- Files: `src/codexbot/handlers/message_queue.py:91`, `src/codexbot/bot.py:224`, `src/codexbot/web/events.py:42`, `src/codexbot/web/update_checker.py:36`
- Impact: Restart, test isolation, and multi-instance reasoning depend on manual cleanup. Missed cleanup paths can produce stale status messages, stuck queues, or old WebSocket state.
- Fix approach: Move global state behind lifecycle-owned objects injected into handlers. Keep shutdown cleanup in one place and expose explicit reset methods for tests.

## Known Bugs

**Web-only startup fails through Python entrypoint:**
- Symptoms: Running `codexbot` with only `WEB_UI_PASSWORD` raises `ValueError("TELEGRAM_BOT_TOKEN environment variable is required")`.
- Files: `src/codexbot/config.py:112`, `src/codexbot/main.py:31`, `docker/entrypoint.sh:15`
- Trigger: Configure the web UI without Telegram credentials.
- Workaround: Provide dummy Telegram env vars, or run with real Telegram credentials even when using only the web UI.

**Claude resume options are not exposed consistently:**
- Symptoms: Claude Code sessions do not get the same "existing sessions in this directory" picker as Codex sessions.
- Files: `src/codexbot/bot.py:3344`, `src/codexbot/web/api.py:1308`, `web-ui/src/components/NewSessionDialog.tsx:53`
- Trigger: Select a project directory with Claude history and create a Claude runtime session.
- Workaround: Start a fresh Claude session, or pass a known resume session ID through code paths that already support `resume_session_id`.

**WebSocket client event listeners accumulate across stream lifecycles:**
- Symptoms: `EventStream.stop()` closes the socket but does not remove the `visibilitychange`, `pageshow`, or `focus` handlers registered by `armVisibilityRefresh()`.
- Files: `web-ui/src/ws.ts:46`, `web-ui/src/ws.ts:61`, `web-ui/src/ws.ts:79`
- Trigger: Repeated login/logout or repeated construction of `EventStream` in the same browser page.
- Workaround: Reload the page to clear browser-level listeners.

**Slow web subscribers are silently starved:**
- Symptoms: `EventBus.publish()` removes a full subscriber queue from `_subscribers` without sending a shutdown event or closing the WebSocket.
- Files: `src/codexbot/web/events.py:88`, `src/codexbot/web/api.py:1606`, `tests/codexbot/test_web_events.py:91`
- Trigger: A browser tab stops reading events long enough for its queue to fill.
- Workaround: The user must reconnect or reload; the server does not notify the client that live updates have stopped.

## Security Considerations

**Authenticated web UI is full host control:**
- Risk: A valid web session can create tmux windows in arbitrary directories, send terminal input, open a persistent shell, attach to agent tmux windows, switch git branches, view diffs, upload files, capture screenshots, and trigger self-update.
- Files: `src/codexbot/web/api.py:608`, `src/codexbot/web/api.py:917`, `src/codexbot/web/api.py:958`, `src/codexbot/web/api.py:1038`, `src/codexbot/web/api.py:1112`, `src/codexbot/web/api.py:1334`, `src/codexbot/web/api.py:1369`
- Current mitigation: Password login, optional TOTP, signed HttpOnly cookie, WebSocket origin checks, and conservative defaults for `WEB_UI_HOST`.
- Recommendations: Treat the web UI as an admin console. Keep `WEB_UI_HOST=127.0.0.1` unless behind a trusted reverse proxy or VPN. Add config switches for terminal shell and self-update, and document that no per-session or per-directory authorization exists.

**TOTP enrollment secret is logged:**
- Risk: On first web TOTP enrollment, startup logs include the ASCII QR, `otpauth://` URI, and manual entry secret.
- Files: `src/codexbot/web/server.py:107`, `src/codexbot/web/server.py:127`, `src/codexbot/config.py:166`
- Current mitigation: The secret file is persisted with `chmod(0o600)`.
- Recommendations: Do not log the manual secret in long-lived launchd/Docker logs. Prefer a one-shot enrollment command or a local-only endpoint that clears after first successful enrollment.

**Self-update runs a detached shell command from the web API:**
- Risk: `/api/update/run` starts `sh -c "git pull --ff-only origin main && ./scripts/install_macos_launchd.sh"` with no response log, no second server-side confirmation, and auto-update enabled by default.
- Files: `src/codexbot/web/api.py:1334`, `src/codexbot/web/api.py:1352`, `src/codexbot/web/update_checker.py:21`, `scripts/install_macos_launchd.sh`
- Current mitigation: Requires web auth and refuses a dirty working tree.
- Recommendations: Gate update execution behind an explicit `CODEXBOT_AUTO_UPDATE=true` plus a separate `CODEXBOT_ALLOW_WEB_UPDATE_RUN=true`, record update logs under `~/.codexbot/logs`, and return an operation ID that the UI can poll.

**Directory browsing has no root sandbox:**
- Risk: Authenticated users can navigate from the starting directory to filesystem root and create sessions in any readable directory.
- Files: `src/codexbot/web/api.py:1286`, `src/codexbot/handlers/directory_browser.py:143`, `src/codexbot/bot.py:3264`
- Current mitigation: Hidden directories are omitted unless `CODEXBOT_SHOW_HIDDEN_DIRS=true`; authentication is required.
- Recommendations: Add optional `CODEXBOT_PROJECT_ROOTS` allowlist enforcement shared by Telegram and web directory browsers.

## Performance Bottlenecks

**Transcript indexing scans the full Codex sessions tree:**
- Problem: `_refresh_sessions_index()` walks `config.codex_sessions_path.rglob("*.jsonl")` and stats every transcript on refresh.
- Files: `src/codexbot/session.py:709`, `src/codexbot/session.py:730`, `src/codexbot/session_monitor.py:649`, `src/codexbot/web/api.py:569`
- Cause: The index is rebuilt from filesystem scans; cache entries avoid reparsing unchanged headers but not the directory walk/stat pass.
- Improvement path: Maintain an incremental index keyed by date directory and mtime, watch known active transcript paths directly, and only run full discovery for explicit resume/history lookups.

**SPA bundle is large and loaded eagerly:**
- Problem: `pnpm --dir web-ui build` emits a single `web-ui/dist/assets/index-*.js` bundle at about 1.39 MB minified / 412 KB gzip and Vite warns about chunks larger than 500 KB.
- Files: `web-ui/package.json:7`, `web-ui/vite.config.ts:18`, `web-ui/src/App.tsx:14`, `web-ui/src/components/TerminalPanel.tsx:3`, `web-ui/src/components/OfficePanel.tsx`
- Cause: Terminal, office visualization, markdown, xterm, and panels are imported eagerly from `web-ui/src/App.tsx`.
- Improvement path: Dynamically import `TerminalPanel`, `OfficePanel`, `DiffPanel`, and screenshot/update modal code paths; add `manualChunks` for heavy vendor libraries.

**Pane streaming polls every tracked window while any web subscriber exists:**
- Problem: `stream_pane_loop()` samples each `session_manager.window_states` entry every 0.3s, performing tmux window lookup and pane capture.
- Files: `src/codexbot/web/streaming.py:25`, `src/codexbot/web/streaming.py:91`, `src/codexbot/web/streaming.py:112`, `src/codexbot/tmux_manager.py:176`
- Cause: The streamer cannot subscribe to true token events, so it infers in-progress text from visible tmux panes.
- Improvement path: Track active/busy window IDs from transcript/status events and only poll those windows. Reuse a single tmux window snapshot per loop instead of calling `find_window_by_id()` for each tracked state.

**Full transcript histories are cached per session:**
- Problem: The history cache stores all parsed messages for up to `CODEXBOT_HISTORY_CACHE_MAX_SESSIONS` sessions.
- Files: `src/codexbot/session.py:119`, `src/codexbot/session.py:1009`, `src/codexbot/config.py:308`
- Cause: `get_history_snapshot()` returns full parsed histories, then HTTP pagination slices in memory.
- Improvement path: Store offset indexes and parse bounded windows for web pagination. Keep full-history cache optional for small transcripts.

## Fragile Areas

**Session identity rebinding:**
- Files: `src/codexbot/session.py:478`, `src/codexbot/session.py:558`, `src/codexbot/session.py:620`, `src/codexbot/session.py:1078`
- Why fragile: Window-to-session mapping depends on tmux window IDs, cwd normalization, transcript mtime, excluded session IDs, `/status` probing, and special handling for `/clear`, `/new`, `/resume`, Codex, and Claude.
- Safe modification: Add focused tests in `tests/codexbot/test_session.py` for every new runtime transition. Keep routing keyed by tmux window IDs and avoid name-based routing except startup re-resolution.
- Test coverage: Good unit coverage exists in `tests/codexbot/test_session.py`, but live tmux and real transcript writers are not exercised by the standard unit tests.

**Telegram message queue correctness:**
- Files: `src/codexbot/handlers/message_queue.py:91`, `src/codexbot/handlers/message_queue.py:177`, `src/codexbot/handlers/message_queue.py:360`, `src/codexbot/handlers/message_queue.py:642`
- Why fragile: Queue draining/refilling manually compensates `task_done()`, content/completion tasks have different pressure policies, and status conversion edits prior Telegram messages in place.
- Safe modification: Preserve FIFO semantics per `(user_id, thread_id)` lane. Extend `tests/codexbot/handlers/test_message_queue.py` before changing queue inspection, merge, retry, or completion dedupe logic.
- Test coverage: Queue unit tests exist, but Telegram API transport behavior is mocked.

**Embedded terminal WebSocket lifecycle:**
- Files: `src/codexbot/web/api.py:1369`, `src/codexbot/web/api.py:1439`, `src/codexbot/web/api.py:1537`, `src/codexbot/web/api.py:1557`, `web-ui/src/components/TerminalPanel.tsx:143`
- Why fragile: The route forks a PTY inside a FastAPI WebSocket handler, bridges binary frames to tmux, creates grouped tmux sessions for attach mode, and keeps persistent shell sessions for shell mode.
- Safe modification: Add integration tests around close, reconnect, resize, and kill-session cleanup before altering this path. Keep terminal process cleanup idempotent.
- Test coverage: `tests/codexbot/test_web_api.py` covers helper naming and shell-session creation through mocks; it does not open a real terminal WebSocket.

**Config import side effects:**
- Files: `src/codexbot/config.py:358`, `tests/conftest.py:1`, `tests/codexbot/test_config.py:5`
- Why fragile: `config = Config()` runs at import time, loads `.env`, creates config directories, may generate web secrets, and validates channel env vars before tests can import many modules.
- Safe modification: Keep import-time behavior minimal. Prefer a config factory passed into main/server construction and reserve filesystem creation for startup.
- Test coverage: Config tests exist, but the root test harness forces Telegram variables globally to satisfy import-time validation.

## Scaling Limits

**Per-lane Telegram queue caps at 500 tasks by default:**
- Current capacity: `CODEXBOT_QUEUE_MAXSIZE` defaults to `500`.
- Limit: Content and completion tasks are never dropped; under sustained Telegram slowness, producer paths can await queue space while status updates are dropped.
- Scaling path: Add per-lane metrics, backpressure visibility in `/diag`, and configurable policies for content coalescing under extreme output bursts.

**Web event bus has no replay or explicit disconnect on overflow:**
- Current capacity: `EventBus(queue_size=256)` per subscriber.
- Limit: A slow subscriber loses future events after overflow and does not receive an explicit close frame.
- Scaling path: Send an overflow event before disconnecting, close the WebSocket, and make the browser reconnect and reload history from `/api/sessions/{window_id}/messages`.

**Resume picker returns only ten sessions per cwd:**
- Current capacity: `list_sessions_for_directory()` returns up to 10 sessions.
- Limit: Projects with long-running usage hide older resumable sessions from both Telegram and web.
- Scaling path: Add cursor pagination and search by summary/session ID to `/api/resume-sessions`.

**Single process holds all live state:**
- Current capacity: One bot/web process per `CODEXBOT_DIR`, enforced by `src/codexbot/utils.py:80`.
- Limit: Horizontal scaling is not supported; running multiple instances against one tmux/state directory risks duplicate delivery and split-brain state.
- Scaling path: Keep single-instance semantics explicit, or move queue/session/event state into a shared durable coordinator before attempting multiple workers.

## Dependencies at Risk

**`telegramify-markdown`:**
- Risk: The code imports private APIs and pins `<0.6` because `0.6.x` removed those internals.
- Impact: Security updates or Python compatibility fixes in newer `telegramify-markdown` releases cannot be adopted without rewriting `src/codexbot/markdown_v2.py`.
- Migration plan: Replace private renderer calls with local renderer code and retain table/expandable-quote tests in `tests/codexbot/test_markdown_v2.py`.

**`python-telegram-bot` internals:**
- Risk: Startup mutates private limiter internals through `rate_limiter._base_limiter._level`.
- Impact: A python-telegram-bot or aiolimiter internal change can break startup or silently remove the intended rate-limit warmup.
- Migration plan: Wrap this in a compatibility helper with version-gated tests, or remove the private mutation and rely on public retry/backoff behavior.

**CLI process behavior (`codex`, `claude`, `tmux`):**
- Risk: Session detection and startup prompt automation depend on CLI output, transcript locations, tmux pane command names, and prompt text.
- Impact: Runtime CLI updates can break session detection, prompt auto-advance, or terminal status parsing without Python import/type failures.
- Migration plan: Keep runtime-specific logic under `src/codexbot/runtimes/`, add fixture transcripts for new CLI versions, and use live smoke tests for `tmux_manager.create_window()` and runtime detection.

## Missing Critical Features

**Web-only mode:**
- Problem: The documented and Docker-level web-only channel is blocked by import-time Telegram validation and Telegram-first `main()` startup.
- Blocks: Browser-only deployments, Docker setups without Telegram, and simpler local web testing.

**Runtime-aware resume history:**
- Problem: Resume history is not keyed by runtime and does not index historical Claude project transcripts.
- Blocks: Claude Code parity with Codex for resume workflows.

**Configurable admin surface:**
- Problem: The web UI has no server-side option to disable terminal shell, self-update, directory browsing above approved roots, or git branch switching.
- Blocks: Safer deployment behind shared reverse proxies or on machines where browser access should be narrower than full host control.

**Frontend and browser-flow tests:**
- Problem: The React app has no dedicated unit or browser tests; `web-ui/package.json` only defines `dev`, `build`, and `preview`.
- Blocks: Automated coverage for session creation dialog sequencing, WebSocket reconnect, terminal panel lifecycle, diff panel refresh, upload flow, notifications, and update banner behavior.

## Test Coverage Gaps

**Web API tests are smoke tests with mocked backends:**
- What's not tested: Real `libtmux`, transcript files, git subprocesses, upload bodies, self-update process launch, terminal WebSocket PTY bridging, and static SPA behavior.
- Files: `tests/codexbot/test_web_api.py:1`, `tests/codexbot/test_web_server.py`, `tests/codexbot/test_web_events.py`, `tests/codexbot/test_web_streaming.py`
- Risk: Route shape regressions are caught, but host integration failures can ship until manual use.
- Priority: High

**Web-only configuration path is untested:**
- What's not tested: `Config` accepting `WEB_UI_PASSWORD` without Telegram vars and `main()` starting web without Telegram polling.
- Files: `tests/conftest.py:1`, `tests/codexbot/test_config.py:97`, `tests/integration/test_config_integration.py:14`
- Risk: The current tests assert the Telegram-only requirement and mask the documented web-only path.
- Priority: High

**No frontend test runner:**
- What's not tested: React component state machines, WebSocket reconnect behavior, localStorage cleanup, modal flows, and panel lifecycle.
- Files: `web-ui/package.json:7`, `web-ui/src/App.tsx`, `web-ui/src/ws.ts`, `web-ui/src/components/NewSessionDialog.tsx`, `web-ui/src/components/TerminalPanel.tsx`
- Risk: Browser-only bugs require manual discovery.
- Priority: Medium

**Runtime CLI integration has limited live coverage:**
- What's not tested: Real Codex and Claude process startup, session ID discovery through tmux pane PIDs, prompt auto-advance, and transcript path compatibility with installed CLI versions.
- Files: `src/codexbot/runtimes/codex.py`, `src/codexbot/runtimes/claude.py`, `src/codexbot/tmux_manager.py`, `tests/codexbot/test_session.py`, `tests/codexbot/test_terminal_parser.py`
- Risk: Runtime updates can break core session detection while unit tests continue passing against fixtures and mocks.
- Priority: High

---

*Concerns audit: 2026-05-21*
