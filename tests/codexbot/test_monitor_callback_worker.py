"""A slow primary (Telegram) callback must not hold up the monitor loop."""

import asyncio

import pytest

from codexbot.session_monitor import NewMessage, SessionMonitor


@pytest.mark.asyncio
async def test_slow_callback_runs_off_the_loop_in_order(tmp_path):
    monitor = SessionMonitor(projects_path=tmp_path, state_file=tmp_path / "s.json")
    delivered: list[str] = []
    release = asyncio.Event()

    async def slow_callback(msg: NewMessage) -> None:
        await release.wait()
        delivered.append(msg.text)

    monitor.set_message_callback(slow_callback)
    for text in ("a", "b", "c"):
        monitor._ensure_callback_worker()
        # Never blocks, whatever the callback is doing.
        monitor._callback_queue.put_nowait(
            NewMessage(session_id="s", text=text, is_complete=True)
        )
    await asyncio.sleep(0.05)
    assert delivered == []

    release.set()
    await asyncio.wait_for(monitor._callback_queue.join(), timeout=2)
    assert delivered == ["a", "b", "c"]
    await monitor.stop()
