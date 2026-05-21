# Technology Stack

**Analysis Date:** 2026-05-21

## Languages

**Primary:**
- Python 3.12+ - backend package and CLI entry point under `src/codexbot/`; enforced by `pyproject.toml` (`requires-python = ">=3.12"`) and exercised by `.github/workflows/check.yml` on Python 3.12 and 3.13.
- TypeScript ES2022 - browser SPA under `web-ui/src/`, compiled with strict TypeScript settings from `web-ui/tsconfig.json`.

**Secondary:**
- Bash - local operations, Docker entrypoint, and macOS launchd installer in `scripts/restart.sh`, `scripts/install_macos_launchd.sh`, `scripts/uninstall_macos_launchd.sh`, and `docker/entrypoint.sh`.
- CSS - SPA styling in `web-ui/src/styles.css`.
- Dockerfile/YAML - container image and compose service in `Dockerfile` and `docker-compose.yml`.

## Runtime

**Environment:**
- Python 3.12 runtime for packaged app execution. `Dockerfile` uses `python:3.12-slim`; `.github/workflows/check.yml` validates Python 3.12 and 3.13.
- Node.js runtime for building the Vite SPA. `Dockerfile` installs Debian `nodejs`/`npm`; no `.nvmrc` or Node version pin is present.
- tmux is a runtime dependency. Sessions are tmux windows managed by `src/codexbot/tmux_manager.py`; the Docker image installs `tmux`; `scripts/install_macos_launchd.sh` and `docker/entrypoint.sh` fail if `tmux` is not on `PATH`.
- Agent CLIs are runtime dependencies. `Dockerfile` installs `@openai/codex` and `@anthropic-ai/claude-code`; `src/codexbot/runtimes/codex.py` and `src/codexbot/runtimes/claude.py` launch them inside tmux panes.

**Package Manager:**
- Python: `uv` is the development/install tool used by `README.md`, `.github/workflows/check.yml`, and `scripts/install_macos_launchd.sh`.
- Python lockfile: present at `uv.lock`.
- Python build backend: Hatchling via `[build-system]` in `pyproject.toml`.
- Frontend: `pnpm@10.25.0` is pinned in `web-ui/package.json` and installed in `Dockerfile`.
- Frontend lockfile: present at `web-ui/pnpm-lock.yaml`.

## Frameworks

**Core:**
- FastAPI 0.136.1 - HTTP API, WebSocket endpoints, CORS, and static SPA hosting in `src/codexbot/web/api.py`.
- Uvicorn 0.47.0 - embedded ASGI server launched from `src/codexbot/web/server.py`.
- python-telegram-bot 22.7 - Telegram long polling, bot commands, forum-topic handlers, message sending, and global rate limiting in `src/codexbot/bot.py` and `src/codexbot/handlers/`.
- React 18.3.1 - SPA framework for `web-ui/src/App.tsx` and `web-ui/src/components/`.
- Vite 5.4.21 - frontend dev server and production bundler configured in `web-ui/vite.config.ts`.

**Testing:**
- pytest 9.0.3 - backend test runner configured in `pyproject.toml`, with tests under `tests/`.
- pytest-asyncio 1.3.0 - async test support for FastAPI, queues, and monitor code under `tests/codexbot/`.
- pytest-cov 7.1.0 - coverage settings in `pyproject.toml`.
- pyright 1.1.409 - Python type checking command in `.github/workflows/check.yml` and AGENTS instructions.
- TypeScript 5.9.3 - frontend type checking through `pnpm --dir web-ui build`.

**Build/Dev:**
- Ruff 0.15.13 - Python linting and formatting configured through `pyproject.toml`.
- Hatchling - Python wheel build backend declared in `pyproject.toml`.
- Vite React plugin 4.7.0 - React transform in `web-ui/vite.config.ts`.
- Docker - single-image build in `Dockerfile`; compose service in `docker-compose.yml`.
- macOS launchd - local service installer in `scripts/install_macos_launchd.sh`.

## Key Dependencies

**Critical:**
- `python-telegram-bot[rate-limiter]` 22.7 - Telegram Bot API integration, forum topics, message handlers, and `AIORateLimiter` in `src/codexbot/bot.py`.
- `fastapi` 0.136.1 - authenticated REST API, WebSockets, static files, and middleware in `src/codexbot/web/api.py`.
- `uvicorn[standard]` 0.47.0 - embedded web server in `src/codexbot/web/server.py`.
- `libtmux` 0.57.1 - tmux server/window/pane API wrapper in `src/codexbot/tmux_manager.py`.
- `httpx` 0.28.1 - async OpenAI-compatible transcription calls in `src/codexbot/transcribe.py`.
- `aiofiles` 25.1.0 - async transcript and monitor reads in `src/codexbot/session.py` and `src/codexbot/session_monitor.py`.
- `itsdangerous` 2.2.0 - signed web session cookies in `src/codexbot/web/auth.py`.
- `pyotp` 2.9.0 and `qrcode` 8.2 - Web UI TOTP enrollment and verification in `src/codexbot/config.py` and `src/codexbot/web/auth.py`.
- `Pillow` 12.2.0 - screenshot rendering/resizing and Telegram image constraints in `src/codexbot/screenshot.py` and `src/codexbot/bot.py`.
- `telegramify-markdown` 0.5.4 and `mistletoe` 1.4.0 - Telegram MarkdownV2 conversion in `src/codexbot/markdown_v2.py` and `src/codexbot/handlers/message_sender.py`.

