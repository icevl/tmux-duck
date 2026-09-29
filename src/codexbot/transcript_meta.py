"""Session metadata that Claude Code records in its transcript.

Besides conversation records, Claude Code 2.1 appends small metadata
records to the session JSONL::

    {"type": "ai-title", "aiTitle": "Conversation recall"}
    {"type": "permission-mode", "permissionMode": "bypassPermissions"}
    {"type": "pr-link", "prNumber": 29, "prUrl": "https://…/pull/29", …}
    {"type": "last-prompt", "lastPrompt": "fix the parser", …}
    {"type": "system", "subtype": "away_summary", "content": "We fixed …"}

``away_summary`` is Claude's own recap of the session (goal, state, next
step), written when the user comes back after a break; together with the
last prompt it tells a returning user what the session is about — the
auto title is generated once from the first message and goes stale.

The active model comes from the conversation itself: Claude stamps every
assistant message with ``message.model`` (and a top-level ``effort``) and
echoes ``/model`` / ``/effort`` as ``<local-command-stdout>Set model to …``
user records (so a switch shows up before the next reply); Codex writes a ``turn_context`` record carrying
``model`` and ``effort`` at the start of every turn.

The latest of each wins. ``TranscriptMetaCache`` keeps a per-file byte
offset so repeated lookups (every `/api/sessions` call) only parse what was
appended since the previous one, and only lines that can carry metadata.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from dataclasses import astuple, dataclass, field, replace
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

META_RECORD_TYPES = frozenset(
    {
        "ai-title",
        "permission-mode",
        "pr-link",
        "last-prompt",
        "system",
        "assistant",
        "user",
        "turn_context",
    }
)
_META_LINE_MARKERS = (
    b'"type":"ai-title"',
    b'"type":"permission-mode"',
    b'"type":"pr-link"',
    b'"type":"last-prompt"',
    b'"subtype":"away_summary"',
    b'"type":"turn_context"',
    b"<local-command-stdout>Set ",
)
_ASSISTANT_MARKER = b'"type":"assistant"'
# The first "model" key of an assistant line is `message.model`; tool inputs
# (e.g. an Agent call's `"model":"sonnet"`) come later in the record.
_ASSISTANT_MODEL = re.compile(rb'"model":"([^"\\]+)"')
# Claude 2.1 stamps the reasoning effort as top-level fields written after
# `message` (`…,"effort":"medium","perTurnEffort":"medium",…`); matching the
# pair, in the line's tail, keeps a tool input's own "effort" key out.
_ASSISTANT_EFFORT = (
    re.compile(rb'"effort":"([a-z]+)","perTurnEffort":"'),
    re.compile(rb'"perTurnEffort":"([a-z]+)"'),
)
_ASSISTANT_TAIL_BYTES = 1024
_SIDECHAIN_MARKER = b'"isSidechain":true'
_RECAP_FOOTER = re.compile(r"\s*\(disable recaps in /config\)\s*$")
_IMAGE_ATTACHMENT = re.compile(r"\s*\(image attached: [^)]*\)")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_SET_MODEL = re.compile(r"^<local-command-stdout>Set model to (.+?)(?: and saved\b|$)")
_SET_EFFORT = re.compile(r"^<local-command-stdout>Set effort level to ([a-z]+)")
_SYNTHETIC_MODEL = "<synthetic>"
_READ_CHUNK_BYTES = 1 << 20


@dataclass
class TranscriptMeta:
    title: str | None = None
    permission_mode: str | None = None
    pr_url: str | None = None
    pr_number: int | None = None
    last_prompt: str | None = None
    recap: str | None = None
    recap_at: str | None = None
    # A model id ("claude-opus-5-5", "gpt-5.4") or, right after a `/model`
    # switch and until the next reply, Claude's display name ("Sonnet 5").
    model: str | None = None
    effort: str | None = None

    def apply(self, record: dict[str, Any]) -> bool:
        """Fold one transcript record in; return True if anything changed."""
        kind = record.get("type")
        before = astuple(self)
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
        elif kind == "last-prompt":
            prompt = record.get("lastPrompt")
            if isinstance(prompt, str):
                prompt = _IMAGE_ATTACHMENT.sub("", prompt).strip()
                if prompt:
                    self.last_prompt = prompt
        elif kind == "system" and record.get("subtype") == "away_summary":
            content = record.get("content")
            if isinstance(content, str):
                recap = _RECAP_FOOTER.sub("", content).strip()
                if recap:
                    self.recap = recap
                    timestamp = record.get("timestamp")
                    self.recap_at = timestamp if isinstance(timestamp, str) else None
        elif kind == "assistant" and not record.get("isSidechain"):
            message = record.get("message")
            model = message.get("model") if isinstance(message, dict) else None
            if isinstance(model, str) and model and model != _SYNTHETIC_MODEL:
                self.model = model
                effort = record.get("effort")
                if isinstance(effort, str) and effort:
                    self.effort = effort
        elif kind == "user":
            message = record.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            if isinstance(content, str):
                self._apply_local_command(content)
        elif kind == "turn_context":
            payload = record.get("payload")
            if isinstance(payload, dict):
                model = payload.get("model")
                if isinstance(model, str) and model:
                    self.model = model
                effort = payload.get("effort")
                if isinstance(effort, str) and effort:
                    self.effort = effort
        return before != astuple(self)

    def _apply_local_command(self, content: str) -> None:
        if not content.startswith("<local-command-stdout>Set "):
            return
        text = _ANSI.sub("", content).replace("`", "")
        if match := _SET_MODEL.match(text):
            model = match.group(1).strip()
            if model:
                self.model = model
        elif match := _SET_EFFORT.match(text):
            self.effort = match.group(1)

    def to_payload(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "permission_mode": self.permission_mode,
            "pr_url": self.pr_url,
            "pr_number": self.pr_number,
            "last_prompt": self.last_prompt,
            "recap": self.recap,
            "recap_at": self.recap_at,
            "model": self.model,
            "effort": self.effort,
        }


@dataclass
class _FileState:
    offset: int = 0
    meta: TranscriptMeta = field(default_factory=TranscriptMeta)


def _is_meta_line(line: bytes) -> bool:
    # Claude writes compact JSON, so a substring test avoids parsing the
    # (often multi-megabyte) conversation records.
    return any(marker in line for marker in _META_LINE_MARKERS)


def _assistant_model_record(line: bytes) -> dict[str, Any] | None:
    """Model and effort of an assistant line, without parsing the record.

    Assistant records carry the (large) response content, and only
    ``message.model`` and ``effort`` matter here, so a regex beats
    ``json.loads``.
    """
    if _ASSISTANT_MARKER not in line or _SIDECHAIN_MARKER in line:
        return None
    match = _ASSISTANT_MODEL.search(line)
    if match is None:
        return None
    try:
        model = match.group(1).decode("utf-8")
    except UnicodeDecodeError:
        return None
    record: dict[str, Any] = {"type": "assistant", "message": {"model": model}}
    tail = line[-_ASSISTANT_TAIL_BYTES:]
    for pattern in _ASSISTANT_EFFORT:
        if efforts := pattern.findall(tail):
            record["effort"] = efforts[-1].decode("ascii")
            break
    return record


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
                        if (fast := _assistant_model_record(line)) is not None:
                            state.meta.apply(fast)
                            continue
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
