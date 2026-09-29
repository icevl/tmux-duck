"""Model switching: catalog, Claude slash commands, Codex relaunch."""

import json
from unittest.mock import AsyncMock, patch

import pytest

from codexbot import model_switch
from codexbot.model_switch import (
    ModelSwitchError,
    codex_restart_command,
    model_catalog,
    switch_model,
)
from codexbot.tmux_manager import TmuxWindow


def _window(command: str) -> TmuxWindow:
    return TmuxWindow(
        window_id="@3", window_name="w", cwd="/tmp", pane_current_command=command
    )


class TestCatalog:
    def test_claude_offers_aliases_without_restart(self):
        catalog = model_catalog("claude")
        ids = [m["id"] for m in catalog["models"]]
        assert "claude-opus-5-5[1m]" in ids and "claude-sonnet-5" in ids
        assert catalog["restarts"] is False

    def test_codex_reads_listed_models_from_cache(self, tmp_path, monkeypatch):
        cache = tmp_path / "models_cache.json"
        cache.write_text(
            json.dumps(
                {
                    "models": [
                        {
                            "slug": "gpt-5.5",
                            "display_name": "GPT-5.5",
                            "visibility": "list",
                            "supported_reasoning_levels": [
                                {"effort": "low"},
                                {"effort": "xhigh"},
                            ],
                        },
                        {"slug": "codex-auto-review", "visibility": "hide"},
                    ]
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(model_switch, "_codex_models_cache_path", lambda: cache)
        catalog = model_catalog("codex")
        assert catalog["models"] == [
            {"id": "gpt-5.5", "label": "GPT-5.5", "efforts": ["low", "xhigh"]}
        ]
        assert catalog["restarts"] is True

    def test_codex_falls_back_without_cache(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            model_switch, "_codex_models_cache_path", lambda: tmp_path / "missing"
        )
        ids = [m["id"] for m in model_catalog("codex")["models"]]
        assert ids == [i for i, _ in model_switch.CODEX_FALLBACK_MODELS]


class TestCodexRestartCommand:
    def test_resumes_with_model_and_effort(self, monkeypatch):
        monkeypatch.setattr(
            model_switch.config, "codex_command", "codex --no-alt-screen"
        )
        assert codex_restart_command("sid-1", "gpt-5.5", "high") == (
            "codex --no-alt-screen resume sid-1 -m gpt-5.5 "
            "-c model_reasoning_effort=high"
        )


class TestSwitch:
    @pytest.mark.asyncio
    async def test_rejects_unsafe_values(self):
        with pytest.raises(ModelSwitchError):
            await switch_model("@3", "claude", None, "opus; rm -rf ~", None)
        with pytest.raises(ModelSwitchError):
            await switch_model("@3", "claude", None, None, None)

    @pytest.mark.asyncio
    async def test_claude_sends_model_then_effort(self, monkeypatch):
        send = AsyncMock(return_value=True)
        monkeypatch.setattr(model_switch.tmux_manager, "send_keys", send)
        monkeypatch.setattr(model_switch, "CLAUDE_COMMAND_GAP", 0)
        await switch_model("@3", "claude", "s", "sonnet", "high")
        assert [c.args for c in send.await_args_list] == [
            ("@3", "/model sonnet"),
            ("@3", "/effort high"),
        ]

    @pytest.mark.asyncio
    async def test_codex_quits_then_relaunches(self, monkeypatch):
        monkeypatch.setattr(model_switch.config, "codex_command", "codex")
        panes = iter(["codex", "zsh"])
        find = AsyncMock(side_effect=lambda _wid: _window(next(panes)))
        send = AsyncMock(return_value=True)
        typed = AsyncMock(return_value=True)
        tm = model_switch.tmux_manager
        with (
            patch.object(tm, "find_window_by_id", find),
            patch.object(tm, "send_keys", send),
            patch.object(tm, "type_start_command", typed),
        ):
            await switch_model("@3", "codex", "sid-1", "gpt-5.5", "low")
        assert send.await_args_list[0].args == ("@3", "/quit")
        typed.assert_awaited_once()
        window_id, cmd, runtime = typed.await_args.args
        assert (window_id, cmd) == (
            "@3",
            "codex resume sid-1 -m gpt-5.5 -c model_reasoning_effort=low",
        )
        # The relaunch gets the startup watcher (Codex's folder-trust prompt).
        assert runtime.name == "codex"

    @pytest.mark.asyncio
    async def test_codex_needs_a_session_id(self):
        with pytest.raises(ModelSwitchError):
            await switch_model("@3", "codex", None, "gpt-5.5", None)

    @pytest.mark.asyncio
    async def test_codex_that_never_exits_is_not_relaunched(self, monkeypatch):
        monkeypatch.setattr(model_switch, "CODEX_EXIT_TIMEOUT", 0.1)
        tm = model_switch.tmux_manager
        typed = AsyncMock(return_value=True)
        with (
            patch.object(
                tm, "find_window_by_id", AsyncMock(return_value=_window("codex"))
            ),
            patch.object(tm, "send_keys", AsyncMock(return_value=True)),
            patch.object(tm, "type_start_command", typed),
            pytest.raises(ModelSwitchError),
        ):
            await switch_model("@3", "codex", "sid-1", "gpt-5.5", None)
        typed.assert_not_awaited()
