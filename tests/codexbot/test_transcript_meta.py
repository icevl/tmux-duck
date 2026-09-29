"""Transcript metadata: title, permission mode, PR link, model."""

import json
from unittest.mock import patch

import pytest

from codexbot.monitor_state import TrackedSession
from codexbot.session_monitor import SessionInfo, SessionMonitor
from codexbot.transcript_meta import TranscriptMeta, TranscriptMetaCache


def _line(record: dict) -> str:
    return json.dumps(record, separators=(",", ":")) + "\n"


TITLE = {"type": "ai-title", "aiTitle": "Fix the parser"}
MODE = {"type": "permission-mode", "permissionMode": "plan"}
PR = {
    "type": "pr-link",
    "prNumber": 29,
    "prUrl": "https://github.com/acme/app/pull/29",
    "prRepository": "acme/app",
}
TURN = {"type": "user", "message": {"role": "user", "content": "hello"}}


class TestTranscriptMetaCache:
    def test_latest_values_win(self, tmp_path):
        path = tmp_path / "s.jsonl"
        path.write_text(
            _line(TITLE)
            + _line(TURN)
            + _line(MODE)
            + _line(PR)
            + _line({"type": "ai-title", "aiTitle": "Fix the parser and tests"}),
            encoding="utf-8",
        )
        meta = TranscriptMetaCache().get(path)
        assert meta.to_payload() == {
            "title": "Fix the parser and tests",
            "permission_mode": "plan",
            "pr_url": "https://github.com/acme/app/pull/29",
            "pr_number": 29,
            "last_prompt": None,
            "recap": None,
            "recap_at": None,
            "model": None,
            "effort": None,
        }

    def test_reads_only_appended_bytes(self, tmp_path):
        path = tmp_path / "s.jsonl"
        path.write_text(_line(TITLE), encoding="utf-8")
        cache = TranscriptMetaCache()
        assert cache.get(path).title == "Fix the parser"

        with path.open("a", encoding="utf-8") as fh:
            fh.write(_line(MODE))
        with patch("codexbot.transcript_meta.json.loads", wraps=json.loads) as loads:
            meta = cache.get(path)
        assert (meta.title, meta.permission_mode) == ("Fix the parser", "plan")
        assert loads.call_count == 1

    def test_unterminated_tail_is_read_once_complete(self, tmp_path):
        path = tmp_path / "s.jsonl"
        partial = _line(MODE)
        path.write_text(_line(TITLE) + partial[:10], encoding="utf-8")
        cache = TranscriptMetaCache()
        assert cache.get(path).permission_mode is None

        path.write_text(_line(TITLE) + partial, encoding="utf-8")
        assert cache.get(path).permission_mode == "plan"

    def test_truncated_file_is_rescanned(self, tmp_path):
        path = tmp_path / "s.jsonl"
        path.write_text(_line(TITLE) + _line(PR), encoding="utf-8")
        cache = TranscriptMetaCache()
        assert cache.get(path).pr_number == 29

        path.write_text(_line(MODE), encoding="utf-8")
        assert cache.get(path).to_payload() == {
            "title": None,
            "permission_mode": "plan",
            "pr_url": None,
            "pr_number": None,
            "last_prompt": None,
            "recap": None,
            "recap_at": None,
            "model": None,
            "effort": None,
        }

    def test_missing_file(self, tmp_path):
        assert TranscriptMetaCache().get(tmp_path / "nope.jsonl") == TranscriptMeta()

    def test_rejects_non_http_pr_url(self):
        meta = TranscriptMeta()
        assert not meta.apply({"type": "pr-link", "prUrl": "javascript:alert(1)"})
        assert meta.pr_url is None


class TestMonitorMetaListener:
    @pytest.mark.asyncio
    async def test_fires_only_when_metadata_changes(self, tmp_path):
        monitor = SessionMonitor(
            projects_path=tmp_path / "projects",
            state_file=tmp_path / "monitor_state.json",
        )
        path = tmp_path / "s.jsonl"
        path.write_text(_line(TITLE) + _line(TURN), encoding="utf-8")
        monitor.state.update_session(
            TrackedSession(session_id="s", file_path=str(path), last_byte_offset=0)
        )
        calls = 0

        async def listener() -> None:
            nonlocal calls
            calls += 1

        monitor.add_meta_listener(listener)
        sessions = [SessionInfo(session_id="s", file_path=path)]
        with patch.object(monitor, "_resolve_active_sessions", return_value=sessions):
            await monitor.check_for_updates({"s"}, bootstrap=False)
            await monitor._notify_meta_listeners()
            assert calls == 1

            with path.open("a", encoding="utf-8") as fh:
                fh.write(_line(TITLE) + _line(TURN))
            await monitor.check_for_updates({"s"}, bootstrap=False)
            await monitor._notify_meta_listeners()
            assert calls == 1

            with path.open("a", encoding="utf-8") as fh:
                fh.write(_line(MODE))
            await monitor.check_for_updates({"s"}, bootstrap=False)
            await monitor._notify_meta_listeners()
            assert calls == 2


