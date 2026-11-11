"""Images agents produce (screenshots they Read / view), served to the web UI.

Transcripts carry these as base64 inside tool results. Rather than ship the
bytes in every history response and WebSocket event, each image is written
once to ``<state dir>/media/<sha256>.<ext>`` and messages reference it by
URL (``/api/media/<name>``). Content addressing makes rewrites idempotent:
re-parsing a transcript lands on the same files.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from pathlib import Path

from .utils import codexbot_dir

logger = logging.getLogger(__name__)

# Media no message has referenced for this long is pruned at startup; a
# transcript that's re-read later just writes it again.
MAX_AGE_DAYS = 30

_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
}

# What /api/media accepts: exactly the names this module writes.
MEDIA_NAME_RE = re.compile(r"^[0-9a-f]{32}\.(png|jpg|gif|webp)$")


def media_dir() -> Path:
    return codexbot_dir() / "media"


def store_images(images: list[tuple[str, bytes]] | None) -> list[str]:
    """Persist images and return their URLs; unknown types are skipped."""
    urls: list[str] = []
    if not images:
        return urls
    for media_type, data in images:
        ext = _EXTENSIONS.get(media_type.lower())
        if not ext or not data:
            continue
        name = f"{hashlib.sha256(data).hexdigest()[:32]}.{ext}"
        path = media_dir() / name
        try:
            if path.exists():
                # Touch so pruning keeps media that's still being shown.
                path.touch()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".tmp")
                tmp.write_bytes(data)
                tmp.replace(path)
        except OSError:
            logger.warning("Could not store agent image %s", name, exc_info=True)
            continue
        urls.append(f"/api/media/{name}")
    return urls


def prune_media(max_age_days: int = MAX_AGE_DAYS) -> int:
    """Delete media untouched for ``max_age_days``; returns how many."""
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    try:
        entries = list(media_dir().iterdir())
    except OSError:
        return 0
    for path in entries:
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
                removed += 1
        except OSError:
            continue
    return removed
