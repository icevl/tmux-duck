"""Agent images (screenshots) reach the web chat as stored media URLs."""

import base64
import json
import os

import pytest

from codexbot import media_store
from codexbot.media_store import MEDIA_NAME_RE, store_images
from codexbot.session import _messages_from_parsed
from codexbot.transcript_parser import TranscriptParser

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


@pytest.fixture(autouse=True)
def state_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEXBOT_DIR", str(tmp_path))
    return tmp_path


def _codex_view_image(output):
    return [
        {
            "type": "response_item",
            "timestamp": "2026-11-11T10:00:00Z",
            "payload": {
                "type": "function_call",
                "name": "view_image",
                "call_id": "call_1",
                "arguments": json.dumps({"path": "/tmp/shot.png"}),
            },
        },
        {
            "type": "response_item",
            "timestamp": "2026-11-11T10:00:01Z",
            "payload": {
                "type": "function_call_output",
                "call_id": "call_1",
                "output": output,
            },
        },
    ]


class TestCodexViewImage:
    def test_image_output_becomes_image_data_not_base64_text(self):
        data_uri = "data:image/png;base64," + base64.b64encode(PNG).decode()
        entries, _ = TranscriptParser.parse_entries(
            _codex_view_image([{"type": "input_image", "image_url": data_uri}])
        )
        result = next(e for e in entries if e.content_type == "tool_result")
        assert result.image_data == [("image/png", PNG)]
        assert "base64" not in result.text

    def test_text_output_list_keeps_its_text(self):
        entries, _ = TranscriptParser.parse_entries(
            _codex_view_image([{"type": "input_text", "text": "no image here"}])
        )
        result = next(e for e in entries if e.content_type == "tool_result")
        assert "no image here" in result.text
        assert not result.image_data


class TestMediaStore:
    def test_stores_once_by_content(self, state_dir):
        first = store_images([("image/png", PNG)])
        again = store_images([("image/png", PNG)])
        assert first == again and len(first) == 1
        name = first[0].removeprefix("/api/media/")
        assert MEDIA_NAME_RE.match(name)
        assert (state_dir / "media" / name).read_bytes() == PNG

    def test_skips_unknown_types(self):
        assert store_images([("image/svg+xml", b"<svg/>"), ("image/png", b"")]) == []

    def test_name_pattern_rejects_paths(self):
        assert not MEDIA_NAME_RE.match("../state.json")
        assert not MEDIA_NAME_RE.match("a" * 32 + ".svg")

    def test_prune_removes_only_old_media(self, state_dir):
        [url] = store_images([("image/png", PNG)])
        path = state_dir / "media" / url.removeprefix("/api/media/")
        assert media_store.prune_media() == 0
        old = path.stat().st_mtime - 40 * 86400
        os.utime(path, (old, old))
        assert media_store.prune_media() == 1
        assert not path.exists()


def test_history_messages_carry_image_urls():
    data_uri = "data:image/png;base64," + base64.b64encode(PNG).decode()
    entries, _ = TranscriptParser.parse_entries(
        _codex_view_image([{"type": "input_image", "image_url": data_uri}])
    )
    messages = _messages_from_parsed(entries)
    result = next(m for m in messages if m["content_type"] == "tool_result")
    assert result["images"] == store_images([("image/png", PNG)])
    tool_use = next(m for m in messages if m["content_type"] == "tool_use")
    assert "images" not in tool_use
