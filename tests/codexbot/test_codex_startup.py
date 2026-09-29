"""Codex launch-time trust prompt: detection and auto-accept."""

from unittest.mock import AsyncMock, patch

import pytest

from codexbot.runtimes import codex
from codexbot.runtimes.codex import accept_startup_prompts, trust_prompt_keys

TRUST_PANE = """\
> You are in /Volumes/evo/Projects/tunio
  Do you trust the contents of this directory? Working with untrusted
  contents comes with higher risk of prompt injection. Trusting the
  directory allows project-local config, hooks, and exec policies to
  load.
› 1. Yes, continue
  2. No, quit
  Press enter to continue
"""


def test_cursor_on_yes_just_confirms():
    assert trust_prompt_keys(TRUST_PANE) == ["Enter"]


def test_cursor_on_no_moves_up_first():
    pane = TRUST_PANE.replace("› 1. Yes", "  1. Yes").replace("  2. No", "› 2. No")
    assert trust_prompt_keys(pane) == ["Up", "Enter"]


def test_no_prompt():
    assert trust_prompt_keys("› Implement {feature}\n  gpt-5.4 medium") is None


@pytest.mark.asyncio
async def test_watcher_accepts_the_prompt_once_it_appears(monkeypatch):
    monkeypatch.setattr(codex, "STARTUP_POLL_SECONDS", 0)
    panes = iter(["Booting…", TRUST_PANE])
    from codexbot.tmux_manager import tmux_manager

    send = AsyncMock(return_value=True)
    with (
        patch.object(
            tmux_manager, "capture_pane", AsyncMock(side_effect=lambda _w: next(panes))
        ),
        patch.object(tmux_manager, "send_keys", send),
    ):
        assert await accept_startup_prompts("@9") is True
    send.assert_awaited_once_with("@9", "Enter", enter=False, literal=False)


@pytest.mark.asyncio
async def test_watcher_gives_up_without_a_prompt(monkeypatch):
    monkeypatch.setattr(codex, "STARTUP_WATCH_SECONDS", 0.05)
    monkeypatch.setattr(codex, "STARTUP_POLL_SECONDS", 0.01)
    from codexbot.tmux_manager import tmux_manager

    send = AsyncMock(return_value=True)
    with (
        patch.object(tmux_manager, "capture_pane", AsyncMock(return_value="› ready")),
        patch.object(tmux_manager, "send_keys", send),
    ):
        assert await accept_startup_prompts("@9") is False
    send.assert_not_awaited()
