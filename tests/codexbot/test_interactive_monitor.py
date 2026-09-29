"""Tests for interactive-prompt navigation math.

The Claude/Codex selection pickers advance one option per arrow press but wrap
past their ends inconsistently, so option selection moves straight from the
cursor's real position to the target. `_cursor_moves` is that pure calculation.
"""

from __future__ import annotations

from codexbot.web.interactive_monitor import _cursor_moves


def test_no_move() -> None:
    assert _cursor_moves(0, 0) == ("Down", 0)
    assert _cursor_moves(3, 3) == ("Down", 0)


def test_downward() -> None:
    assert _cursor_moves(0, 1) == ("Down", 1)
    assert _cursor_moves(1, 3) == ("Down", 2)
    assert _cursor_moves(0, 4) == ("Down", 4)


def test_upward_never_wraps() -> None:
    assert _cursor_moves(2, 1) == ("Up", 1)
    assert _cursor_moves(4, 0) == ("Up", 4)
    # From "Chat about this" back to an option: Down would not wrap there.
    assert _cursor_moves(5, 1) == ("Up", 4)
