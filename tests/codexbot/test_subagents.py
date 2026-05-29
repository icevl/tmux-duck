"""Tests for subagent discovery + transcript loading (codexbot.subagents)."""

import json
from pathlib import Path

from codexbot.subagents import (
    discover_subagents,
    load_subagent_messages,
    resolve_subagent_file,
)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _assistant(text: str, stop_reason: str = "end_turn") -> dict:
    return {
        "type": "assistant",
        "isSidechain": True,
        "timestamp": "2026-05-29T08:00:00Z",
        "message": {
            "role": "assistant",
            "stop_reason": stop_reason,
            "content": [{"type": "text", "text": text}],
        },
    }


def _user(text: str) -> dict:
    return {
        "type": "user",
        "isSidechain": True,
        "timestamp": "2026-05-29T07:59:00Z",
        "message": {"role": "user", "content": [{"type": "text", "text": text}]},
    }


def _build_project(tmp_path: Path) -> Path:
    """Mirror the real layout: main <uuid>.jsonl + sibling subagents/ tree."""
    main = tmp_path / "proj" / "sess.jsonl"
    main.parent.mkdir(parents=True, exist_ok=True)
    main.write_text(json.dumps({"type": "user", "message": {"content": "hi"}}) + "\n")

    subs = main.with_suffix("") / "subagents"

    # Interactive Agent run — finished (ends in end_turn).
    _write_jsonl(
        subs / "agent-aaa111.jsonl",
        [_user("explore the repo"), _assistant("Found 3 files.")],
    )
    (subs / "agent-aaa111.meta.json").write_text(
        json.dumps({"agentType": "Explore", "description": "repo scan"})
    )

    # Interactive Agent run — still running (last line not end_turn).
    _write_jsonl(
        subs / "agent-bbb222.jsonl",
        [_user("do work"), _assistant("partial", stop_reason="tool_use")],
    )
    (subs / "agent-bbb222.meta.json").write_text(
        json.dumps({"agentType": "general", "description": "in progress"})
    )

    # Workflow run — one agent completed (journal), one running.
    wf = subs / "workflows" / "wf_run1"
    _write_jsonl(wf / "agent-ccc333.jsonl", [_user("step"), _assistant("done step")])
    (wf / "agent-ccc333.meta.json").write_text(json.dumps({"agentType": "worker"}))
    _write_jsonl(
        wf / "agent-ddd444.jsonl",
        [_user("step2"), _assistant("working", stop_reason="tool_use")],
    )
    (wf / "agent-ddd444.meta.json").write_text(json.dumps({"agentType": "worker"}))
    (wf / "journal.jsonl").write_text(
        "\n".join(
            json.dumps(r)
            for r in [
                {"type": "started", "agentId": "ccc333"},
                {"type": "started", "agentId": "ddd444"},
                {"type": "result", "agentId": "ccc333"},
            ]
        )
        + "\n"
    )
    return main


def test_discover_lists_agent_and_workflow_runs(tmp_path: Path) -> None:
    main = _build_project(tmp_path)
    subs = {s.agent_id: s for s in discover_subagents(main)}
    assert set(subs) == {"aaa111", "bbb222", "ccc333", "ddd444"}

    assert subs["aaa111"].spawn_kind == "agent"
    assert subs["aaa111"].agent_type == "Explore"
    assert subs["aaa111"].description == "repo scan"
    assert subs["aaa111"].status == "completed"  # ends in end_turn

    assert subs["bbb222"].status == "running"  # last line is tool_use

    assert subs["ccc333"].spawn_kind == "workflow"
    assert subs["ccc333"].run_id == "wf_run1"
    assert subs["ccc333"].status == "completed"  # journal result line
    assert subs["ddd444"].status == "running"  # started but no result, not end_turn


def test_no_subagents_dir_returns_empty(tmp_path: Path) -> None:
    main = tmp_path / "proj" / "lonely.jsonl"
    main.parent.mkdir(parents=True, exist_ok=True)
    main.write_text("{}\n")
    assert discover_subagents(main) == []


def test_load_messages_parses_transcript(tmp_path: Path) -> None:
    main = _build_project(tmp_path)
    msgs = load_subagent_messages(main, "aaa111")
    assert msgs is not None
    texts = [m["text"] for m in msgs if m["content_type"] == "text"]
    assert "Found 3 files." in texts
    # Completion control entries never leak into the rendered transcript.
    assert all(m["content_type"] != "completion" for m in msgs)


def test_load_messages_unknown_agent_returns_none(tmp_path: Path) -> None:
    main = _build_project(tmp_path)
    assert load_subagent_messages(main, "nope999") is None


def test_path_traversal_is_rejected(tmp_path: Path) -> None:
    main = _build_project(tmp_path)
    assert resolve_subagent_file(main, "../../../etc/passwd") is None
    assert load_subagent_messages(main, "../../secret") is None
