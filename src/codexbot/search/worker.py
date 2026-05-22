"""Local search worker CLI skeleton.

Phase 2 establishes the process boundary and status state. Real transcript
backfill, generation activation, and retrieval are added by later plans.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import UTC, datetime
from typing import Sequence

from .backfill import materialize_initial_backfill
from .contracts import SearchWorkerStatus
from .live import upsert_generation_documents
from .queue import (
    complete_items,
    fail_items,
    lease_ready_items,
    ready_item_count,
    record_queue_error,
)
from .state import activate_generation, read_generation_metadata, write_worker_status

logger = logging.getLogger(__name__)
LIVE_BATCH_SIZE = 32
LIVE_FLUSH_INTERVAL_SECONDS = 60.0
_last_live_flush_at: datetime | None = None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _failed_error_summary(exc: BaseException) -> str:
    return f"{type(exc).__name__}: search backfill failed"


def _run_generation_task(current_task: str) -> None:
    """Materialize and activate a fresh generation for a local worker task."""
    write_worker_status(
        SearchWorkerStatus(
            status="running",
            current_task=current_task,
            heartbeat_at=_now_iso(),
        )
    )
    try:
        manifest = asyncio.run(materialize_initial_backfill())
        activate_generation(manifest)
    except Exception as exc:
        logger.exception("search_generation_task_failed task=%s", current_task)
        write_worker_status(
            SearchWorkerStatus(
                status="failed",
                current_task=current_task,
                heartbeat_at=_now_iso(),
                recent_error=_failed_error_summary(exc),
            )
        )
        raise

    write_worker_status(
        SearchWorkerStatus(
            status="completed",
            current_task=current_task,
            heartbeat_at=_now_iso(),
            counters=manifest.counters,
        )
    )


def run_initial_backfill() -> None:
    """Materialize and activate an initial backfill generation."""
    _run_generation_task("initial_backfill")


def run_rebuild() -> None:
    """Materialize and activate a fresh explicit rebuild generation."""
    _run_generation_task("rebuild")


def _seconds_since_flush(now: datetime) -> float:
    if _last_live_flush_at is None:
        return 0.0
    return max(0.0, (now - _last_live_flush_at).total_seconds())


def drain_live_queue_once(
    *,
    batch_size: int = LIVE_BATCH_SIZE,
    flush_interval_seconds: float = LIVE_FLUSH_INTERVAL_SECONDS,
    force: bool = False,
    max_attempts: int = 3,
    now: datetime | None = None,
) -> int:
    """Drain one live queue batch into the active generation when flushable."""
    global _last_live_flush_at
    current_time = now or datetime.now(UTC)
    generation = read_generation_metadata()
    if generation is None:
        return 0

    ready = ready_item_count(now=current_time)
    if ready <= 0:
        return 0

    flush_due = _seconds_since_flush(current_time) >= flush_interval_seconds
    if _last_live_flush_at is None and not force and ready < batch_size:
        _last_live_flush_at = current_time
        return 0
    if not force and ready < batch_size and not flush_due:
        return 0

    items = lease_ready_items(
        limit=batch_size,
        lease_owner="search-live-worker",
        now=current_time,
    )
    if not items:
        return 0

    queue_ids = [item.queue_id for item in items]
    try:
        upsert_generation_documents(
            generation.generation_id,
            [item.document for item in items],
        )
    except Exception as exc:
        logger.exception("search_live_drain_failed")
        record_queue_error(exc)
        fail_items(queue_ids, exc, max_attempts=max_attempts)
        return 0

    complete_items(queue_ids)
    _last_live_flush_at = current_time
    return len(items)


async def run_live_loop(*, poll_interval_seconds: float = 1.0) -> None:
    """Continuously drain live queue work until cancelled."""
    while True:
        try:
            drain_live_queue_once()
        except Exception as exc:
            logger.exception("search_live_loop_iteration_failed")
            record_queue_error(exc)
        await asyncio.sleep(poll_interval_seconds)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="codexbot-search-worker")
    parser.add_argument(
        "command",
        nargs="?",
        default="initial-backfill",
        choices=("initial-backfill", "rebuild", "live-loop", "live-drain-once"),
    )
    args = parser.parse_args(argv)

    if args.command == "initial-backfill":
        try:
            run_initial_backfill()
        except Exception:
            return 1
        return 0
    if args.command == "rebuild":
        try:
            run_rebuild()
        except Exception:
            return 1
        return 0
    if args.command == "live-drain-once":
        try:
            drain_live_queue_once(force=True)
        except Exception:
            return 1
        return 0
    if args.command == "live-loop":
        try:
            asyncio.run(run_live_loop())
        except KeyboardInterrupt:
            return 0
        except Exception:
            return 1
        return 0
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "LIVE_BATCH_SIZE",
    "LIVE_FLUSH_INTERVAL_SECONDS",
    "drain_live_queue_once",
    "main",
    "run_initial_backfill",
    "run_live_loop",
    "run_rebuild",
]
