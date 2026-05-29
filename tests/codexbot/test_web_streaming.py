"""Tests for the live pane streaming extractor."""

import asyncio
import types

import pytest

from codexbot.web import streaming as streaming_mod
from codexbot.web.events import EventBus
from codexbot.web.streaming import _extract_stream_body, stream_pane_loop


def test_extract_drops_chrome_and_status() -> None:
    pane = (
        "Some context\n"
        "\n"
        "> what's the weather in Tokyo\n"
        "\n"
        "Looking up Tokyo weather…\n"
        "It's 18C and partly cloudy.\n"
        "\n"
        "·  Working… (esc to interrupt)\n"
        "────────────────────────────────────────────\n"
        "  ❯\n"
        "────────────────────────────────────────────\n"
        "  [Opus] Context: 34%\n"
        "  ⏵⏵ bypass permissions\n"
    )
    body = _extract_stream_body(pane)
    assert "Looking up Tokyo weather" in body
    assert "18C and partly cloudy" in body
    assert "esc to interrupt" not in body  # spinner line stripped
    assert "what's the weather" not in body  # user echo stripped
    assert "Context: 34%" not in body  # chrome stripped


def test_extract_returns_empty_when_no_body() -> None:
    pane = (
        "> hi\n"
        "\n"
        "·  Working… (esc to interrupt)\n"
        "────────────────────────────────────────────\n"
        "  ❯\n"
    )
    assert _extract_stream_body(pane) == ""


def test_extract_strips_ansi() -> None:
    pane = "> ask\n\n\x1b[31mhello\x1b[0m there"
    body = _extract_stream_body(pane)
    assert body == "hello there"


def test_extract_no_user_echo_keeps_whole_body() -> None:
    pane = "First assistant line\nsecond line"
    body = _extract_stream_body(pane)
    assert "First assistant line" in body
    assert "second line" in body


def _install_fake_pane(monkeypatch, *, runtime: str, pane: str) -> None:
    """Wire stream_pane_loop's session/tmux deps to a single fake window."""
    ws = types.SimpleNamespace(session_id="sess-1", runtime=runtime)
    fake_session_manager = types.SimpleNamespace(
        window_states={"@1": ws},
    )
    monkeypatch.setattr(streaming_mod, "session_manager", fake_session_manager)

    async def fake_find_window_by_id(window_id):
        return types.SimpleNamespace(window_id=window_id)

    async def fake_capture_pane(window_id):
        return pane

    fake_tmux = types.SimpleNamespace(
        find_window_by_id=fake_find_window_by_id,
        capture_pane=fake_capture_pane,
    )
    monkeypatch.setattr(streaming_mod, "tmux_manager", fake_tmux)


async def _run_loop_once(bus: EventBus) -> list[dict]:
    """Run the pane loop briefly, then cancel; return published events."""
    q = bus.subscribe()
    task = asyncio.create_task(stream_pane_loop(bus, poll_interval=0.01))
    await asyncio.sleep(0.06)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    events = []
    while not q.empty():
        events.append(q.get_nowait())
    return events


@pytest.mark.asyncio
async def test_interactive_prompt_pane_does_not_stream(monkeypatch) -> None:
    # A Codex AskUserQuestion prompt in the pane: its footer carries
    # "esc to interrupt" but the agent is idle-waiting, so the loop must NOT
    # publish a 'stream' event (which would re-arm the busy watchdog forever).
    pane = (
        "Question 1/1\n"
        "  Which option?\n"
        "  ◯ Option A\n"
        "  ◉ Option B\n"
        "  tab to add notes | enter to submit answer | esc to interrupt\n"
    )
    bus = EventBus()
    _install_fake_pane(monkeypatch, runtime="codex", pane=pane)
    events = await _run_loop_once(bus)
    assert all(e["type"] != "stream" for e in events)


@pytest.mark.asyncio
async def test_working_pane_streams(monkeypatch) -> None:
    # Positive control: a genuinely working pane still streams.
    pane = (
        "> do the thing\n"
        "\n"
        "Working on it, here is some output.\n"
        "·  Working… (esc to interrupt)\n"
        "────────────────────────────────────────────\n"
        "  ❯\n"
        "────────────────────────────────────────────\n"
    )
    bus = EventBus()
    _install_fake_pane(monkeypatch, runtime="codex", pane=pane)
    events = await _run_loop_once(bus)
    assert any(e["type"] == "stream" for e in events)
