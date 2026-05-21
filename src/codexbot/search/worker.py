"""Local search worker CLI skeleton.

Phase 2 establishes the process boundary and status state. Real transcript
backfill, generation activation, and retrieval are added by later plans.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from typing import Sequence

from .contracts import SearchWorkerStatus
from .state import write_worker_status


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def run_initial_backfill() -> None:
    """Mark initial backfill as running for status consumers."""
    write_worker_status(
        SearchWorkerStatus(
            status="running",
            current_task="initial_backfill",
            heartbeat_at=_now_iso(),
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
        run_initial_backfill()
        return 0
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = ["main", "run_initial_backfill"]
