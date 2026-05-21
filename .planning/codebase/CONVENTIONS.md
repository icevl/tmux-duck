# Coding Conventions

**Analysis Date:** 2026-05-21

## Naming Patterns

**Files:**
- Use snake_case Python modules under `src/codexbot/`, matching the runtime area: `src/codexbot/session_monitor.py`, `src/codexbot/transcript_parser.py`, `src/codexbot/handlers/message_queue.py`.
- Keep handler-specific tests under the mirrored package path `tests/codexbot/handlers/`, for example `tests/codexbot/handlers/test_message_queue.py`.
- Use PascalCase React component files in `web-ui/src/components/`, for example `web-ui/src/components/ChatView.tsx`, `web-ui/src/components/ConfirmDialog.tsx`, and `web-ui/src/components/TerminalPanel.tsx`.
- Use lower-case TypeScript utility files for non-components, for example `web-ui/src/api.ts`, `web-ui/src/ws.ts`, and `web-ui/src/components/office/engine.ts`.

**Functions:**
- Use snake_case for Python functions and methods: `_build_codex_command()` in `src/codexbot/config.py`, `_queue_key()` in `src/codexbot/handlers/message_queue.py`, and `claude_transcript_path()` in `src/codexbot/session.py`.
- Prefix private implementation helpers with `_` when they are module-internal: `_sniff_image_ext()` in `src/codexbot/web/api.py`, `_safe_answer_callback_query()` in `src/codexbot/bot.py`, and `_read_claude_session_for_pane()` in `src/codexbot/runtimes/claude.py`.
- Use async functions for I/O, subprocess, tmux, Telegram, FastAPI WebSocket, and queue work: `_run_tmux_command()` in `src/codexbot/web/api.py`, `capture_screenshot()` in `src/codexbot/web/screenshot_helper.py`, and `stream_pane_loop()` in `src/codexbot/web/streaming.py`.
- In TypeScript, use camelCase helpers and PascalCase components: `request<T>()` in `web-ui/src/api.ts`, `loadPanelOpenMap()` in `web-ui/src/App.tsx`, and `ConfirmDialog()` in `web-ui/src/components/ConfirmDialog.tsx`.

**Variables:**
- Use UPPER_SNAKE_CASE for constants at module scope: `SENSITIVE_ENV_VARS` in `src/codexbot/config.py`, `MAX_UPLOAD_BYTES` in `src/codexbot/web/api.py`, and `MERGE_MAX_LENGTH` in `src/codexbot/handlers/message_queue.py`.
- Use lower snake_case for Python locals and attributes: `window_states`, `thread_bindings`, and `_history_cache` in `src/codexbot/session.py`.
- Use camelCase for React state variables and API helpers: `totpRequired` in `web-ui/src/components/Login.tsx`, `sort_order` only when mirroring backend JSON in `web-ui/src/api.ts`, and `panelOpenMap` style helpers in `web-ui/src/App.tsx`.
- Preserve backend wire keys when defining TypeScript API interfaces: `window_id`, `session_id`, `sort_order`, and `totp_required` in `web-ui/src/api.ts`.

**Types:**
- Use PascalCase for Python dataclasses and protocol-like abstractions: `WindowState`, `CodexSession`, and `SessionManager` in `src/codexbot/session.py`; `MessageTask` in `src/codexbot/handlers/message_queue.py`; `AgentRuntime` in `src/codexbot/runtimes/base.py`.
- Use frozen dataclasses for immutable registry/config value objects: `SlashCommand` in `src/codexbot/slash_commands.py`, `SkillHint` in `src/codexbot/skill_hints.py`, and `AuthConfig` in `src/codexbot/web/auth.py`.
- Use Pydantic `BaseModel` classes for FastAPI request bodies: `LoginRequest`, `CreateSessionRequest`, and `PatchSessionRequest` in `src/codexbot/web/api.py`.
- Use TypeScript `interface Props` for component props and exported interfaces for API DTOs: `web-ui/src/components/Login.tsx`, `web-ui/src/components/ConfirmDialog.tsx`, and `web-ui/src/api.ts`.

## Code Style

**Formatting:**
- Format Python with Ruff formatter via `uv run ruff format src/ tests/`; the enforced check is `uv run ruff format --check src/ tests/` in `scripts/git-hooks/pre-push` and `.github/workflows/check.yml`.
- Python targets 3.12 syntax and type behavior through `[tool.ruff] target-version = "py312"` and `[tool.black] target-version = ["py312"]` in `pyproject.toml`.
- Use 4-space indentation, type annotations on public functions, and modern union syntax such as `str | None` as seen in `src/codexbot/session.py`, `src/codexbot/web/api.py`, and `src/codexbot/runtimes/base.py`.
- Format TypeScript consistently with the existing Vite/React source: double quotes, semicolons, 2-space indentation, trailing commas in multi-line calls, and JSX props split across lines as in `web-ui/src/components/Login.tsx` and `web-ui/src/components/ConfirmDialog.tsx`.
- There is no Prettier or ESLint config in the repo; do not introduce formatting churn in `web-ui/src/` unless adding the corresponding tool config.

