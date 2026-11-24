"""Logging for the service: a size-capped file under launchd, stderr in a TTY.

Under launchd, stdout/stderr land in ~/.codexbot/logs/launchd.*.log, which
launchd never rotates. Python logging therefore goes to its own rotating
file, and stderr — still where crashes and child-process output end up —
is filtered: every child process we spawn (tmux, ~50 a second) prints
macOS's harmless "MallocStackLogging: can't turn off malloc stack logging"
warning on start, which grew that file by hundreds of MB a day.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
import threading

from .utils import codexbot_dir

LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
LOG_MAX_BYTES = 20 * 1024 * 1024
LOG_BACKUPS = 5

# Lines dropped from stderr (child-process noise, see module docstring).
_STDERR_NOISE = (b"MallocStackLogging: can't turn off malloc stack logging",)


def log_file() -> str:
    return str(codexbot_dir() / "logs" / "codexbot.log")


def setup_logging() -> None:
    """Configure the root logger; call once at startup."""
    if sys.stderr.isatty():
        logging.basicConfig(format=LOG_FORMAT, level=logging.INFO)
        return
    path = log_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(LOG_FORMAT))
    logging.basicConfig(level=logging.INFO, handlers=[handler])
    _filter_stderr()


def _filter_stderr() -> None:
    """Route fd 2 (ours and every child's) through a noise filter."""
    real_stderr = os.dup(2)
    read_fd, write_fd = os.pipe()
    os.dup2(write_fd, 2)
    os.close(write_fd)

    def pump() -> None:
        with os.fdopen(read_fd, "rb", buffering=0) as src:
            buffer = b""
            while chunk := src.read(65536):
                buffer += chunk
                *lines, buffer = buffer.split(b"\n")
                kept = [
                    line
                    for line in lines
                    if not any(noise in line for noise in _STDERR_NOISE)
                ]
                if kept:
                    os.write(real_stderr, b"\n".join(kept) + b"\n")

    threading.Thread(target=pump, name="stderr-filter", daemon=True).start()
