# External Integrations

**Analysis Date:** 2026-05-21

## APIs & External Services

**Messaging:**
- Telegram Bot API - primary chat transport, forum-topic routing, command menus, file downloads, topic create/rename/delete, and outbound assistant notifications.
  - SDK/Client: `python-telegram-bot[rate-limiter]` in `src/codexbot/bot.py`, `src/codexbot/handlers/message_sender.py`, and `src/codexbot/handlers/message_queue.py`.
  - Auth: `TELEGRAM_BOT_TOKEN`.
  - Access control: `ALLOWED_USERS` whitelist enforced by `Config.is_user_allowed()` in `src/codexbot/config.py` and `is_user_allowed()` in `src/codexbot/bot.py`.
  - Transport: long polling via `application.run_polling(allowed_updates=["message", "callback_query"])` in `src/codexbot/main.py`; no Telegram webhook endpoint is implemented.

**AI Runtime CLIs:**
- OpenAI Codex CLI - launched inside tmux windows for Codex sessions.
  - SDK/Client: local `codex` CLI command built by `src/codexbot/runtimes/codex.py`.
  - Auth: local Codex CLI login state under `CODEX_HOME` or default `~/.codex`; Codi intentionally scrubs `OPENAI_API_KEY` and `OPENAI_BASE_URL` from tmux children in `src/codexbot/config.py` and `src/codexbot/tmux_manager.py`.
  - Config: `CODEX_COMMAND`, `CODEXBOT_AUTO_APPROVE_DANGEROUS`, `CODEXBOT_CODEX_SESSIONS_PATH`, `CODEX_HOME`.
- Claude Code CLI - launched inside tmux windows for Claude sessions.
  - SDK/Client: local `claude` CLI command built by `src/codexbot/runtimes/claude.py`.
  - Auth: local Claude Code login/state under `~/.claude`; Codi reads `~/.claude/sessions` and `~/.claude/projects` by default.
  - Config: `CLAUDE_COMMAND`, `CLAUDEBOT_AUTO_APPROVE_DANGEROUS`, `CLAUDEBOT_CLAUDE_SESSIONS_PATH`, `CLAUDEBOT_CLAUDE_PROJECTS_PATH`, `CLAUDEBOT_SESSION_DETECT_TIMEOUT`, `CLAUDEBOT_SESSION_DETECT_INTERVAL`.

**AI APIs:**
- OpenAI-compatible Audio Transcriptions API - optional Telegram voice-message transcription.
  - SDK/Client: direct `httpx.AsyncClient` call in `src/codexbot/transcribe.py`.
  - Endpoint: `{OPENAI_BASE_URL}/audio/transcriptions`, defaulting to `https://api.openai.com/v1/audio/transcriptions`.
  - Model: `gpt-4o-transcribe` in `src/codexbot/transcribe.py`.
  - Auth: `OPENAI_API_KEY`.

**Browser Transport:**
- FastAPI Web UI - REST API and WebSocket transport sharing the Telegram session manager and event bus.
  - SDK/Client: `fetch()` wrappers in `web-ui/src/api.ts`; event WebSocket client in `web-ui/src/ws.ts`; terminal WebSocket client in `web-ui/src/components/TerminalPanel.tsx`.
  - Server: `src/codexbot/web/api.py` creates `/api/*`, `/api/ws`, and `/api/sessions/{window_id}/term`; `src/codexbot/web/server.py` embeds Uvicorn in the bot process.
  - Auth: `WEB_UI_PASSWORD`, signed cookie `codexbot_session`, optional TOTP, and WebSocket Origin checks in `src/codexbot/web/auth.py`.

**Update Checking:**
- GitHub REST API - self-update notification source for the web UI.
  - SDK/Client: `urllib.request` in `src/codexbot/web/update_checker.py`.
  - Endpoint: `https://api.github.com/repos/icevl/codi/commits/main`.
  - Auth: none for runtime polling.
  - Behavior: compares remote `main` SHA with local `git rev-parse HEAD`; publishes `update_available` through `src/codexbot/web/events.py` when the tree is clean.