**Linting:**
- Run `uv run ruff check src/ tests/` before completing Python changes; this command is documented in `AGENTS.md`, `scripts/git-hooks/pre-push`, and `.github/workflows/check.yml`.
- Run `uv run pyright src/codexbot/` before completing typed Python changes; this command is documented in `AGENTS.md`, `scripts/git-hooks/pre-push`, and `.github/workflows/check.yml`.
- Run `pnpm --dir web-ui build` or `cd web-ui && pnpm build` for frontend changes; the build script is `tsc --noEmit && vite build` in `web-ui/package.json`.
- Keep TypeScript strict-mode clean under `web-ui/tsconfig.json`, including `strict`, `noImplicitAny`, `noUnusedLocals`, `noUnusedParameters`, and `noFallthroughCasesInSwitch`.

## Import Organization

**Order:**
1. Use `from __future__ import annotations` first when the module needs postponed annotations, as in `src/codexbot/web/api.py`, `src/codexbot/session.py`, and `src/codexbot/runtimes/claude.py`.
2. Put standard library imports next, grouped by module: `asyncio`, `json`, `logging`, `Path`, and `Any` in `src/codexbot/web/api.py`.
3. Put third-party imports after the standard library: `fastapi`, `pydantic`, `telegram`, `PIL`, and `httpx` in `src/codexbot/web/api.py`, `src/codexbot/bot.py`, and `src/codexbot/transcribe.py`.
4. Put package-local imports last and prefer relative imports inside `src/codexbot/`: `from ..session import session_manager` in `src/codexbot/web/api.py`, `from .config import config` in `src/codexbot/session.py`, and `from .message_sender import send_with_fallback` in `src/codexbot/handlers/message_queue.py`.

**Path Aliases:**
- Python tests import installed package paths such as `from codexbot.config import Config` in `tests/codexbot/test_config.py`; keep test imports package-based rather than relative.
- TypeScript uses relative imports only, for example `import { api } from "../api"` in `web-ui/src/components/Login.tsx` and `import { EventStream } from "./ws"` in `web-ui/src/App.tsx`.
- No TypeScript path aliases are configured in `web-ui/tsconfig.json`; do not use alias imports without adding and documenting compiler/bundler support.

## Error Handling

**Patterns:**
- Use explicit validation errors for configuration and parsing: `Config` raises `ValueError` for missing or invalid env vars in `src/codexbot/config.py`, and tests assert these with `pytest.raises` in `tests/codexbot/test_config.py`.
- Translate API validation and domain failures into `HTTPException` with concrete status codes and `detail` strings in `src/codexbot/web/api.py`.
- Treat subprocess, tmux, filesystem, and WebSocket boundaries as failure boundaries: catch `OSError`, `asyncio.TimeoutError`, `FileNotFoundError`, `PermissionError`, and `WebSocketDisconnect` near the boundary in `src/codexbot/web/api.py`, `src/codexbot/web/server.py`, and `src/codexbot/runtimes/claude.py`.
- Preserve cancellation semantics in long-running async loops: `src/codexbot/web/streaming.py` catches `asyncio.CancelledError` separately from generic exceptions.
- Catch broad `Exception` only at integration boundaries where the code logs and continues, and annotate intentional broad catches with `# noqa: BLE001` as in `src/codexbot/slash_commands.py` and `src/codexbot/web/api.py`.
- Do not expose raw user message text in logs. `src/codexbot/bot.py` uses `_log_dispatch_event()` to emit metadata such as `user_id`, `thread_id`, `window_id`, `session_id`, and `message_len`.

## Logging

**Framework:** Python `logging`

**Patterns:**
- Define `logger = logging.getLogger(__name__)` near the top of Python modules: `src/codexbot/config.py`, `src/codexbot/session.py`, `src/codexbot/web/api.py`, and `src/codexbot/handlers/message_queue.py`.
- Use structured, parameterized log messages instead of string interpolation when values are dynamic: `logger.warning("Failed to persist web UI secret: %s", exc)` in `src/codexbot/config.py`.
- Use `logger.info` for lifecycle state, `logger.warning` for recoverable degradation, and `logger.error` for failed user-visible operations; examples are in `src/codexbot/web/server.py`, `src/codexbot/handlers/message_queue.py`, and `src/codexbot/bot.py`.
- Avoid logging secrets or raw user content. Env var names are defined in `SENSITIVE_ENV_VARS` in `src/codexbot/config.py`, and dispatch logging in `src/codexbot/bot.py` records lengths and identifiers rather than message bodies.
- Frontend error handling surfaces user-safe messages through state such as `setError((err as Error).message)` in `web-ui/src/components/Login.tsx`; there is no frontend logging framework.

