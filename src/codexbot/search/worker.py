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
from .state import activate_generation, write_worker_status

logger = logging.getLogger(__name__)


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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="codexbot-search-worker")
    parser.add_argument(
        "command",
        nargs="?",
        default="initial-backfill",
        choices=("initial-backfill", "rebuild"),
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
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["main", "run_initial_backfill", "run_rebuild"]
