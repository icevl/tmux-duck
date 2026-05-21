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

from .contracts import SearchWorkerStatus
from .state import write_worker_status
from .backfill import materialize_initial_backfill

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _failed_error_summary(exc: BaseException) -> str:
    return f"{type(exc).__name__}: search backfill failed"


def run_initial_backfill() -> None:
    """Materialize an inactive initial backfill generation."""
    write_worker_status(
        SearchWorkerStatus(
            status="running",
            current_task="initial_backfill",
            heartbeat_at=_now_iso(),
        )
    )
    try:
        manifest = asyncio.run(materialize_initial_backfill())
    except Exception as exc:
        logger.exception("search_initial_backfill_failed")
        write_worker_status(
            SearchWorkerStatus(
                status="failed",
                current_task="initial_backfill",
                heartbeat_at=_now_iso(),
                recent_error=_failed_error_summary(exc),
            )
        )
        raise

    write_worker_status(
        SearchWorkerStatus(
            status="completed",
            current_task="initial_backfill",
            heartbeat_at=_now_iso(),
            counters=manifest.counters,
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="codexbot-search-worker")
    parser.add_argument(
        "command",
        nargs="?",
        default="initial-backfill",
        choices=("initial-backfill",),
    )
    args = parser.parse_args(argv)

    if args.command == "initial-backfill":
        try:
            run_initial_backfill()
        except Exception:
            return 1
        return 0
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["main", "run_initial_backfill"]
