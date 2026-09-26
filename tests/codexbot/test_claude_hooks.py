"""Claude lifecycle hooks: launch wiring, forwarding script, event handling."""

import json
import os
import shlex
import shutil
import subprocess
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from codexbot import claude_hooks
from codexbot.config import config
from codexbot.runtimes.claude import ClaudeRuntime
from codexbot.session import WindowState, session_manager


@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path / "state"))
    monkeypatch.setattr(config, "claude_event_hooks", True)
    monkeypatch.setattr(config, "claude_command", "claude")
    return tmp_path / "state"


def _settings_path(cmd: str) -> Path:
    return Path(shlex.split(cmd.split("--settings ", 1)[1])[0])


class TestLaunchWiring:
    def test_claude_windows_load_event_hooks(self):
        cmd = ClaudeRuntime().build_start_command(None)
        settings = json.loads(_settings_path(cmd).read_text())
        assert set(settings["hooks"]) == {"SessionStart", "Notification"}
        [entry] = settings["hooks"]["SessionStart"]
        script = Path(entry["hooks"][0]["command"].split()[-1])
        assert script.is_file()
        assert "/api/hooks/claude" in script.read_text()

    def test_disabled_by_flag(self, monkeypatch):
        monkeypatch.setattr(config, "claude_event_hooks", False)
        assert "--settings" not in ClaudeRuntime().build_start_command(None)

    def test_respects_settings_in_configured_command(self, monkeypatch):
        monkeypatch.setattr(config, "claude_command", "claude --settings mine.json")
        cmd = ClaudeRuntime().build_start_command("sid-1")
        assert cmd.count("--settings") == 1
        assert "--resume sid-1" in cmd

    def test_connector_settings_keep_write_gate_and_add_event_hooks(self):
        from codexbot.connectors.approval import ensure_claude_hook_settings

        settings = json.loads(Path(ensure_claude_hook_settings()).read_text())
        assert set(settings["hooks"]) == {"SessionStart", "Notification", "PreToolUse"}
        assert "Monitor" in settings["hooks"]["PreToolUse"][0]["matcher"]


class _Capture(BaseHTTPRequestHandler):
    received: list[tuple[dict, dict]] = []

    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers["Content-Length"]))
        _Capture.received.append((dict(self.headers), json.loads(body)))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, *args):
        pass


