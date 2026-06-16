"""Tests for the Attention Router policy engine."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from codexbot.web.attention import (
    AttentionItem,
    AttentionRouter,
    BrowserNotifier,
    in_quiet_hours,
)
from codexbot.web.events import EventBus


class FakeNotifier:
    def __init__(self) -> None:
        self.items: list[AttentionItem] = []

    async def deliver(self, item: AttentionItem) -> None:
        self.items.append(item)


def _status(window_id: str, status: str, since: float, **extra: Any) -> dict[str, Any]:
    base = {
        "type": "session_status",
        "window_id": window_id,
        "status": status,
        "status_since": since,
        "attention": status == "blocked",
        "prompt_summary": None,
    }
    base.update(extra)
    return base


def _router(notifier: FakeNotifier, **kwargs: Any) -> AttentionRouter:
    # Quiet hours off by default so dispatch tests are deterministic.
    kwargs.setdefault("quiet_hours", None)
    return AttentionRouter(EventBus(), [notifier], **kwargs)


# -- quiet hours (pure) ----------------------------------------------------


def test_in_quiet_hours_wraps_midnight() -> None:
    win = (23, 8)
    assert in_quiet_hours(23, win)
    assert in_quiet_hours(0, win)
    assert in_quiet_hours(7, win)
    assert not in_quiet_hours(8, win)
    assert not in_quiet_hours(12, win)


def test_in_quiet_hours_same_day() -> None:
    win = (9, 17)
    assert not in_quiet_hours(8, win)
    assert in_quiet_hours(9, win)
    assert in_quiet_hours(16, win)
    assert not in_quiet_hours(17, win)


def test_in_quiet_hours_none_and_empty() -> None:
    assert not in_quiet_hours(3, None)
    assert not in_quiet_hours(3, (5, 5))


# -- dispatch policy -------------------------------------------------------


@pytest.mark.asyncio
async def test_blocked_notifies_with_prompt() -> None:
    notifier = FakeNotifier()
    router = _router(notifier)
    await router._handle_status(  # noqa: SLF001
        _status("@1", "blocked", 1000.0, prompt_summary="Allow Edit foo.py?")
    )
    assert len(notifier.items) == 1
    item = notifier.items[0]
    assert item.reason == "blocked"
    assert item.window_id == "@1"
    assert item.body == "Allow Edit foo.py?"


@pytest.mark.asyncio
async def test_blocked_without_prompt_has_default_body() -> None:
    notifier = FakeNotifier()
    router = _router(notifier)
    await router._handle_status(_status("@1", "blocked", 1000.0))  # noqa: SLF001
    assert notifier.items[0].body == "Waiting for your input"


@pytest.mark.asyncio
async def test_long_turn_done_notifies() -> None:
    notifier = FakeNotifier()
    router = _router(notifier, turn_done_min_seconds=60.0)
    await router._handle_status(_status("@1", "running", 1000.0))  # noqa: SLF001
    await router._handle_status(_status("@1", "done", 1100.0))  # noqa: SLF001
    assert len(notifier.items) == 1
    assert notifier.items[0].reason == "turn_done"
    assert notifier.items[0].body == "Finished after 2m"


@pytest.mark.asyncio
async def test_short_turn_done_is_silent() -> None:
    notifier = FakeNotifier()
    router = _router(notifier, turn_done_min_seconds=60.0)
    await router._handle_status(_status("@1", "running", 1000.0))  # noqa: SLF001
    await router._handle_status(_status("@1", "done", 1030.0))  # noqa: SLF001
    assert notifier.items == []


@pytest.mark.asyncio
async def test_done_without_prior_running_is_silent() -> None:
    # An idle window that emits a stray completion (or one whose run start we
    # cleared on idle) has no measurable duration → no ping.
    notifier = FakeNotifier()
    router = _router(notifier)
    await router._handle_status(_status("@1", "running", 1000.0))  # noqa: SLF001
    await router._handle_status(_status("@1", "idle", 1005.0))  # noqa: SLF001
    await router._handle_status(_status("@1", "done", 2000.0))  # noqa: SLF001
    assert notifier.items == []


@pytest.mark.asyncio
async def test_cooldown_collapses_repeats() -> None:
    notifier = FakeNotifier()
    router = _router(notifier, cooldown_seconds=30.0)
    await router._handle_status(_status("@1", "blocked", 1000.0))  # noqa: SLF001
    await router._handle_status(_status("@1", "blocked", 1010.0))  # noqa: SLF001
    assert len(notifier.items) == 1
    # Past the cooldown window it fires again.
    await router._handle_status(_status("@1", "blocked", 1040.0))  # noqa: SLF001
    assert len(notifier.items) == 2


@pytest.mark.asyncio
async def test_quiet_hours_suppress() -> None:
    notifier = FakeNotifier()
    # (0, 24) covers every hour, so any local time is "quiet".
    router = _router(notifier, quiet_hours=(0, 24))
    await router._handle_status(_status("@1", "blocked", 1000.0))  # noqa: SLF001
    assert notifier.items == []


def test_is_active_reflects_notifiers() -> None:
    assert AttentionRouter(EventBus(), []).is_active() is False
    assert AttentionRouter(EventBus(), [FakeNotifier()]).is_active() is True


# -- bus wiring (end to end) ----------------------------------------------


@pytest.mark.asyncio
async def test_browser_notifier_publishes_attention_event() -> None:
    bus = EventBus()
    client = bus.subscribe()
    notifier = BrowserNotifier(bus)
    await notifier.deliver(AttentionItem("@1", "blocked", "repo · claude", "answer me"))
    ev = await asyncio.wait_for(client.get(), timeout=0.5)
    assert ev["type"] == "attention"
    assert ev["window_id"] == "@1"
    assert ev["reason"] == "blocked"
    assert ev["title"] == "repo · claude"
    assert ev["body"] == "answer me"


@pytest.mark.asyncio
async def test_browser_notifier_skips_connector_windows() -> None:
    from codexbot.session import WindowState, session_manager

    bus = EventBus()
    client = bus.subscribe()
    notifier = BrowserNotifier(bus)
    wid = "@browser-notifier-conn-test"
    session_manager.window_states[wid] = WindowState(connector_id="slack")
    try:
        await notifier.deliver(AttentionItem(wid, "blocked", "n", "b"))
        assert client.empty()
    finally:
        session_manager.window_states.pop(wid, None)


@pytest.mark.asyncio
async def test_consume_loop_delivers_and_ignores_other_events() -> None:
    bus = EventBus()
    notifier = FakeNotifier()
    router = AttentionRouter(bus, [notifier], quiet_hours=None)
    await router.start()
    try:
        await bus.publish({"type": "message", "window_id": "@1"})  # ignored
        await bus.publish(_status("@2", "blocked", 1000.0, prompt_summary="hi"))

        async def _wait() -> None:
            while not notifier.items:
                await asyncio.sleep(0.01)

        await asyncio.wait_for(_wait(), timeout=1.0)
        assert len(notifier.items) == 1
        assert notifier.items[0].window_id == "@2"
    finally:
        await router.stop()
