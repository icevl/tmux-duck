"""Discovery + parsing of Claude Code subagent transcripts.

Claude Code writes subagent (Agent / Workflow) transcripts to sibling files of
the main session transcript — the session monitor only reads the main file, so
without these helpers the Web UI never sees subagent work. Layout::

    ~/.claude/projects/<slug>/<uuid>.jsonl                       (main session)
    ~/.claude/projects/<slug>/<uuid>/subagents/
        agent-<id>.jsonl                                         (interactive Agent run)
        agent-<id>.meta.json            {agentType, description}
        workflows/wf_<runId>/
            agent-<id>.jsonl                                     (Workflow subagent run)
            agent-<id>.meta.json        {agentType, ...}
            journal.jsonl               {type: started|result, agentId}

Every subagent line carries `isSidechain: true` and an `agentId`; a finished
interactive run ends in an assistant message with `stop_reason == "end_turn"`,
and a finished Workflow run gets a `{type:"result", agentId}` journal line.
Subagent files never contain a `system/turn_duration` record.

These helpers back the read-only Web UI endpoints (list a session's subagents
and fetch one subagent's transcript on demand). They never mutate state.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .transcript_parser import TranscriptParser

logger = logging.getLogger(__name__)

# agentId / runId are filesystem path components — validate before joining.
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass
class SubagentInfo:
    agent_id: str
    agent_type: str
    description: str
    spawn_kind: str  # "agent" | "workflow"
    run_id: str | None  # workflow run id (wf_…) when spawn_kind == "workflow"
    status: str  # "running" | "completed"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_safe_id(value: str) -> bool:
    return bool(value) and _SAFE_ID_RE.match(value) is not None


def subagents_dir(main_file: Path) -> Path:
    """`<slug>/<uuid>.jsonl` → `<slug>/<uuid>/subagents`."""
    return main_file.with_suffix("") / "subagents"


def _agent_id_from_file(agent_file: Path) -> str:
    # agent-<id>.jsonl → <id>
    stem = agent_file.stem  # "agent-<id>"
    return stem[len("agent-") :] if stem.startswith("agent-") else stem


def _read_meta(agent_file: Path) -> tuple[str, str]:
    meta_path = agent_file.with_suffix(".meta.json")
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "", ""
    if not isinstance(data, dict):
        return "", ""
    return str(data.get("agentType", "")), str(data.get("description", ""))


def _last_json_record(path: Path) -> dict | None:
    """Parse the file's last complete JSONL record, reading backwards.

    A single subagent record (e.g. a long final assistant message) can exceed
    any fixed tail size, so we grow the read window from the end until the last
    non-empty line parses as JSON.
    """
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size == 0:
        return None
    window = 65536
    try:
        with path.open("rb") as fh:
            while True:
                read_back = min(window, size)
                fh.seek(size - read_back)
                chunk = fh.read(read_back)
                lines = chunk.split(b"\n")
                # The trailing element is empty (file ends with "\n") or the
                # final complete line; either way the last non-empty entry is a
                # complete record as long as it isn't the very first split
                # element of a window that began mid-record.
                last = next((ln for ln in reversed(lines) if ln.strip()), None)
                if last is not None:
                    try:
                        data = json.loads(last.decode("utf-8", errors="ignore"))
                        return data if isinstance(data, dict) else None
                    except json.JSONDecodeError:
                        pass
                if read_back >= size or window > 8 * 1024 * 1024:
                    return None
                window *= 4
    except OSError:
        return None


def _ends_in_end_turn(agent_file: Path) -> bool:
    """True if the last complete JSONL record is an assistant end_turn — the
    marker that an interactive subagent run finished."""
    data = _last_json_record(agent_file)
    if data is None:
        return False
    message = data.get("message")
    if isinstance(message, dict):
        return message.get("stop_reason") in ("end_turn", "stop_sequence")
    return False


def _load_workflow_results(journal_path: Path) -> set[str]:
    """agentIds that have a `{type:"result"}` journal line (completed)."""
    done: set[str] = set()
    try:
        text = journal_path.read_text(encoding="utf-8")
    except OSError:
        return done
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if data.get("type") == "result" and isinstance(data.get("agentId"), str):
            done.add(data["agentId"])
    return done


def _build_info(
    agent_file: Path,
    *,
    spawn_kind: str,
    run_id: str | None,
    completed_ids: set[str] | None,
) -> SubagentInfo:
    agent_id = _agent_id_from_file(agent_file)
    agent_type, description = _read_meta(agent_file)
    if completed_ids is not None:
        completed = agent_id in completed_ids or _ends_in_end_turn(agent_file)
    else:
        completed = _ends_in_end_turn(agent_file)
    return SubagentInfo(
        agent_id=agent_id,
        agent_type=agent_type or ("workflow-subagent" if run_id else "agent"),
        description=description,
        spawn_kind=spawn_kind,
        run_id=run_id,
        status="completed" if completed else "running",
    )


def discover_subagents(main_file: Path) -> list[SubagentInfo]:
    """List every subagent run spawned by a Claude main session."""
    base = subagents_dir(main_file)
    if not base.is_dir():
        return []

    out: list[SubagentInfo] = []
    try:
        for agent_file in sorted(base.glob("agent-*.jsonl")):
            out.append(
                _build_info(
                    agent_file, spawn_kind="agent", run_id=None, completed_ids=None
                )
            )
        for wf_dir in sorted(base.glob("workflows/wf_*")):
            if not wf_dir.is_dir():
                continue
            run_id = wf_dir.name
            completed = _load_workflow_results(wf_dir / "journal.jsonl")
            for agent_file in sorted(wf_dir.glob("agent-*.jsonl")):
                out.append(
                    _build_info(
                        agent_file,
                        spawn_kind="workflow",
                        run_id=run_id,
                        completed_ids=completed,
                    )
                )
    except OSError as e:
        logger.debug("subagent discovery failed for %s: %s", main_file, e)
    return out


def resolve_subagent_file(main_file: Path, agent_id: str) -> Path | None:
    """Locate the transcript file for a subagent id under a main session."""
    if not is_safe_id(agent_id):
        return None
    base = subagents_dir(main_file)
    if not base.is_dir():
        return None
    direct = base / f"agent-{agent_id}.jsonl"
    if direct.is_file():
        return direct
    for wf_dir in base.glob("workflows/wf_*"):
        candidate = wf_dir / f"agent-{agent_id}.jsonl"
        if candidate.is_file():
            return candidate
    return None


def load_subagent_messages(main_file: Path, agent_id: str) -> list[dict[str, Any]] | None:
    """Parse a subagent transcript into Web-UI message dicts (history snapshot).

    Returns None when the subagent file can't be found. `completion` control
    entries are dropped (they never render as chat bubbles).
    """
    agent_file = resolve_subagent_file(main_file, agent_id)
    if agent_file is None:
        return None

    entries: list[dict] = []
    try:
        with agent_file.open("r", encoding="utf-8") as fh:
            offset = 0
            for line in fh:
                data = TranscriptParser.parse_line(line)
                if data:
                    data[TranscriptParser.TRANSCRIPT_OFFSET_KEY] = offset
                    entries.append(data)
                offset += len(line.encode("utf-8"))
    except OSError as e:
        logger.debug("failed reading subagent file %s: %s", agent_file, e)
        return None

    parsed_entries, _ = TranscriptParser.parse_entries(entries)
    messages: list[dict[str, Any]] = []
    for e in parsed_entries:
        if e.content_type == "completion":
            continue
        message: dict[str, Any] = {
            "role": e.role,
            "text": e.text,
            "content_type": e.content_type,
            "timestamp": e.timestamp,
        }
        if e.tool_name is not None:
            message["tool_name"] = e.tool_name
        if e.tool_input is not None:
            message["tool_input"] = e.tool_input
        if e.tool_use_id is not None:
            message["tool_use_id"] = e.tool_use_id
        if e.transcript_offset is not None:
            message["transcript_offset"] = e.transcript_offset
        if e.transcript_index is not None:
            message["transcript_index"] = e.transcript_index
        messages.append(message)
    return messages
