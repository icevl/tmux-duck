# AGENTS.md

Codi is a self-hosted bridge between Codex / Claude Code sessions running in tmux and two front-ends — a browser SPA and a Telegram bot — kept in sync.

## Common Commands

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run pyright src/codexbot/
/tmp/codexbot-venv/bin/pytest -q
./scripts/restart.sh
```

## Core Design Constraints

- 1 session = 1 tmux window. Telegram topic and web window both bind to the same tmux window.
- Routing is keyed by tmux window IDs (`@12`), not names.
- Telegram is topic-only; no non-topic fallback logic.
- Multi-runtime: Codex and Claude Code adapters under `src/codexbot/runtimes/`.
- Message truncation happens only at the Telegram send layer.
- Session detection is automatic: `/status` probing + transcript indexing under `~/.codex/sessions` and `~/.claude/projects`.
- Per-user message queue preserves ordering and merges updates safely.
- Web channel uses FastAPI + WebSocket event bus shared with the Telegram path.

## Configuration

- Default state dir: `~/.codexbot/` (override `CODEXBOT_DIR`). Env-var names keep the legacy `CODEXBOT_*` prefix.
- State files: `state.json`, `monitor_state.json`, `web_ui_secret`, `web_ui_totp_secret`.
- Required env vars depend on the enabled channel: Telegram needs `TELEGRAM_BOT_TOKEN` + `ALLOWED_USERS`; web needs `WEB_UI_PASSWORD`.
- Runtime startup overrides: `CODEX_COMMAND`, `CLAUDE_COMMAND`.

<!-- GSD:project-start source:.planning/PROJECT.md -->

## Current GSD Project

Active project: **Codi Session Search**.

Core value: users can quickly locate active Codex and Claude sessions by exact
terms and meaning while Codi stays responsive during startup, async backfill,
live indexing, and normal Web UI/Telegram delivery.

Important constraints for this project:

- Search v1 is limited to currently open tmux-backed sessions.
- Search routing still uses current tmux window IDs; indexed row identity comes
  from transcript provenance, not display names or mutable window metadata.
- Transcript JSONL/session state remains authoritative. The search index is a
  derived, rebuildable cache.
- Embedding, LanceDB writes, backfill, query execution, and index maintenance
  must stay outside the main FastAPI/WebSocket/Telegram hot path.
- Live indexing batches should flush at 32 queued items or 60 seconds.

Planning artifacts:

- `.planning/PROJECT.md`
- `.planning/REQUIREMENTS.md`
- `.planning/ROADMAP.md`
- `.planning/STATE.md`
- `.planning/research/`

Current next step: plan Phase 1, **Search Contract and Status Surface**.

<!-- GSD:project-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

For planned feature work, keep GSD artifacts and execution in sync.

Use these entry points:

- `$gsd-plan-phase 1` to create the executable plan for the current phase.
- `$gsd-execute-phase 1` after the plan is approved or when executing a planned
  phase.
- `$gsd-quick` for small fixes, docs, and ad-hoc tasks.
- `$gsd-debug` for focused investigation and bug fixing.

Do not bypass the planning artifacts for session-search implementation unless
the user explicitly asks to skip GSD for a specific change.

<!-- GSD:workflow-end -->
