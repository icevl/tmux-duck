# Testing Patterns

**Analysis Date:** 2026-05-21

## Test Framework

**Runner:**
- Pytest `>=8.0` is configured in `pyproject.toml` and used for all backend tests under `tests/`.
- `pytest-asyncio >=0.24.0` is configured through `asyncio_mode = "auto"` in `pyproject.toml`.
- Test discovery is limited to `tests` through `[tool.pytest.ini_options] testpaths = ["tests"]` in `pyproject.toml`.
- The `integration` marker is declared in `pyproject.toml` and applied in `tests/integration/test_config_integration.py` and `tests/integration/test_monitor_state_integration.py`.

**Assertion Library:**
- Use plain `assert` statements and `pytest.raises`; examples are in `tests/codexbot/test_config.py`, `tests/codexbot/test_web_events.py`, and `tests/codexbot/test_session_monitor.py`.
- Use FastAPI `TestClient` for HTTP assertions in `tests/codexbot/test_web_api.py`.

**Run Commands:**
```bash
uv run pytest                         # Run all backend tests
uv run pytest --tb=short -q           # CI/pre-push backend test command
/tmp/codexbot-venv/bin/pytest -q      # Local AGENTS.md test lane
uv run pytest --cov=codexbot --cov-report=term-missing  # Coverage view
uv run ruff check src/ tests/         # Python lint
uv run ruff format --check src/ tests/ # Python format check
uv run pyright src/codexbot/          # Python type check
pnpm --dir web-ui build               # Frontend typecheck and production build
```

## Test File Organization

**Location:**
- Unit tests live under `tests/codexbot/` and mirror the package under `src/codexbot/`, for example `tests/codexbot/test_session.py` for `src/codexbot/session.py` and `tests/codexbot/test_web_events.py` for `src/codexbot/web/events.py`.
- Handler tests live under `tests/codexbot/handlers/`, mirroring `src/codexbot/handlers/`.
- Integration tests live under `tests/integration/` and are marked with `pytestmark = pytest.mark.integration`.
- Shared backend fixtures live in `tests/conftest.py` and `tests/codexbot/conftest.py`.
- There are no TypeScript test files or frontend test runner config under `web-ui/`; validate frontend changes with `web-ui/package.json` script `build`.

**Naming:**
- Use `test_*.py` filenames for Python tests: `tests/codexbot/test_transcript_parser.py`, `tests/codexbot/test_web_api.py`, and `tests/integration/test_monitor_state_integration.py`.
- Use `Test*` classes to group related behavior when a module has multiple scenarios: `TestConfigValid` in `tests/codexbot/test_config.py`, `TestMessageQueueCompletionOrdering` in `tests/codexbot/handlers/test_message_queue.py`, and `TestReadNewLinesOffsetRecovery` in `tests/codexbot/test_session_monitor.py`.
- Use `test_*` function names that describe the behavior, not the implementation detail alone: `test_completion_task_is_not_merged_and_runs_after_content` in `tests/codexbot/handlers/test_message_queue.py`.

**Structure:**
```text
tests/
├── conftest.py                         # import-time env isolation
├── codexbot/
│   ├── conftest.py                     # factories and pane text fixtures
│   ├── test_config.py                  # unit tests for src/codexbot/config.py
│   ├── test_web_api.py                 # FastAPI smoke and behavior tests
│   └── handlers/
│       └── test_message_queue.py       # handler package tests
└── integration/
    └── test_monitor_state_integration.py # real tmp_path file I/O tests
```

## Test Structure

**Suite Organization:**
```python
import pytest

from codexbot.config import Config


@pytest.fixture
def _base_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "test:token")
    monkeypatch.setenv("ALLOWED_USERS", "12345")
    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))


@pytest.mark.usefixtures("_base_env")
class TestConfigValid:
    def test_valid_config(self):
        cfg = Config()
        assert cfg.telegram_bot_token == "test:token"
```
Pattern source: `tests/codexbot/test_config.py`.

