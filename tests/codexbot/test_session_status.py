"""Tests for the server-side SessionStatusTracker state machine."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from codexbot.web.events import EventBus
from codexbot.web.session_status import (
    SessionStatusTracker,
    Status,
    WindowStatus,
)


def _activity(window_id: str, ts: float, **extra: Any) -> dict[str, Any]:
    base = {"type": "message", "window_id": window_id, "role": "assistant", "ts": ts}
    base.update(extra)
    return base


def _completion(window_id: str, ts: float) -> dict[str, Any]:
    return {"type": "completion", "window_id": window_id, "ts": ts}


def _prompt(window_id: str, ts: float, **extra: Any) -> dict[str, Any]:
    base = {"type": "interactive_prompt", "window_id": window_id, "ts": ts}
    base.update(extra)
    return base


def _cleared(window_id: str, ts: float) -> dict[str, Any]:
    return {"type": "interactive_prompt_cleared", "window_id": window_id, "ts": ts}


def _drain(q: "asyncio.Queue[dict[str, Any]]") -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


@pytest.mark.asyncio
async def test_activity_marks_running_and_publishes() -> None:
    bus = EventBus()
    client = bus.subscribe()
    tracker = SessionStatusTracker(bus)

    await tracker._handle(_activity("@1", 100.0))  # noqa: SLF001

    st = tracker.get("@1")
    assert st is not None and st.status is Status.running
    assert st.since == 100.0
    events = _drain(client)
    assert len(events) == 1
    assert events[0]["type"] == "session_status"
    assert events[0]["window_id"] == "@1"
    assert events[0]["status"] == "running"
    assert events[0]["attention"] is False


@pytest.mark.asyncio
async def test_running_then_completion_is_done() -> None:
    bus = EventBus()
    tracker = SessionStatusTracker(bus)
    await tracker._handle(_activity("@1", 100.0))  # noqa: SLF001
    await tracker._handle(_completion("@1", 105.0))  # noqa: SLF001
    assert tracker.get("@1").status is Status.done


@pytest.mark.asyncio
async def test_completion_without_running_stays_idle() -> None:
    # A stray / lagging completion on a window we never saw running must not
    # flip it to "done" (mirrors the client wasBusy gate).
    bus = EventBus()
    tracker = SessionStatusTracker(bus)
    await tracker._handle(_completion("@1", 100.0))  # noqa: SLF001
    assert tracker.get("@1").status is Status.idle


@pytest.mark.asyncio
async def test_interactive_prompt_blocks_with_summary() -> None:
    bus = EventBus()
    tracker = SessionStatusTracker(bus)
    await tracker._handle(_activity("@1", 100.0))  # noqa: SLF001
    await tracker._handle(  # noqa: SLF001
        _prompt("@1", 101.0, ui_name="Permission", content="Allow Edit foo.py?")
    )
    st = tracker.get("@1")
    assert st.status is Status.blocked
    assert st.attention is True
    assert st.prompt_summary == "Permission"


@pytest.mark.asyncio
async def test_prompt_cleared_resumes_running() -> None:
    bus = EventBus()
    tracker = SessionStatusTracker(bus)
    await tracker._handle(_prompt("@1", 100.0, content="choose"))  # noqa: SLF001
    assert tracker.get("@1").status is Status.blocked
    await tracker._handle(_cleared("@1", 101.0))  # noqa: SLF001
    st = tracker.get("@1")
    assert st.status is Status.running
    assert st.prompt_summary is None


@pytest.mark.asyncio
async def test_completion_while_blocked_goes_idle() -> None:
    bus = EventBus()
    tracker = SessionStatusTracker(bus)
    await tracker._handle(_prompt("@1", 100.0, content="choose"))  # noqa: SLF001
    await tracker._handle(_completion("@1", 101.0))  # noqa: SLF001
    assert tracker.get("@1").status is Status.idle


@pytest.mark.asyncio
async def test_activity_while_blocked_does_not_unblock() -> None:
    # Claude redraws its pane while parked on a prompt; that residual activity
    # must not re-arm "running" under the blocked window.
    bus = EventBus()
    tracker = SessionStatusTracker(bus)
    await tracker._handle(_prompt("@1", 100.0, content="choose"))  # noqa: SLF001
    await tracker._handle(_activity("@1", 101.0))  # noqa: SLF001
    assert tracker.get("@1").status is Status.blocked


@pytest.mark.asyncio
async def test_repeated_activity_publishes_once() -> None:
    bus = EventBus()
    client = bus.subscribe()
    tracker = SessionStatusTracker(bus)
    await tracker._handle(_activity("@1", 100.0))  # noqa: SLF001
    await tracker._handle(_activity("@1", 101.0))  # noqa: SLF001
    await tracker._handle(_activity("@1", 102.0))  # noqa: SLF001
    events = [e for e in _drain(client) if e["type"] == "session_status"]
    assert len(events) == 1  # only the idle -> running flip is published
    # but the last activity is tracked for the watchdog
    assert tracker.get("@1").last_activity == 102.0


@pytest.mark.asyncio
async def test_non_agent_message_does_not_run() -> None:
    bus = EventBus()
    tracker = SessionStatusTracker(bus)
    # A user echo with no tool/assistant role is not "the agent working".
    await tracker._handle(  # noqa: SLF001
        {"type": "message", "window_id": "@1", "role": "user", "ts": 100.0}
    )
    assert tracker.get("@1").status is Status.idle


@pytest.mark.asyncio
async def test_watchdog_expires_running_to_done() -> None:
    bus = EventBus()
    tracker = SessionStatusTracker(bus, watchdog_seconds=90.0)
    await tracker._handle(_activity("@1", 100.0))  # noqa: SLF001
    # Not yet expired.
    await tracker._sweep_expired(100.0 + 89.0)  # noqa: SLF001
    assert tracker.get("@1").status is Status.running
    # Past the watchdog window.
    await tracker._sweep_expired(100.0 + 91.0)  # noqa: SLF001
    assert tracker.get("@1").status is Status.done


@pytest.mark.asyncio
async def test_acknowledge_clears_done() -> None:
    bus = EventBus()
    tracker = SessionStatusTracker(bus)
    await tracker._handle(_activity("@1", 100.0))  # noqa: SLF001
    await tracker._handle(_completion("@1", 101.0))  # noqa: SLF001
    assert tracker.get("@1").status is Status.done
    await tracker.acknowledge("@1")
    assert tracker.get("@1").status is Status.idle
    # Acknowledge is a no-op for non-done windows.
    await tracker._handle(_activity("@1", 200.0))  # noqa: SLF001
    await tracker.acknowledge("@1")
    assert tracker.get("@1").status is Status.running


@pytest.mark.asyncio
async def test_events_without_window_id_are_ignored() -> None:
    bus = EventBus()
    tracker = SessionStatusTracker(bus)
    await tracker._handle(_activity("", 100.0))  # noqa: SLF001
    await tracker._handle({"type": "message", "role": "assistant", "ts": 100.0})  # noqa: SLF001
    assert tracker.snapshot() == {}


@pytest.mark.asyncio
async def test_snapshot_is_a_copy() -> None:
    bus = EventBus()
    tracker = SessionStatusTracker(bus)
    await tracker._handle(_activity("@1", 100.0))  # noqa: SLF001
    snap = tracker.snapshot()
    snap.clear()
    assert tracker.get("@1") is not None


def test_window_status_payload_shape() -> None:
    st = WindowStatus(status=Status.blocked, since=12.0, prompt_summary="x")
    payload = st.to_payload()
    assert payload == {
        "status": "blocked",
        "status_since": 12.0,
        "attention": True,
        "prompt_summary": "x",
    }


@pytest.mark.asyncio
async def test_end_to_end_via_running_tracker() -> None:
    # Drive the real consume loop: publish bus events, expect a session_status
    # echo on a client subscriber. Verifies start()/subscribe wiring.
    bus = EventBus()
    client = bus.subscribe()
    tracker = SessionStatusTracker(bus)
    await tracker.start()
    try:
        await bus.publish(_activity("@9", 100.0))

        async def _wait_status() -> dict[str, Any]:
            while True:
                ev = await client.get()
                if ev["type"] == "session_status" and ev["window_id"] == "@9":
                    return ev

        ev = await asyncio.wait_for(_wait_status(), timeout=1.0)
        assert ev["status"] == "running"
        assert tracker.get("@9").status is Status.running
    finally:
        await tracker.stop()


@pytest.mark.asyncio
async def test_internal_subscriber_not_counted_but_receives() -> None:
    bus = EventBus()
    internal = bus.subscribe(internal=True)
    assert bus.subscriber_count == 0  # internal doesn't gate the poll loops
    client = bus.subscribe()
    assert bus.subscriber_count == 1
    await bus.publish({"type": "ping"})
    assert (await asyncio.wait_for(internal.get(), timeout=0.5))["type"] == "ping"
    assert (await asyncio.wait_for(client.get(), timeout=0.5))["type"] == "ping"
    bus.unsubscribe(internal)
    assert bus.subscriber_count == 1
