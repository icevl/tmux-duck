"""Nonblocking search worker supervisor used by backend startup."""

from __future__ import annotations

import asyncio
import logging
import subprocess
import sys

from .state import read_generation_metadata, read_worker_status
from .worker import drain_live_queue_once

logger = logging.getLogger(__name__)


async def start_worker_if_needed() -> None:
    """Launch initial backfill worker process when no active generation exists."""
    if read_generation_metadata() is not None:
        return

    worker_status = read_worker_status()
    if worker_status is not None and worker_status.status == "running":
        return

    try:
        await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "codexbot.search.worker",
            "initial-backfill",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        logger.warning("Could not launch search worker: %s", exc)


async def live_queue_loop(*, poll_interval_seconds: float = 1.0) -> None:
    """Run live queue draining without blocking web startup."""
    while True:
        try:
            await asyncio.to_thread(drain_live_queue_once)
        except Exception:
            logger.exception("search live queue loop failed")
        await asyncio.sleep(poll_interval_seconds)


__all__ = ["live_queue_loop", "start_worker_if_needed"]