class TestSessionRecap:
    def test_latest_recap_and_prompt_without_harness_noise(self, tmp_path):
        path = tmp_path / "s.jsonl"
        path.write_text(
            _line({"type": "ai-title", "aiTitle": "Conversation recall"})
            + _line({"type": "last-prompt", "lastPrompt": "привет"})
            + _line(
                {
                    "type": "system",
                    "subtype": "away_summary",
                    "content": "We shipped the fix. (disable recaps in /config)",
                    "timestamp": "2026-09-26T08:40:19.913Z",
                }
            )
            + _line({"type": "system", "subtype": "turn_duration", "durationMs": 5})
            + _line(
                {
                    "type": "last-prompt",
                    "lastPrompt": "check this (image attached: /tmp/a.png) please",
                }
            ),
            encoding="utf-8",
        )
        meta = TranscriptMetaCache().get(path)
        assert meta.recap == "We shipped the fix."
        assert meta.recap_at == "2026-09-26T08:40:19.913Z"
        assert meta.last_prompt == "check this please"
        assert meta.title == "Conversation recall"

    def test_other_system_records_do_not_count_as_changes(self):
        meta = TranscriptMeta()
        assert not meta.apply({"type": "system", "subtype": "turn_duration"})
        assert meta.apply({"type": "system", "subtype": "away_summary", "content": "x"})


def _assistant(model: str, **extra: object) -> dict:
    # Key order follows Claude's: `message` first, `effort` among the
    # trailing top-level fields.
    return {
        "type": "assistant",
        "message": {
            "model": model,
            "role": "assistant",
            "content": [
                {
                    "type": "tool_use",
                    "name": "Agent",
                    "input": {"model": "haiku", "effort": "low"},
                }
            ],
        },
        **extra,
    }


def _stdout(text: str) -> dict:
    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": f"<local-command-stdout>{text}</local-command-stdout>",
        },
    }


class TestModel:
    def test_claude_model_from_latest_reply(self, tmp_path):
        path = tmp_path / "s.jsonl"
        path.write_text(
            _line(_assistant("claude-opus-5-5"))
            + _line(_assistant("claude-haiku-4-5", isSidechain=True))
            + _line(_assistant("<synthetic>")),
            encoding="utf-8",
        )
        meta = TranscriptMetaCache().get(path)
        assert meta.model == "claude-opus-5-5"
        assert meta.effort is None

    def test_claude_effort_from_latest_reply(self, tmp_path):
        path = tmp_path / "s.jsonl"
        path.write_text(
            _line(_assistant("claude-opus-5-5", effort="high", perTurnEffort="high"))
            + _line(
                _assistant("claude-opus-5-5", effort="medium", perTurnEffort="medium")
            )
            + _line(
                _assistant(
                    "claude-haiku-4-5",
                    isSidechain=True,
                    effort="max",
                    perTurnEffort="max",
                )
            ),
            encoding="utf-8",
        )
        meta = TranscriptMetaCache().get(path)
        assert (meta.model, meta.effort) == ("claude-opus-5-5", "medium")

    def test_effort_in_tool_input_is_ignored(self, tmp_path):
        path = tmp_path / "s.jsonl"
        path.write_text(_line(_assistant("claude-opus-5-5")), encoding="utf-8")
        assert TranscriptMetaCache().get(path).effort is None

    def test_assistant_lines_are_not_json_parsed(self, tmp_path):
        path = tmp_path / "s.jsonl"
        path.write_text(_line(_assistant("claude-sonnet-5")), encoding="utf-8")
        with patch("codexbot.transcript_meta.json.loads", wraps=json.loads) as loads:
            meta = TranscriptMetaCache().get(path)
        assert meta.model == "claude-sonnet-5"
        assert loads.call_count == 0

    def test_claude_model_and_effort_commands(self, tmp_path):
        path = tmp_path / "s.jsonl"
        path.write_text(
            _line(_assistant("claude-opus-5-5"))
            + _line(
                _stdout(
                    "Set model to \x1b[1mSonnet 5\x1b[22m and saved as your "
                    "default for new sessions"
                )
            )
            + _line(
                _stdout(
                    "Set effort level to high (saved as your default for new "
                    "sessions): Comprehensive implementation"
                )
            ),
            encoding="utf-8",
        )
        meta = TranscriptMetaCache().get(path)
        assert (meta.model, meta.effort) == ("Sonnet 5", "high")

        with path.open("a", encoding="utf-8") as fh:
            fh.write(_line(_stdout("Set model to `Opus 5.5 (1M context)`")))
            fh.write(_line(_assistant("claude-opus-5-5")))
        assert TranscriptMetaCache().get(path).model == "claude-opus-5-5"

    def test_user_text_quoting_the_command_is_ignored(self):
        meta = TranscriptMeta()
        assert not meta.apply(
            {
                "type": "user",
                "message": {"content": "why does it say Set model to Sonnet 5?"},
            }
        )
        assert not meta.apply(
            {
                "type": "user",
                "message": {
                    "content": [
                        {
                            "type": "tool_result",
                            "content": "<local-command-stdout>Set model to X",
                        }
                    ]
                },
            }
        )
        assert meta.model is None

    def test_codex_turn_context(self, tmp_path):
        path = tmp_path / "rollout.jsonl"
        path.write_text(
            _line({"type": "session_meta", "payload": {"id": "abc"}})
            + _line(
                {
                    "type": "turn_context",
                    "payload": {"model": "gpt-5.4", "effort": "medium"},
                }
            )
            + _line({"type": "turn_context", "payload": {"model": "gpt-5.5"}}),
            encoding="utf-8",
        )
        meta = TranscriptMetaCache().get(path)
        assert (meta.model, meta.effort) == ("gpt-5.5", "medium")