- GitHub Actions - repository CI and Claude automation.
  - SDK/Client: workflow actions in `.github/workflows/check.yml`, `.github/workflows/claude.yml`, and `.github/workflows/claude-code-review.yml`.
  - Auth: GitHub Actions secrets `CLAUDE_CODE_OAUTH_TOKEN` and `GITHUB_TOKEN` are referenced by workflow files; no secret values are stored in the repo.

**Terminal Multiplexing:**
- tmux - local process/session substrate for every Codex or Claude session.
  - SDK/Client: `libtmux` plus `tmux` subprocess calls in `src/codexbot/tmux_manager.py` and `src/codexbot/web/api.py`.
  - Auth: local OS user permissions; no network auth.
  - Contract: routing uses tmux window IDs such as `@12`; one session maps to one tmux window.

**Frontend Media/CDN Surface:**
- Tunio player/media domains - optional player UI imported by `web-ui/src/components/Sidebar.tsx`.
  - SDK/Client: `tunio-player` package in `web-ui/package.json`.
  - Auth: Not detected in source.
  - Network allowlist: CSP in `src/codexbot/web/api.py` permits `https://*.tunio.ai` for images, media, and connections.

## Data Storage

**Databases:**
- No database server or ORM detected.
  - Connection: Not applicable.
  - Client: Not applicable.

**Local State Files:**
- Codi state directory - `CODEXBOT_DIR` defaults to `~/.codexbot` in `src/codexbot/utils.py`.
  - `state.json`: thread bindings, window state, runtime mapping, display names, pinned flags, and sort order managed by `src/codexbot/session.py`.
  - `monitor_state.json`: session JSONL byte offsets managed by `src/codexbot/monitor_state.py` and `src/codexbot/session_monitor.py`.
  - `web_ui_secret`: cookie signing secret generated/persisted by `src/codexbot/config.py`.
  - `web_ui_totp_secret`: TOTP seed generated/persisted by `src/codexbot/config.py`.
  - `search/`: derived search namespace reserved by `src/codexbot/search/state.py` for generation metadata and future index/queue state; not authoritative and rebuildable from session/transcript sources.
  - `skill_hints.json`: cached Codex skill hints managed by `src/codexbot/skill_hints.py`.
  - `codexbot.lock`: single-instance lock managed by `src/codexbot/main.py` and `src/codexbot/utils.py`.

**Transcript Sources:**
- Codex transcripts - default `~/.codex/sessions`, override with `CODEXBOT_CODEX_SESSIONS_PATH` or `CODEX_HOME`, read by `src/codexbot/session.py` and `src/codexbot/session_monitor.py`.
- Claude session metadata - default `~/.claude/sessions`, override with `CLAUDEBOT_CLAUDE_SESSIONS_PATH`, read by `src/codexbot/runtimes/claude.py`.
- Claude JSONL transcripts - default `~/.claude/projects`, override with `CLAUDEBOT_CLAUDE_PROJECTS_PATH`, resolved by `claude_transcript_path()` in `src/codexbot/session.py`.

**File Storage:**
- Local filesystem only.
- Incoming Telegram images are stored under `$CODEXBOT_DIR/images` by `photo_handler()` in `src/codexbot/bot.py`.
- Web-uploaded images are accepted by `/api/sessions/{window_id}/upload` in `src/codexbot/web/api.py` and forwarded as local file paths to the agent.
- Built SPA assets are served from `web-ui/dist` or `CODEXBOT_WEB_DIST` by `src/codexbot/web/api.py`.

**Caching:**
- In-memory history cache in `SessionManager._history_cache` in `src/codexbot/session.py`, bounded by `CODEXBOT_HISTORY_CACHE_MAX_SESSIONS`.
- In-memory EventBus subscriber queues in `src/codexbot/web/events.py`.
- In-memory Telegram per-user/per-topic message queues in `src/codexbot/handlers/message_queue.py`.
- Persistent transcript offset cache in `monitor_state.json`.

