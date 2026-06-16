"""Tests for interactive-prompt navigation math.

The Claude/Codex selection pickers wrap and advance one option per Down press,
while Up wraps unpredictably — so option selection navigates forward-only from
the cursor's real position. `_forward_steps` is that pure calculation.
"""

from __future__ import annotations

from codexbot.web.interactive_monitor import _forward_steps


def test_forward_steps_no_move() -> None:
    assert _forward_steps(0, 0, 5) == 0
    assert _forward_steps(3, 3, 5) == 0


def test_forward_steps_downward() -> None:
    assert _forward_steps(0, 1, 5) == 1
    assert _forward_steps(1, 3, 5) == 2
    assert _forward_steps(0, 4, 5) == 4


def test_forward_steps_wraps_forward() -> None:
    # Target above the cursor: wrap past the bottom rather than press Up.
    assert _forward_steps(2, 1, 5) == 4  # 2->3->4->0->1
    assert _forward_steps(4, 0, 5) == 1  # last -> first
    assert _forward_steps(3, 2, 4) == 3  # 3->0->1->2


def test_forward_steps_two_option_menu() -> None:
    assert _forward_steps(0, 1, 2) == 1
    assert _forward_steps(1, 0, 2) == 1
