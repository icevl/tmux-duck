"""Tests for the local agent-usage collectors (sidebar counters)."""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from codexbot.web.usage import UsageCollector, read_codex_usage


# ── Codex rollout parsing ───────────────────────────────────────────────────


def _write_rollout(root: Path, day: str, name: str, lines: list[dict]) -> Path:
    d = root / day
    d.mkdir(parents=True, exist_ok=True)
    f = d / name
    f.write_text("\n".join(json.dumps(x) for x in lines) + "\n")
    return f


def _rate_limit_event(primary_pct: float, secondary_pct: float) -> dict:
    return {
        "timestamp": "2026-07-02T10:00:00Z",
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {"total_token_usage": {"total_tokens": 1}},
            "rate_limits": {
                "limit_id": "codex",
                "primary": {
                    "used_percent": primary_pct,
                    "window_minutes": 300,
                    "resets_at": 1779740975,
                },
                "secondary": {
                    "used_percent": secondary_pct,
                    "window_minutes": 10080,
                    "resets_at": 1780345775,
                },
            },
        },
    }


def test_codex_reads_last_rate_limits(tmp_path: Path) -> None:
    _write_rollout(
        tmp_path,
        "2026/07/02",
        "rollout-a.jsonl",
        [
            {"type": "event_msg", "payload": {"type": "user_message"}},
            _rate_limit_event(10.0, 5.0),
            {"type": "event_msg", "payload": {"type": "agent_message"}},
            _rate_limit_event(30.5, 23.0),
        ],
    )
    usage = read_codex_usage(tmp_path)
    assert usage is not None
    assert usage["primary"]["used_percent"] == 30.5
    assert usage["primary"]["window_minutes"] == 300
    assert usage["secondary"]["used_percent"] == 23.0
    assert usage["updated_at"] is not None


def test_codex_picks_newest_day_dir(tmp_path: Path) -> None:
    _write_rollout(
        tmp_path, "2026/06/30", "rollout-old.jsonl", [_rate_limit_event(99.0, 99.0)]
    )
    _write_rollout(
        tmp_path, "2026/07/02", "rollout-new.jsonl", [_rate_limit_event(12.0, 7.0)]
    )
    usage = read_codex_usage(tmp_path)
    assert usage is not None
    assert usage["primary"]["used_percent"] == 12.0


def test_codex_missing_dir_returns_none(tmp_path: Path) -> None:
    assert read_codex_usage(tmp_path / "nope") is None


def test_codex_no_rate_limits_returns_none(tmp_path: Path) -> None:
    _write_rollout(
        tmp_path,
        "2026/07/02",
        "rollout-a.jsonl",
        [{"type": "event_msg", "payload": {}}],
    )
    assert read_codex_usage(tmp_path) is None


# ── Claude transcript aggregation ───────────────────────────────────────────


def _usage_line(msg_id: str, ts: float, inp: int, out: int) -> str:
    return json.dumps(
        {
            "type": "assistant",
            "timestamp": datetime.fromtimestamp(ts, tz=timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            "message": {
                "id": msg_id,
                "usage": {
                    "input_tokens": inp,
                    "output_tokens": out,
                    "cache_read_input_tokens": 100,
                    "cache_creation_input_tokens": 10,
                },
            },
        }
    )


@pytest.fixture
def claude_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "projects"
    (root / "-Users-mike-proj").mkdir(parents=True)
    from codexbot.config import config

    monkeypatch.setattr(config, "claude_projects_path", root)
    return root


def test_claude_sums_and_dedups(claude_root: Path) -> None:
    now = time.time()
    f = claude_root / "-Users-mike-proj" / "s1.jsonl"
    # One message written as three content-block lines (same id, same usage) —
    # must be counted once. A second distinct message adds on top.
    f.write_text(
        "\n".join(
            [
                _usage_line("msg_1", now - 60, 100, 50),
                _usage_line("msg_1", now - 60, 100, 50),
                _usage_line("msg_1", now - 60, 100, 50),
                _usage_line("msg_2", now - 30, 20, 5),
            ]
        )
        + "\n"
    )
    snap = UsageCollector().snapshot()
    claude = snap["claude"]
    assert claude is not None
    assert claude["today"]["input"] == 120
    assert claude["today"]["output"] == 55
    assert claude["last_5h"]["input"] == 120


def test_claude_incremental_append(claude_root: Path) -> None:
    now = time.time()
    f = claude_root / "-Users-mike-proj" / "s1.jsonl"
    f.write_text(_usage_line("msg_1", now - 60, 100, 50) + "\n")
    collector = UsageCollector()
    assert collector.snapshot()["claude"]["today"]["input"] == 100
    # Append another message; only the tail is parsed, totals grow.
    with open(f, "a") as fh:
        fh.write(_usage_line("msg_2", now - 10, 7, 3) + "\n")
    snap = collector.snapshot()
    assert snap["claude"]["today"]["input"] == 107
    assert snap["claude"]["today"]["output"] == 53


def test_claude_partial_trailing_line_deferred(claude_root: Path) -> None:
    now = time.time()
    f = claude_root / "-Users-mike-proj" / "s1.jsonl"
    full = _usage_line("msg_1", now - 60, 100, 50)
    partial = _usage_line("msg_2", now - 10, 7, 3)
    f.write_text(full + "\n" + partial[: len(partial) // 2])  # no trailing newline
    collector = UsageCollector()
    assert collector.snapshot()["claude"]["today"]["input"] == 100
    # Complete the partial line — it gets counted on the next poll.
    with open(f, "a") as fh:
        fh.write(partial[len(partial) // 2 :] + "\n")
    assert collector.snapshot()["claude"]["today"]["input"] == 107


def test_claude_truncated_file_reparses(claude_root: Path) -> None:
    now = time.time()
    f = claude_root / "-Users-mike-proj" / "s1.jsonl"
    f.write_text(_usage_line("msg_1", now - 60, 100, 50) + "\n")
    collector = UsageCollector()
    assert collector.snapshot()["claude"]["today"]["input"] == 100
    # File replaced with smaller content (rotation) — cache resets, no double count.
    f.write_text(_usage_line("msg_9", now - 5, 1, 1) + "\n")
    assert collector.snapshot()["claude"]["today"]["input"] == 1


def test_claude_missing_root_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from codexbot.config import config

    monkeypatch.setattr(config, "claude_projects_path", tmp_path / "missing")
    assert UsageCollector().snapshot()["claude"] is None