## Authentication & Identity

**Auth Provider:**
- Telegram channel uses Telegram identity plus local `ALLOWED_USERS`.
  - Implementation: every command/message handler checks `config.is_user_allowed()` in `src/codexbot/bot.py`.
- Web UI uses custom password and TOTP authentication.
  - Implementation: `Authenticator` in `src/codexbot/web/auth.py` verifies `WEB_UI_PASSWORD`, optional TOTP from `WEB_UI_TOTP_SECRET`, and mints a signed `codexbot_session` cookie using `itsdangerous.TimestampSigner`.
  - Session lifetime: 30 days from `COOKIE_MAX_AGE_SECONDS` in `src/codexbot/web/auth.py`.
  - WebSocket defense: same-origin or `WEB_UI_ALLOWED_ORIGINS` allowlist checks before accepting `/api/ws` and `/api/sessions/{window_id}/term`.
- Codex/Claude runtime identity is delegated to the local CLI login state.
  - Implementation: `src/codexbot/runtimes/codex.py` and `src/codexbot/runtimes/claude.py` start local CLIs and do not use service API keys directly.

## Monitoring & Observability

**Error Tracking:**
- None detected. No Sentry, OpenTelemetry, Datadog, Prometheus, or hosted error tracking client is present in `pyproject.toml` or `web-ui/package.json`.

**Logs:**
- Python logging is configured in `src/codexbot/main.py`.
- Uvicorn access logs are disabled in `src/codexbot/web/server.py`.
- macOS launchd deployment writes logs under `~/.codexbot/logs` as configured by `scripts/install_macos_launchd.sh`.
- Telegram queue/dispatch diagnostics are retained in memory by `src/codexbot/handlers/message_queue.py` and exposed through the `/diag` Telegram command in `src/codexbot/bot.py`.
- Web clients receive live event stream messages through `src/codexbot/web/events.py` and `/api/ws`.

## CI/CD & Deployment

**Hosting:**
- Self-hosted local process by default.
- macOS launchd service generated by `scripts/install_macos_launchd.sh`.
- Docker image and compose service in `Dockerfile`, `docker/entrypoint.sh`, and `docker-compose.yml`.
- No managed cloud deployment config detected.

**CI Pipeline:**
- GitHub Actions check pipeline in `.github/workflows/check.yml`.
  - Runs on push and pull requests targeting `main`.
  - Matrix: Python 3.12 and 3.13.
  - Commands: `uv sync --all-extras`, `uv run ruff check src/ tests/`, `uv run ruff format --check src/ tests/`, `uv run pyright src/codexbot/`, and `uv run pytest --tb=short -q`.
- Claude issue/comment automation in `.github/workflows/claude.yml`.
- Claude code review automation in `.github/workflows/claude-code-review.yml`.

## Environment Configuration

**Required env vars:**
- `TELEGRAM_BOT_TOKEN` - required by `src/codexbot/config.py`.
- `ALLOWED_USERS` - required by `src/codexbot/config.py`.
- `WEB_UI_PASSWORD` - required to enable the web UI in `src/codexbot/web/server.py`.
- `OPENAI_API_KEY` - required only for Telegram voice transcription in `src/codexbot/bot.py` and `src/codexbot/transcribe.py`.

