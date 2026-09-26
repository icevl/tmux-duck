"""Account profiles: isolation, launch wiring, login status and sign-in flow."""

import asyncio
import json
import stat
import sys
import textwrap
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from codexbot import accounts
from codexbot.accounts import (
    AccountManager,
    LoginFlow,
    parse_claude_status,
    parse_codex_status,
)
from codexbot.config import config
from codexbot.profiles import ProfileStore, default_profile
from codexbot.runtimes import get_runtime
from codexbot.session import WindowState, claude_transcript_path


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A fake $HOME with a populated ~/.claude, plus an isolated codexbot dir."""
    fake_home = tmp_path / "home"
    claude_dir = fake_home / ".claude"
    (claude_dir / "skills").mkdir(parents=True)
    (claude_dir / "settings.json").write_text('{"theme": "dark"}')
    (fake_home / ".claude.json").write_text(
        json.dumps(
            {
                "hasCompletedOnboarding": True,
                "mcpServers": {"playwright": {"command": "npx"}},
                "oauthAccount": {"emailAddress": "me@example.com"},
                "userID": "secret-ish",
            }
        )
    )
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path / "codexbot"))
    monkeypatch.setattr(config, "claude_projects_path", claude_dir / "projects")
    monkeypatch.setattr(config, "claude_sessions_path", claude_dir / "sessions")
    monkeypatch.setattr(config, "claude_event_hooks", False)
    monkeypatch.setattr(config, "claude_auto_approve_dangerous", False)
    monkeypatch.setattr(config, "claude_command", "claude")
    store = ProfileStore()
    for module in ("profiles", "session", "accounts", "web.api"):
        monkeypatch.setattr(f"codexbot.{module}.profile_store", store)
    return fake_home


class TestProfileStore:
    def test_create_isolates_credentials_and_shares_config(self, home):
        from codexbot import profiles

        profile = profiles.profile_store.create("claude", "Second Account")
        profile_home = Path(profile.home or "")
        assert profile.id == "second-account"
        assert (profile_home / "settings.json").resolve() == (
            home / ".claude" / "settings.json"
        )
        assert (profile_home / "skills").is_symlink()
        assert not (profile_home / "CLAUDE.md").exists()  # absent in ~/.claude
        seeded = json.loads((profile_home / ".claude.json").read_text())
        assert seeded == {
            "hasCompletedOnboarding": True,
            "mcpServers": {"playwright": {"command": "npx"}},
        }
        assert profile.env() == {"CLAUDE_CONFIG_DIR": str(profile_home)}
        assert profile.claude_projects_path == profile_home / "projects"

    def test_persists_and_lists_defaults_first(self, home):
        from codexbot import profiles

        created = profiles.profile_store.create("claude", "Work")
        with pytest.raises(ValueError):
            profiles.profile_store.create("claude", "work")
        again = profiles.profile_store.create("claude", "Work!")
        assert (created.id, again.id) == ("work", again.id)
        assert again.id.startswith("work-")

        reloaded = ProfileStore()
        assert [p.id for p in reloaded.list("claude")] == ["", created.id, again.id]
        assert [p.runtime for p in reloaded.list()][:2] == ["claude", "codex"]
        assert reloaded.get(created.id, "codex") is None
        assert reloaded.resolve("missing", "claude") == default_profile("claude")

    def test_delete_removes_home(self, home):
        from codexbot import profiles

        profile = profiles.profile_store.create("claude", "Temp")
        profiles.profile_store.delete(profile.id)
        assert not Path(profile.home or "").exists()
        assert (home / ".claude" / "settings.json").exists()  # link target kept
        assert ProfileStore().get(profile.id, "claude") is None

    def test_codex_profiles_not_supported_yet(self, home):
        from codexbot import profiles

        with pytest.raises(ValueError):
            profiles.profile_store.create("codex", "Other")


class TestLaunchAndPaths:
    def test_default_profile_launches_unchanged(self, home):
        assert get_runtime("claude").build_start_command(None) == "claude"

    def test_profile_runtime_sets_config_dir(self, home):
        from codexbot import profiles

        profile = profiles.profile_store.create("claude", "Work")
        runtime = get_runtime("claude", profile.id)
        cmd = runtime.build_start_command("sid-1")
        assert cmd == f"CLAUDE_CONFIG_DIR={profile.home} claude --resume sid-1"
        assert get_runtime("codex", profile.id).name == "codex"

    @pytest.mark.asyncio
    async def test_discovery_reads_profile_sessions_dir(self, home, monkeypatch):
        from codexbot import profiles
        from codexbot.runtimes import claude as claude_runtime

        profile = profiles.profile_store.create("claude", "Work")
        sessions_dir = Path(profile.home or "") / "sessions"
        sessions_dir.mkdir()
        seen: list[Path] = []

        def fake_read(pane_pid, cwd, directory, floor, fallback):
            seen.append(directory)
            return "sid-9"

        monkeypatch.setattr(claude_runtime, "_read_claude_session_for_pane", fake_read)
        sid = await get_runtime("claude", profile.id).discover_session_id(
            window_id="@1",
            pane_pid=1,
            cwd="/tmp",
        )
        assert (sid, seen) == ("sid-9", [sessions_dir])

    def test_transcript_path_follows_profile(self, home, tmp_path):
        from codexbot import profiles

        profile = profiles.profile_store.create("claude", "Work")
        default_path = claude_transcript_path("s1", str(tmp_path))
        profile_path = claude_transcript_path("s1", str(tmp_path), profile.id)
        assert default_path is not None and profile_path is not None
        assert default_path.is_relative_to(home / ".claude" / "projects")
        assert profile_path.is_relative_to(Path(profile.home or "") / "projects")

    def test_window_state_round_trips_profile(self):
        state = WindowState(session_id="s", runtime="claude", profile="work")
        assert WindowState.from_dict(state.to_dict()).profile == "work"
        assert "profile" not in WindowState(runtime="claude").to_dict()


class TestStatusParsing:
    def test_claude_json(self):
        status = parse_claude_status(
            json.dumps(
                {
                    "loggedIn": True,
                    "authMethod": "claude.ai",
                    "email": "me@example.com",
                    "subscriptionType": "max",
                }
            )
        )
        assert (status.logged_in, status.email, status.detail) == (
            True,
            "me@example.com",
            "max",
        )
        signed_out = parse_claude_status('{"loggedIn": false, "authMethod": "none"}')
        assert (signed_out.logged_in, signed_out.detail) == (False, None)
        assert parse_claude_status("garbage").logged_in is None

    def test_codex_text(self):
        assert parse_codex_status("Logged in using ChatGPT\n", 0).logged_in is True
        assert parse_codex_status("Not logged in\n", 1).logged_in is False


class TestLoginFlowParsing:
    def test_claude_url_inside_osc8_hyperlink(self):
        url = "https://claude.com/cai/oauth/authorize?code=true&client_id=abc&state=xyz"
        flow = LoginFlow(profile=default_profile("claude"))
        assert flow.absorb(
            "Opening browser to sign in…\r\n"
            f"If the browser didn't open, visit: \x1b]8;;{url}\x07{url}\x1b]8;;\x07\r\n"
            "Paste code here if prompted > "
        )
        assert (flow.state, flow.url) == ("awaiting_code", url)
        assert flow.absorb(
            "Invalid code. Please make sure the full code was copied.\r\n"
        )
        assert (
            flow.message == "Invalid code. Please make sure the full code was copied."
        )

    def test_codex_device_code(self):
        flow = LoginFlow(profile=default_profile("codex"))
        flow.absorb(
            "1. Open this link in your browser and sign in to your account\n"
            "   https://auth.openai.com/codex/device\n\n"
            "2. Enter this one-time code (expires in 15 minutes)\n"
            "   \x1b[94mAB12-CD34\x1b[0m\n"
        )
        assert (flow.state, flow.url, flow.user_code) == (
            "awaiting_browser",
            "https://auth.openai.com/codex/device",
            "AB12-CD34",
        )


FAKE_CLAUDE = textwrap.dedent(
    """\
    #!{python}
    import json, os, sys
    marker = os.path.join(os.environ["CLAUDE_CONFIG_DIR"], "logged-in")
    if sys.argv[1:] == ["auth", "status"]:
        print(json.dumps({{"loggedIn": os.path.exists(marker), "email": "b@example.com"}}))
        sys.exit(0)
    assert sys.stdin.isatty(), "login must run on a tty"
    print("visit: https://claude.com/cai/oauth/authorize?code=true&state=s1", flush=True)
    while True:
        sys.stdout.write("Paste code here if prompted > ")
        sys.stdout.flush()
        code = sys.stdin.readline().strip()
        if code == "good-code":
            open(marker, "w").close()
            print("Login successful.")
            sys.exit(0)
        print("Invalid code. Please make sure the full code was copied.", flush=True)
    """
)


class TestAccountManagerLogin:
    @pytest.fixture
    def fake_cli(self, home, tmp_path, monkeypatch):
        script = tmp_path / "fake-claude"
        script.write_text(FAKE_CLAUDE.format(python=sys.executable))
        script.chmod(script.stat().st_mode | stat.S_IXUSR)
        monkeypatch.setattr(config, "claude_command", str(script))
        return script

    async def _wait(self, predicate, timeout=10.0):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while not predicate():
            assert loop.time() < deadline, "timed out"
            await asyncio.sleep(0.05)

    @pytest.mark.asyncio
    async def test_code_round_trip_signs_in(self, fake_cli):
        from codexbot import profiles

        profile = profiles.profile_store.create("claude", "Second")
        bus = AsyncMock()
        manager = AccountManager()
        manager._bus = bus

        assert (await manager.refresh(profile)).logged_in is False
        flow = await manager.start_login(profile)
        await self._wait(lambda: flow.state == "awaiting_code")
        assert flow.url == "https://claude.com/cai/oauth/authorize?code=true&state=s1"

        await manager.submit_code(profile, "wrong")
        await self._wait(lambda: flow.message is not None)
        assert flow.state == "awaiting_code"

        await manager.submit_code(profile, "good-code")
        await self._wait(lambda: flow.state == "succeeded")
        await self._wait(lambda: manager.status(profile).logged_in is True)
        assert manager.status(profile).email == "b@example.com"
        states = [
            call.args[0].get("state")
            for call in bus.publish.await_args_list
            if call.args[0]["type"] == "account_login"
        ]
        assert states[0] == "starting" and states[-1] == "succeeded"

    @pytest.mark.asyncio
    async def test_cancel_kills_the_cli(self, fake_cli):
        from codexbot import profiles

        profile = profiles.profile_store.create("claude", "Second")
        manager = AccountManager()
        flow = await manager.start_login(profile)
        await self._wait(lambda: flow.state == "awaiting_code")
        await manager.cancel_login(profile)
        assert flow.process is not None
        await asyncio.wait_for(flow.process.wait(), 5)
        assert flow.state == "cancelled"

    @pytest.mark.asyncio
    async def test_missing_cli(self, home, monkeypatch):
        monkeypatch.setattr(config, "claude_command", "/nonexistent/claude")
        manager = AccountManager()
        status = await manager.refresh(default_profile("claude"))
        assert status.logged_in is None
        with pytest.raises(RuntimeError):
            await manager.start_login(default_profile("claude"))


class TestAccountsApi:
    @pytest.fixture
    def client(self, home, monkeypatch):
        from fastapi.testclient import TestClient

        from codexbot.session import session_manager
        from codexbot.web.api import create_app
        from codexbot.web.events import EventBus

        monkeypatch.setattr(accounts.account_manager, "refresh", AsyncMock())
        monkeypatch.setattr(accounts.account_manager, "_statuses", {})
        monkeypatch.setattr(session_manager, "window_states", {})
        monkeypatch.setattr(session_manager, "_save_state", lambda: None)
        from test_web_api import _baseline_config

        _baseline_config(monkeypatch)
        client = TestClient(create_app(EventBus()))
        assert (
            client.post("/api/login", json={"password": "hunter2"}).status_code == 200
        )
        return client

    def test_create_list_delete(self, client):
        r = client.post("/api/accounts", json={"runtime": "claude", "label": "Work"})
        assert r.status_code == 200, r.text
        created = r.json()
        assert (created["id"], created["is_default"]) == ("work", False)

        listed = client.get("/api/accounts").json()
        assert [a["id"] for a in listed["accounts"]] == ["default", "default", "work"]
        assert listed["profile_runtimes"] == ["claude"]

        assert client.delete("/api/accounts/claude/default").status_code == 400
        assert client.delete("/api/accounts/claude/work").status_code == 200
        assert client.delete("/api/accounts/claude/work").status_code == 404

    def test_delete_refuses_account_in_use(self, client):
        from codexbot.session import session_manager

        client.post("/api/accounts", json={"runtime": "claude", "label": "Work"})
        session_manager.window_states["@1"] = WindowState(
            runtime="claude", profile="work"
        )
        assert client.delete("/api/accounts/claude/work").status_code == 409

    def test_create_session_validates_profile(self, client, tmp_path):
        from codexbot.accounts import AccountStatus, account_manager, profile_key

        r = client.post(
            "/api/sessions",
            json={"cwd": str(tmp_path), "runtime": "claude", "profile": "nope"},
        )
        assert r.status_code == 400

        client.post("/api/accounts", json={"runtime": "claude", "label": "Work"})
        profile = accounts.profile_store.get("work", "claude")
        assert profile is not None
        account_manager._statuses[profile_key(profile)] = AccountStatus(logged_in=False)
        r = client.post(
            "/api/sessions",
            json={"cwd": str(tmp_path), "runtime": "claude", "profile": "work"},
        )
        assert r.status_code == 409
        assert "signed out" in r.json()["detail"]
