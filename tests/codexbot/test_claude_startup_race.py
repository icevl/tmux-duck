"""Startup-prompt answers are serialised per window and confirmed before Enter."""

import asyncio
from unittest.mock import patch

import pytest

from codexbot.runtimes import claude as claude_mod
from codexbot.tmux_manager import TmuxWindow

TRUST = """\
 Quick safety check: Is this a project you created or one you trust?
 {no}No, exit
 {yes}Yes, I trust this folder
 Enter to confirm · Esc to cancel
"""


class FakePane:
    """A trust prompt whose cursor follows Up/Down; Enter answers it."""

    def __init__(self) -> None:
        self.cursor = 0  # 0 = "No, exit", 1 = "Yes"
        self.keys: list[str] = []
        self.answered: str | None = None

    def text(self) -> str:
        if self.answered:
            return "> " if self.answered == "yes" else "$ "
        return TRUST.format(
            no="❯ " if self.cursor == 0 else "  ",
            yes="❯ " if self.cursor == 1 else "  ",
        )

    async def capture(self, _wid: str) -> str:
        await asyncio.sleep(0)
        return self.text()

    async def send(self, _wid: str, key: str, **_kw: object) -> bool:
        self.keys.append(key)
        await asyncio.sleep(0)
        if key == "Down":
            self.cursor = (self.cursor + 1) % 2
        elif key == "Up":
            self.cursor = (self.cursor - 1) % 2
        elif key == "Enter":
            self.answered = "yes" if self.cursor == 1 else "no"
        return True


@pytest.fixture(autouse=True)
def _fresh_state(monkeypatch):
    monkeypatch.setattr(claude_mod, "_STARTUP_LOCKS", {})
    monkeypatch.setattr(claude_mod, "_STARTUP_LAST_ACTION", {})
    monkeypatch.setattr(claude_mod, "STARTUP_ACTION_COOLDOWN", 60.0)


def _patched(pane: FakePane):
    window = TmuxWindow(
        window_id="@5", window_name="w", cwd="/tmp", pane_current_command="2.1.283"
    )
    tm = claude_mod.tmux_manager
    return (
        patch.object(tm, "find_window_by_id", return_value=window),
        patch.object(tm, "capture_pane", side_effect=pane.capture),
        patch.object(tm, "send_keys", side_effect=pane.send),
    )


@pytest.mark.asyncio
async def test_concurrent_loops_answer_once_and_trust():
    pane = FakePane()
    a, b, c = _patched(pane)
    with a, b, c:
        await asyncio.gather(
            claude_mod._maybe_advance_startup_prompt("@5"),
            claude_mod._maybe_advance_startup_prompt("@5"),
        )
    assert pane.answered == "yes"
    assert pane.keys == ["Down", "Enter"]


@pytest.mark.asyncio
async def test_no_enter_when_cursor_did_not_reach_yes():
    pane = FakePane()

    async def stuck_send(_wid: str, key: str, **_kw: object) -> bool:
        pane.keys.append(key)  # the TUI ignores the arrow
        if key == "Enter":
            pane.answered = "yes" if pane.cursor == 1 else "no"
        return True

    a, b, _ = _patched(pane)
    with (
        a,
        b,
        patch.object(claude_mod.tmux_manager, "send_keys", side_effect=stuck_send),
    ):
        await claude_mod._maybe_advance_startup_prompt("@5")
    assert pane.answered is None
    assert "Enter" not in pane.keys
