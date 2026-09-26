"""Claude transcript metadata: title, permission mode, PR link."""

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