**Patterns:**
- Arrange import-time environment in `tests/conftest.py` before importing `codexbot` modules because `src/codexbot/config.py` creates a module-level `config` singleton.
- Use class-level `@pytest.mark.usefixtures` for repeated setup, as in `tests/codexbot/test_config.py` and `tests/codexbot/handlers/test_interactive_ui.py`.
- Use factory fixtures that return inner `_make()` helpers for structured test data, as in `make_jsonl_entry`, `make_tool_use_block`, and `make_tool_result_block` in `tests/codexbot/conftest.py`.
- Use `tmp_path` for file-system state and avoid writing to real `~/.codexbot/` state paths; examples are in `tests/codexbot/test_utils.py`, `tests/codexbot/test_session_monitor.py`, and `tests/integration/test_monitor_state_integration.py`.
- Use explicit queue cleanup for async global state, especially `await mq.shutdown_workers()` and clearing module dictionaries in `tests/codexbot/handlers/test_message_queue.py`.

## Mocking

**Framework:** `unittest.mock` plus pytest `monkeypatch`

**Patterns:**
```python
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_completion_duplicates_are_filtered_by_session_turn() -> None:
    await mq.shutdown_workers()
    bot = AsyncMock()
    queue = get_or_create_queue(bot, user_id=5)

    with patch(
        "codexbot.handlers.message_queue._process_content_task",
        new_callable=AsyncMock,
    ) as mock_process:
        await enqueue_completion_message(
            bot=bot,
            user_id=5,
            window_id="@5",
            session_id="s1",
            turn_id=11,
            completion_text="done",
        )
        await queue.join()

    assert mock_process.await_count == 1
```
Pattern source: `tests/codexbot/handlers/test_message_queue.py`.

**What to Mock:**
- Mock Telegram bot/message objects with `AsyncMock` and `MagicMock`, as in `tests/codexbot/test_screenshot.py`, `tests/codexbot/test_forward_command.py`, and `tests/codexbot/handlers/test_message_queue.py`.
- Patch module-level singletons at the module under test, for example `codexbot.web.api.tmux_manager` and `codexbot.web.api.session_manager` in `tests/codexbot/test_web_api.py`.
- Patch slow or external async boundaries with `AsyncMock`, such as tmux capture/send calls in `tests/codexbot/handlers/test_status_polling.py` and `tests/codexbot/handlers/test_interactive_ui.py`.
- Patch sleeps in retry tests to keep tests fast: `patch("asyncio.sleep", new=AsyncMock())` in `tests/codexbot/handlers/test_message_queue.py`.
- Use `monkeypatch.setattr` for config flags and singleton attributes when the test needs permanent per-test state, as in `_baseline_config()` in `tests/codexbot/test_web_api.py`.

**What NOT to Mock:**
- Do not mock pure parsers and formatters; assert real output from `src/codexbot/transcript_parser.py`, `src/codexbot/terminal_parser.py`, `src/codexbot/telegram_sender.py`, and `src/codexbot/markdown_v2.py` through tests in `tests/codexbot/test_transcript_parser.py`, `tests/codexbot/test_terminal_parser.py`, `tests/codexbot/test_telegram_sender.py`, and `tests/codexbot/test_markdown_v2.py`.
- Do not mock tmp_path file I/O for persistence behavior; integration-style tests in `tests/integration/test_monitor_state_integration.py` and unit tests in `tests/codexbot/test_utils.py` exercise real temp files.
- Do not call real tmux, Telegram, OpenAI, or filesystem home directories in unit tests; use mocks and temp dirs around `src/codexbot/tmux_manager.py`, `src/codexbot/bot.py`, and `src/codexbot/transcribe.py`.

## Fixtures and Factories

**Test Data:**
```python
@pytest.fixture
def make_jsonl_entry():
    def _make(
        msg_type: str = "assistant",
        content: list | str = "",
        *,
        timestamp: str | None = None,
        session_id: str = "test-session-id",
        cwd: str = "/tmp/test",
    ) -> dict:
        return {
            "type": msg_type,
            "message": {"content": content},
            "sessionId": session_id,
            "cwd": cwd,
        }

    return _make
```
Pattern source: `tests/codexbot/conftest.py`.