**Optional env vars:**
- Web transport: `WEB_UI_HOST`, `WEB_UI_PORT`, `WEB_UI_SECRET`, `WEB_UI_TOTP_REQUIRED`, `WEB_UI_TOTP_SECRET`, `WEB_UI_TOTP_ISSUER`, `WEB_UI_TOTP_ACCOUNT`, `WEB_UI_COOKIE_SECURE`, `WEB_UI_ALLOWED_ORIGINS`, `CODEXBOT_WEB_DIST`.
- Runtime/session: `CODEXBOT_DIR`, `TMUX_SESSION_NAME`, `CODEX_COMMAND`, `CLAUDE_COMMAND`, `CODEXBOT_AUTO_APPROVE_DANGEROUS`, `CLAUDEBOT_AUTO_APPROVE_DANGEROUS`, `CODEXBOT_CODEX_SESSIONS_PATH`, `CODEX_HOME`, `CLAUDEBOT_CLAUDE_SESSIONS_PATH`, `CLAUDEBOT_CLAUDE_PROJECTS_PATH`.
- Monitoring/behavior: `MONITOR_POLL_INTERVAL`, `CODEXBOT_STATUS_POLL_INTERVAL`, `CODEXBOT_TOPIC_CHECK_INTERVAL`, `CODEXBOT_QUEUE_MAXSIZE`, `CODEXBOT_QUEUE_DRAIN_TIMEOUT_SECONDS`, `CODEXBOT_HISTORY_CACHE_MAX_SESSIONS`, `CODEXBOT_SESSION_DETECT_TIMEOUT`, `CODEXBOT_SESSION_DETECT_INTERVAL`, `CODEXBOT_SESSION_STALE_AFTER_SECONDS`, `CODEXBOT_STATUS_PROBE_MIN_INTERVAL_SECONDS`, `CODEXBOT_MONITOR_NEW_SESSION_TAIL_BYTES`, `CODEXBOT_SHOW_HIDDEN_DIRS`, `CODEXBOT_LOG_LEVEL`, `CODEXBOT_AUTO_UPDATE`.
- OpenAI-compatible transcription: `OPENAI_BASE_URL`.
- Docker compose host mount: `CODI_PROJECTS_DIR`.

**Secrets location:**
- Runtime secrets are environment variables or `$CODEXBOT_DIR/.env`; source code reads them through `src/codexbot/config.py`.
- Generated web secrets live in `$CODEXBOT_DIR/web_ui_secret` and `$CODEXBOT_DIR/web_ui_totp_secret`.
- GitHub Actions secrets are referenced by `.github/workflows/claude.yml` and `.github/workflows/claude-code-review.yml`.
- `.env.example` exists as a template; secret values must not be copied into docs or logs.

## Webhooks & Callbacks

**Incoming:**
- Telegram: no webhook. `src/codexbot/main.py` uses long polling for `message` and `callback_query` updates.
- Web UI REST API: `/api/login`, `/api/logout`, `/api/me`, `/api/sessions`, `/api/sessions/{window_id}/messages`, `/api/sessions/{window_id}/text`, `/api/sessions/{window_id}/keys`, `/api/sessions/{window_id}/command`, `/api/sessions/{window_id}/screenshot.png`, `/api/sessions/{window_id}/upload`, `/api/directories`, `/api/resume-sessions`, `/api/runtimes`, `/api/skills`, `/api/skill-hints`, `/api/slash-commands`, `/api/office/state`, and `/api/update/*` in `src/codexbot/web/api.py`.
- Web UI WebSockets: `/api/ws` event stream and `/api/sessions/{window_id}/term` terminal stream in `src/codexbot/web/api.py`.
- GitHub Actions: repository events trigger workflows in `.github/workflows/check.yml`, `.github/workflows/claude.yml`, and `.github/workflows/claude-code-review.yml`.

**Outgoing:**
- Telegram Bot API calls from `src/codexbot/bot.py`, `src/codexbot/handlers/message_sender.py`, and `src/codexbot/handlers/message_queue.py`.
- OpenAI-compatible transcription POST from `src/codexbot/transcribe.py`.
- GitHub commits API polling from `src/codexbot/web/update_checker.py`.
- Local `git pull --ff-only origin main && ./scripts/install_macos_launchd.sh` self-update subprocess from `/api/update/run` in `src/codexbot/web/api.py`.
- Local `tmux` subprocesses and libtmux calls from `src/codexbot/tmux_manager.py` and terminal WebSocket code in `src/codexbot/web/api.py`.

---

*Integration audit: 2026-05-21*