## Comments

**When to Comment:**
- Use module docstrings for modules with cross-cutting responsibilities: `src/codexbot/bot.py`, `src/codexbot/session.py`, `src/codexbot/web/api.py`, and `src/codexbot/handlers/message_queue.py`.
- Use function or class docstrings for public APIs, dataclasses, and non-obvious helpers: `AgentRuntime` in `src/codexbot/runtimes/base.py`, `WindowState` in `src/codexbot/session.py`, and `_build_claude_command()` in `src/codexbot/config.py`.
- Use inline comments to explain non-obvious invariants, external quirks, and state contracts: queue lane keys in `src/codexbot/handlers/message_queue.py`, upload caps in `src/codexbot/web/api.py`, and office sprite/frame assumptions in `web-ui/src/components/office/engine.ts`.
- Keep comments operationally useful. Avoid comments that restate a single line of code.

**JSDoc/TSDoc:**
- TypeScript uses ordinary `//` comments and interface names rather than JSDoc blocks. Follow the examples in `web-ui/src/api.ts` and `web-ui/src/components/office/engine.ts`.
- Do not add JSDoc-only documentation unless a public frontend API needs explanation that types cannot carry.

## Function Design

**Size:** Use small pure helpers around large workflow modules.
- Large orchestration modules exist in `src/codexbot/bot.py`, `src/codexbot/web/api.py`, `src/codexbot/handlers/message_queue.py`, and `web-ui/src/components/ChatView.tsx`; put new logic into focused helpers before wiring it into these files.
- Keep parser and formatter behavior as pure functions where practical: `src/codexbot/terminal_parser.py`, `src/codexbot/transcript_parser.py`, and `src/codexbot/telegram_sender.py`.

**Parameters:** Prefer explicit typed parameters.
- Use keyword-only arguments for helpers with many optional inputs, as in `_run_tmux_command(args: list[str], *, timeout: float = 3.0)` in `src/codexbot/web/api.py` and `discover_session_id(..., *, window_id, pane_pid, cwd, allow_cwd_fallback)` in `src/codexbot/runtimes/base.py`.
- Use dataclasses or Pydantic models for structured state instead of parallel dictionaries when the shape is stable: `MessageTask` in `src/codexbot/handlers/message_queue.py`, `WindowState` in `src/codexbot/session.py`, and `CreateSessionRequest` in `src/codexbot/web/api.py`.

**Return Values:** Make absence explicit.
- Return `None` for best-effort discovery failures: `claude_transcript_path()` in `src/codexbot/session.py`, `capture_screenshot()` in `src/codexbot/web/screenshot_helper.py`, and `discover_session_id()` in `src/codexbot/runtimes/base.py`.
- Return typed dictionaries and lists for JSON-ready API data: session summaries in `src/codexbot/web/api.py` and transcript messages in `src/codexbot/session.py`.
- Use booleans for command/send success at side-effect boundaries: `pane_command_matches()` in `src/codexbot/runtimes/base.py` and queue/send helpers in `src/codexbot/handlers/message_queue.py`.

## Module Design

**Exports:** Keep domain singletons and factories stable.
- `src/codexbot/config.py` exposes the module singleton `config`; tests that need alternate values instantiate `Config` directly in `tests/codexbot/test_config.py`.
- `src/codexbot/session.py` exposes `session_manager`; web and bot modules import it directly in `src/codexbot/web/api.py` and `src/codexbot/bot.py`.
- `src/codexbot/tmux_manager.py` exposes `tmux_manager`; runtime and API modules import it where tmux side effects are needed.
- `src/codexbot/web/api.py` exposes `create_app()` for both runtime startup and FastAPI tests in `tests/codexbot/test_web_api.py`.

**Barrel Files:** Use sparingly.
- `src/codexbot/runtimes/__init__.py` is the runtime registry/barrel for `CodexRuntime`, `ClaudeRuntime`, `get_runtime()`, and `all_runtimes()`.
- `src/codexbot/web/__init__.py` exports web server lifecycle helpers from `src/codexbot/web/server.py`.
- Avoid adding broad package barrels; import directly from the owning module when there is no existing registry pattern.

**Project Skills:**
- Repo-local skill definitions are not detected. `.codex/` and `.agents/` exist, but there is no `.codex/skills/*/SKILL.md` or `.agents/skills/*/SKILL.md` in this repo.

---

*Convention analysis: 2026-05-21*
