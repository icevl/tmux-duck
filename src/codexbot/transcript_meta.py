"""Session metadata that Claude Code records in its transcript.

Besides conversation records, Claude Code 2.1 appends small metadata
records to the session JSONL::

    {"type": "ai-title", "aiTitle": "Conversation recall"}
    {"type": "permission-mode", "permissionMode": "bypassPermissions"}
    {"type": "pr-link", "prNumber": 29, "prUrl": "https://…/pull/29", …}

The latest of each wins. ``TranscriptMetaCache`` keeps a per-file byte
offset so repeated lookups (every `/api/sessions` call) only parse what was
appended since the previous one, and only lines that can carry metadata.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

META_RECORD_TYPES = frozenset({"ai-title", "permission-mode", "pr-link"})
_META_LINE_MARKERS = tuple(
    f'"type":"{kind}"'.encode() for kind in sorted(META_RECORD_TYPES)
)
_READ_CHUNK_BYTES = 1 << 20


@dataclass
class TranscriptMeta:
    title: str | None = None
    permission_mode: str | None = None
    pr_url: str | None = None
    pr_number: int | None = None

    def apply(self, record: dict[str, Any]) -> bool:
        """Fold one transcript record in; return True if anything changed."""
        kind = record.get("type")
        before = (self.title, self.permission_mode, self.pr_url, self.pr_number)
        if kind == "ai-title":
            title = record.get("aiTitle")
            if isinstance(title, str) and title.strip():
                self.title = title.strip()
        elif kind == "permission-mode":
            mode = record.get("permissionMode")
            if isinstance(mode, str) and mode:
                self.permission_mode = mode
        elif kind == "pr-link":
            url = record.get("prUrl")
            if isinstance(url, str) and url.startswith(("https://", "http://")):
                self.pr_url = url
                number = record.get("prNumber")
                self.pr_number = (
                    number
                    if isinstance(number, int) and not isinstance(number, bool)
                    else None
                )
        return before != (self.title, self.permission_mode, self.pr_url, self.pr_number)

    def to_payload(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "permission_mode": self.permission_mode,
            "pr_url": self.pr_url,
            "pr_number": self.pr_number,
        }


@dataclass
class _FileState:
    offset: int = 0
    meta: TranscriptMeta = field(default_factory=TranscriptMeta)


def _is_meta_line(line: bytes) -> bool:
    # Claude writes compact JSON, so a substring test avoids parsing the
    # (often multi-megabyte) conversation records.
    return any(marker in line for marker in _META_LINE_MARKERS)


class TranscriptMetaCache:
    """Incremental, thread-safe reader of transcript metadata."""

    def __init__(self) -> None:
        self._files: dict[str, _FileState] = {}
        self._lock = threading.Lock()

    def get(self, path: Path) -> TranscriptMeta:
        """Return the metadata of ``path``, reading only newly appended bytes."""
        key = str(path)
        with self._lock:
            state = self._files.setdefault(key, _FileState())
            try:
                size = path.stat().st_size
            except OSError:
                return replace(state.meta)
            if size < state.offset:
                state.offset = 0
                state.meta = TranscriptMeta()
            if size > state.offset:
                self._scan(path, state, size)
            return replace(state.meta)

    @staticmethod
    def _scan(path: Path, state: _FileState, size: int) -> None:
        try:
            with path.open("rb") as fh:
                fh.seek(state.offset)
                pending = b""
                position = state.offset
                while position < size:
                    chunk = fh.read(min(_READ_CHUNK_BYTES, size - position))
                    if not chunk:
                        break
                    position += len(chunk)
                    lines = (pending + chunk).split(b"\n")
                    pending = lines.pop()
                    for line in lines:
                        if not _is_meta_line(line):
                            continue
                        try:
                            record = json.loads(line)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            continue
                        if isinstance(record, dict):
                            state.meta.apply(record)
                # An unterminated tail is a record still being written; leave
                # it for the next scan.
                state.offset = position - len(pending)
        except OSError as e:
            logger.debug("transcript meta scan failed for %s: %s", path, e)


transcript_meta_cache = TranscriptMetaCache()