**Location:**
- Use `tests/conftest.py` for process-wide import safety and env isolation required by `src/codexbot/config.py`.
- Use `tests/codexbot/conftest.py` for reusable factories and sample terminal panes consumed by parser, status polling, and interactive UI tests.
- Define local fixtures inside a test file when they are only useful for that file, such as `client`, `authed_client`, and `web_password` in `tests/codexbot/test_web_api.py`.
- Use autouse fixtures only for unavoidable global cleanup, as in `_reset_client` in `tests/codexbot/test_transcribe.py`.

## Coverage

**Requirements:** No minimum coverage threshold is enforced.
- Coverage config is present in `pyproject.toml` under `[tool.coverage.run]` and `[tool.coverage.report]`.
- Coverage source is `codexbot`; branch coverage is enabled; missing lines are shown.
- Logger-only lines and `if __name__ == "__main__"` style lines are excluded through `pyproject.toml`.

**View Coverage:**
```bash
uv run pytest --cov=codexbot --cov-report=term-missing
```

## Test Types

**Unit Tests:**
- Parser, formatter, config, session, web auth, event bus, queue, and handler tests live under `tests/codexbot/`.
- Unit tests isolate external systems by patching tmux, Telegram, HTTP clients, and module singletons; examples are `tests/codexbot/test_web_api.py`, `tests/codexbot/test_transcribe.py`, and `tests/codexbot/handlers/test_message_queue.py`.
- Use unit tests for behavior tied to core design constraints from `AGENTS.md`: tmux window IDs, topic routing, per-user queues, runtime adapters, message truncation, transcript indexing, and FastAPI/WebSocket event flow.

**Integration Tests:**
- Integration tests use `pytestmark = pytest.mark.integration` and live under `tests/integration/`.
- The integration scope is local filesystem behavior with `tmp_path`, not real Telegram, tmux, Codex, Claude, or web browser sessions.
- `tests/integration/test_config_integration.py` checks `.env` loading from an isolated temporary cwd.
- `tests/integration/test_monitor_state_integration.py` checks save/load, corrupt file recovery, dirty tracking, and removal behavior for `src/codexbot/monitor_state.py`.

**E2E Tests:**
- Not used. There are no Playwright, Cypress, Selenium, or browser E2E configs in the repo.
- There are no frontend unit tests for `web-ui/src/`. Use `pnpm --dir web-ui build` for frontend validation and add a frontend test runner before adding `*.test.tsx` files.

## Common Patterns

**Async Testing:**
```python
@pytest.mark.asyncio
async def test_publish_assigns_monotonic_sequence() -> None:
    bus = EventBus()
    q = bus.subscribe()

    await bus.publish({"type": "first"})
    await bus.publish({"type": "second"})

    first = await asyncio.wait_for(q.get(), timeout=0.5)
    second = await asyncio.wait_for(q.get(), timeout=0.5)
    assert first["seq"] == 1
    assert second["seq"] == 2
```
Pattern source: `tests/codexbot/test_web_events.py`.

**Error Testing:**
```python
def test_missing_allowed_users(self, monkeypatch):
    monkeypatch.delenv("ALLOWED_USERS", raising=False)
    with pytest.raises(ValueError, match="ALLOWED_USERS"):
        Config()
```
Pattern source: `tests/codexbot/test_config.py`.

**FastAPI Testing:**
```python
@pytest.fixture
def client(web_password: str) -> TestClient:
    bus = EventBus()
    app = create_app(bus)
    return TestClient(app)
```
Pattern source: `tests/codexbot/test_web_api.py`.

**Parameterized Testing:**
- Use `@pytest.mark.parametrize` for parser and formatter matrices in `tests/codexbot/test_transcript_parser.py`, `tests/codexbot/test_terminal_parser.py`, and `tests/codexbot/test_telegram_sender.py`.
- Keep table cases small and explicit; put complex reusable data in fixtures from `tests/codexbot/conftest.py`.

**State Cleanup:**
- Clear or reset module-level state when testing global queues, registries, or caches: `tests/codexbot/handlers/test_message_queue.py`, `tests/codexbot/handlers/test_interactive_ui.py`, and `tests/codexbot/test_skill_hints.py`.
- Prefer `monkeypatch` for environment and singleton cleanup because pytest automatically restores it after each test; examples are in `tests/codexbot/test_config.py` and `tests/codexbot/test_web_api.py`.

---

*Testing analysis: 2026-05-21*
