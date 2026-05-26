"""Nonblocking search worker supervisor used by backend startup."""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from .idle_detector import IdleTracker, is_workload_idle
from .state import read_generation_metadata, read_worker_status, search_dir
from .worker import drain_live_queue_once

logger = logging.getLogger(__name__)

# A "running" worker_status whose heartbeat is older than this is taken as
# evidence the worker process died (kill -9, OOM, launchd restart) without
# being able to overwrite its own status file. Without this check the
# supervisor would refuse to spawn a fresh worker indefinitely.
RUNNING_STATUS_STALE_SECONDS = 300

# How often the pause controller polls idle state. Two seconds keeps the
# worker responsive to "user started typing again" without churning the
# pause file or hammering tmux capture_pane.
PAUSE_POLL_INTERVAL_SECONDS = 2.0

PAUSE_FLAG_FILENAME = "pause"


def pause_flag_path() -> Path:
    return search_dir() / PAUSE_FLAG_FILENAME


def _set_pause(reason: str) -> None:
    """Create (or refresh) the pause flag file. The body is just an
    advisory reason so a human inspecting the file can see why."""
    path = pause_flag_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(reason)
    except OSError as exc:
        logger.debug("could not write pause flag: %s", exc)


def _clear_pause() -> None:
    try:
        pause_flag_path().unlink()
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.debug("could not remove pause flag: %s", exc)


def _worker_log_path() -> Path:
    """Append-only log file for the search worker subprocess.

    The worker runs out-of-process and used to write to DEVNULL, so any
    import-time or runtime traceback (MPS hangs, dependency mismatches,
    OOM) disappeared. Sending stdout/stderr here keeps the diagnostics."""
    path = search_dir() / "worker.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _running_status_looks_alive(heartbeat_at: str | None) -> bool:
    """True when a 'running' status file was refreshed recently enough that
    the actual process is plausibly still alive. False for orphan status
    files left behind by killed workers."""
    if not heartbeat_at:
        return False
    try:
        parsed = datetime.fromisoformat(heartbeat_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    age = (datetime.now(UTC) - parsed).total_seconds()
    return age < RUNNING_STATUS_STALE_SECONDS


async def start_worker_if_needed(
    idle_tracker: IdleTracker | None = None,
) -> None:
    """Launch initial backfill worker process when no active generation exists.

    Defers start while the workload looks busy — the pause-controller loop
    will keep calling back and try again on the next tick. We never start
    against an idle file because the file is owned by the controller loop;
    here we just hold off until conditions clear.
    """
    if read_generation_metadata() is not None:
        return

    worker_status = read_worker_status()
    if (
        worker_status is not None
        and worker_status.status == "running"
        and _running_status_looks_alive(worker_status.heartbeat_at)
    ):
        return

    if not await is_workload_idle(idle_tracker):
        # Don't even start while busy. Mid-batch pause inside the worker
        # handles the case where the user starts working *after* backfill
        # is already going.
        return

    log_path = _worker_log_path()
    try:
        log_handle = open(log_path, "ab", buffering=0)
    except OSError as exc:
        logger.warning("Could not open search worker log %s: %s", log_path, exc)
        return

    try:
        await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "codexbot.search.worker",
            "initial-backfill",
            stdout=log_handle,
            stderr=log_handle,
        )
    except OSError as exc:
        logger.warning("Could not launch search worker: %s", exc)
    finally:
        # The child inherits the FD; close ours so the file rotates cleanly
        # when the worker exits.
        log_handle.close()


async def pause_controller_loop(idle_tracker: IdleTracker | None = None) -> None:
    """Watch idle state and toggle the pause flag the worker subprocess
    polls between embedding batches. Also retries `start_worker_if_needed`
    so backfill kicks off the moment the workload settles."""
    while True:
        try:
            idle = await is_workload_idle(idle_tracker)
            if idle:
                _clear_pause()
                await start_worker_if_needed(idle_tracker)
            else:
                _set_pause(
                    "agent or build process active in a tmux pane"
                )
        except asyncio.CancelledError:
            _clear_pause()
            raise
        except Exception:  # noqa: BLE001
            logger.exception("pause_controller_loop iteration failed")
        await asyncio.sleep(PAUSE_POLL_INTERVAL_SECONDS)


async def live_queue_loop(*, poll_interval_seconds: float = 1.0) -> None:
    """Run live queue draining without blocking web startup. Skips ticks
    while the pause flag is set so we don't add database churn during
    active user work."""
    flag = pause_flag_path()
    while True:
        try:
            if not flag.exists():
                await asyncio.to_thread(drain_live_queue_once)
        except Exception:
            logger.exception("search live queue loop failed")
        await asyncio.sleep(poll_interval_seconds)


__all__ = [
    "IdleTracker",
    "PAUSE_FLAG_FILENAME",
    "live_queue_loop",
    "pause_controller_loop",
    "pause_flag_path",
    "start_worker_if_needed",
]