class TestForwardingScript:
    def test_posts_payload_with_pane_and_secret(self, monkeypatch):
        server = HTTPServer(("127.0.0.1", 0), _Capture)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        monkeypatch.setattr(config, "web_ui_port", server.server_address[1])
        _Capture.received.clear()
        try:
            command = claude_hooks.hook_command()
            result = subprocess.run(
                shlex.split(command),
                input=json.dumps(
                    {"hook_event_name": "SessionStart", "session_id": "s1"}
                ),
                env={**os.environ, "TMUX_PANE": "%7", "TMUX": "/tmp/sock,1,0"},
                capture_output=True,
                text=True,
                timeout=10,
            )
        finally:
            server.shutdown()

        assert result.returncode == 0 and result.stdout == ""
        [(headers, payload)] = _Capture.received
        from codexbot.connectors.approval import approval_secret

        assert headers["X-Hook-Secret"] == approval_secret()
        assert payload == {
            "hook_event_name": "SessionStart",
            "session_id": "s1",
            "tmux_pane": "%7",
            "tmux": "/tmp/sock,1,0",
        }

    def test_silent_when_server_is_down(self, monkeypatch):
        monkeypatch.setattr(config, "web_ui_port", 1)
        result = subprocess.run(
            shlex.split(claude_hooks.hook_command()),
            input="not json",
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert (result.returncode, result.stdout, result.stderr) == (0, "", "")


@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux not installed")
class TestWindowForPane:
    @pytest.fixture
    def tmux_server(self, monkeypatch):
        label = f"codexbot-test-{uuid.uuid4().hex[:8]}"
        monkeypatch.setattr(config, "tmux_session_name", "ours")

        def tmux(*args: str) -> str:
            return subprocess.run(
                ["tmux", "-L", label, *args], capture_output=True, text=True, check=True
            ).stdout.strip()

        tmux("new-session", "-d", "-s", "ours")
        tmux("new-session", "-d", "-s", "theirs")
        try:
            yield tmux
        finally:
            subprocess.run(["tmux", "-L", label, "kill-server"], capture_output=True)

    @pytest.mark.asyncio
    async def test_resolves_pane_of_our_session(self, tmux_server):
        socket = tmux_server("display-message", "-p", "-t", "ours", "#{socket_path}")
        pane = tmux_server("display-message", "-p", "-t", "ours", "#{pane_id}")
        window = tmux_server("display-message", "-p", "-t", "ours", "#{window_id}")
        assert await claude_hooks.window_for_pane(f"{socket},1,0", pane) == window

    @pytest.mark.asyncio
    async def test_ignores_other_sessions(self, tmux_server):
        socket = tmux_server("display-message", "-p", "-t", "theirs", "#{socket_path}")
        pane = tmux_server("display-message", "-p", "-t", "theirs", "#{pane_id}")
        assert await claude_hooks.window_for_pane(f"{socket},1,0", pane) is None

    @pytest.mark.asyncio
    async def test_rejects_non_pane_ids(self):
        assert await claude_hooks.window_for_pane("", "") is None
        assert await claude_hooks.window_for_pane("/tmp/x,1,0", "@1") is None


class TestHandleHookEvent:
    @pytest.fixture
    def window(self, monkeypatch):
        state = WindowState(session_id="old", runtime="claude", cwd="/work")
        monkeypatch.setattr(session_manager, "window_states", {"@7": state})
        monkeypatch.setattr(session_manager, "_save_state", lambda: None)
        monkeypatch.setattr(session_manager, "_session_index", {})
        monkeypatch.setattr(session_manager, "_status_probe_last_by_window", {})
        monkeypatch.setattr(session_manager, "schedule_hint_discovery", AsyncMock())
        monkeypatch.setattr(
            claude_hooks, "window_for_pane", AsyncMock(return_value="@7")
        )
        return state

    @pytest.mark.asyncio
    async def test_session_start_rebinds_window(self, window, tmp_path):
        bus = MagicMock(publish_sessions_changed=AsyncMock())
        transcript = tmp_path / "new.jsonl"
        await claude_hooks.handle_hook_event(
            {
                "hook_event_name": "SessionStart",
                "source": "clear",
                "session_id": "new",
                "transcript_path": str(transcript),
                "tmux_pane": "%1",
            },
            bus=bus,
        )
        assert window.session_id == "new"
        assert session_manager._session_index["new"] == transcript
        bus.publish_sessions_changed.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_same_session_is_a_no_op(self, window):
        bus = MagicMock(publish_sessions_changed=AsyncMock())
        await claude_hooks.handle_hook_event(
            {"hook_event_name": "SessionStart", "session_id": "old", "tmux_pane": "%1"},
            bus=bus,
        )
        bus.publish_sessions_changed.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unmanaged_window_is_ignored(self, window, monkeypatch):
        monkeypatch.setattr(
            claude_hooks, "window_for_pane", AsyncMock(return_value="@99")
        )
        await claude_hooks.handle_hook_event(
            {"hook_event_name": "SessionStart", "session_id": "new", "tmux_pane": "%1"}
        )
        assert window.session_id == "old"

    @pytest.mark.asyncio
    async def test_notification_pokes_interactive_monitor(self, window):
        monitor = MagicMock()
        await claude_hooks.handle_hook_event(
            {
                "hook_event_name": "Notification",
                "notification_type": "permission_prompt",
                "tmux_pane": "%1",
            },
            interactive_monitor=monitor,
        )
        monitor.request_check.assert_called_once_with("@7")


def test_endpoint_requires_secret(monkeypatch):
    from fastapi.testclient import TestClient

    from codexbot.connectors.approval import approval_secret
    from codexbot.web.api import create_app
    from codexbot.web.events import EventBus

    handled = AsyncMock()
    monkeypatch.setattr(claude_hooks, "handle_hook_event", handled)
    client = TestClient(create_app(EventBus()))

    assert client.post("/api/hooks/claude", json={}).status_code == 403
    r = client.post(
        "/api/hooks/claude",
        json={"hook_event_name": "Notification"},
        headers={"X-Hook-Secret": approval_secret()},
    )
    assert r.status_code == 200
    handled.assert_awaited_once()
