"""Push search index status onto the WebSocket bus.

The search worker runs as a separate process and only updates
`worker_status.json` between coarse-grained tasks. The web UI footer wants a
live picture (initial backfill in progress, queue draining, transient stale
worker), so this loop polls `search_client.get_status()` and publishes a
`search_status` event whenever the visible signature changes — plus a
periodic heartbeat so freshly-connected clients see something within a few
seconds without having to issue an extra HTTP request.

Cadence: 2s while anything is moving (worker running, queue non-empty,
non-terminal state); 10s when idle. The heartbeat ensures a `search_status`
event lands within ~30s regardless.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from ..search import client as search_client
from ..search.contracts import SearchStatusResponse
from ..search.supervisor import pause_flag_path
from ..tmux_manager import tmux_manager

if TYPE_CHECKING:
    from .events import EventBus

logger = logging.getLogger(__name__)

ACTIVE_POLL_SECONDS = 2.0
IDLE_POLL_SECONDS = 10.0
HEARTBEAT_SECONDS = 30.0


async def _open_session_count() -> int | None:
    try:
        windows = await tmux_manager.list_windows()
    except Exception as exc:  # noqa: BLE001
        logger.debug("search status publisher could not list windows: %s", exc)
        return None
    return len(windows)


def _status_signature(status: SearchStatusResponse) -> tuple[Any, ...]:
    """Visible-state fingerprint. Two statuses with the same signature look
    identical in the footer, so we don't need to republish."""
    counters = status.counters
    ops = status.operations
    worker = ops.worker if ops is not None else None
    queue = ops.queue if ops is not None else None
    progress = ops.progress if ops is not None else None
    return (
        status.state,
        status.available,
        status.reason,
        counters.indexed_sessions if counters else None,
        counters.open_sessions if counters else None,
        counters.indexed_chunks if counters else None,
        counters.total_chunks if counters else None,
        counters.queued_items if counters else None,
        counters.failed_items if counters else None,
        worker.status if worker else None,
        worker.current_task if worker else None,
        worker.stale if worker else None,
        worker.paused if worker else None,
        queue.queued_items if queue else None,
        queue.leased_items if queue else None,
        queue.failed_items if queue else None,
        progress.generation_id if progress else None,
    )


def _is_moving(status: SearchStatusResponse) -> bool:
    if status.state in ("building", "partial"):
        return True
    ops = status.operations
    if ops is None:
        return False
    if ops.worker.status == "running" and not ops.worker.stale:
        return True
    if ops.queue.queued_items > 0 or ops.queue.leased_items > 0:
        return True
    return False


async def search_status_publisher_loop(bus: "EventBus") -> None:
    """Run until cancelled. Emits `search_status` events on the bus."""
    last_signature: tuple[Any, ...] | None = None
    last_published_at = 0.0
    while True:
        try:
            open_count = await _open_session_count()
            status = search_client.get_status(open_session_count=open_count)
            signature = _status_signature(status)
            now = time.monotonic()
            elapsed = now - last_published_at

            deferred = pause_flag_path().exists()
            full_signature = signature + (deferred,)
            if full_signature != last_signature or elapsed >= HEARTBEAT_SECONDS:
                payload = status.model_dump(mode="json")
                payload["type"] = "search_status"
                payload["enabled"] = True
                payload["deferred"] = deferred
                await bus.publish(payload)
                last_signature = full_signature
                last_published_at = now

            await asyncio.sleep(
                ACTIVE_POLL_SECONDS if _is_moving(status) else IDLE_POLL_SECONDS,
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("search_status_publisher iteration failed")
            await asyncio.sleep(5.0)