**Infrastructure:**
- `python-dotenv` 1.2.2 - `.env` loading from the working directory and `$CODEXBOT_DIR/.env` in `src/codexbot/config.py`.
- `pydantic` 2.13.4 - FastAPI request models in `src/codexbot/web/api.py`.
- `@xterm/xterm` 6.0.0 and `@xterm/addon-fit` 0.11.0 - terminal panel in `web-ui/src/components/TerminalPanel.tsx`.
- `react-markdown` 10.1.0 and `remark-gfm` 4.0.1 - chat markdown rendering in `web-ui/src/components/Markdown.tsx`.
- `react-resizable-panels` 4.11.1 - multi-panel layout in `web-ui/src/App.tsx`.
- `lucide-react` 1.16.0 - SPA icons throughout `web-ui/src/components/`.
- `tunio-player` 1.2.8 - sidebar audio/player component imported by `web-ui/src/components/Sidebar.tsx`; the backend CSP allows `https://*.tunio.ai` in `src/codexbot/web/api.py`.

## Configuration

**Environment:**
- Configuration is centralized in `src/codexbot/config.py` and loaded at import time into the `config` singleton.
- `.env` lookup order is working-directory `.env`, then `$CODEXBOT_DIR/.env`; do not read or log secret values from either file.
- Default state directory is `~/.codexbot`; override with `CODEXBOT_DIR`.
- `TELEGRAM_BOT_TOKEN` and `ALLOWED_USERS` are required by `src/codexbot/config.py`.
- `WEB_UI_PASSWORD` enables the web channel; `WEB_UI_HOST`, `WEB_UI_PORT`, `WEB_UI_SECRET`, `WEB_UI_TOTP_REQUIRED`, `WEB_UI_TOTP_SECRET`, `WEB_UI_TOTP_ISSUER`, `WEB_UI_TOTP_ACCOUNT`, `WEB_UI_COOKIE_SECURE`, and `WEB_UI_ALLOWED_ORIGINS` configure web auth and transport.
- `OPENAI_API_KEY` and optional `OPENAI_BASE_URL` configure voice transcription in `src/codexbot/transcribe.py`.
- `CODEX_COMMAND`, `CLAUDE_COMMAND`, `CODEXBOT_AUTO_APPROVE_DANGEROUS`, and `CLAUDEBOT_AUTO_APPROVE_DANGEROUS` configure runtime launch commands in `src/codexbot/config.py` and `src/codexbot/runtimes/`.
- `CODEXBOT_CODEX_SESSIONS_PATH`, `CODEX_HOME`, `CLAUDEBOT_CLAUDE_SESSIONS_PATH`, and `CLAUDEBOT_CLAUDE_PROJECTS_PATH` configure transcript/session discovery.
- Sensitive environment variables are scrubbed from tmux child processes by `SENSITIVE_ENV_VARS` in `src/codexbot/config.py` and `TmuxManager._scrub_session_env()` in `src/codexbot/tmux_manager.py`.
- `.env.example` is present as a template; use only variable names from source code or documentation and never copy secret values into planning artifacts.

**Build:**
- Backend package metadata and dev tools: `pyproject.toml`.
- Backend dependency lock: `uv.lock`.
- Frontend package metadata: `web-ui/package.json`.
- Frontend dependency lock: `web-ui/pnpm-lock.yaml`.
- Frontend TypeScript config: `web-ui/tsconfig.json`.
- Frontend Vite config: `web-ui/vite.config.ts`.
- Container build: `Dockerfile`.
- Compose service: `docker-compose.yml`.
- GitHub Actions checks: `.github/workflows/check.yml`, `.github/workflows/claude.yml`, `.github/workflows/claude-code-review.yml`.

## Platform Requirements

**Development:**
- Use Python 3.12+ with `uv sync --all-extras` for backend dependencies.
- Run backend with `uv run codexbot` from the repo root.
- Build SPA with `pnpm --dir web-ui install` and `pnpm --dir web-ui build`; dev mode uses Vite on `127.0.0.1:5173` and proxies `/api` to `http://127.0.0.1:8787` in `web-ui/vite.config.ts`.
- Keep `tmux`, `codex`, and/or `claude` on `PATH` before starting the service; `docker/entrypoint.sh` requires at least one of `codex` or `claude`.
- Use `uv run ruff check src/ tests/`, `uv run ruff format --check src/ tests/`, `uv run pyright src/codexbot/`, `uv run pytest -q`, and `pnpm --dir web-ui build` as the primary verification commands.

**Production:**
- Self-hosted process with tmux as the session substrate. `src/codexbot/main.py` enforces a single instance per `CODEXBOT_DIR` through `codexbot.lock`.
- macOS launchd deployment is generated by `scripts/install_macos_launchd.sh`, including web UI build, plist creation, logs under `~/.codexbot/logs`, and `CODEXBOT_DIR` injection.
- Docker deployment uses `Dockerfile`, `docker/entrypoint.sh`, and `docker-compose.yml`; it bind-mounts Codex, Claude, Codi state, and a projects directory.
- The Python backend serves `web-ui/dist/` from `src/codexbot/web/api.py` when present; override the bundle path with `CODEXBOT_WEB_DIST`.

---

*Stack analysis: 2026-05-21*
