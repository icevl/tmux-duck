"""Codex session context injected as `user` messages is not shown as chat."""

from codexbot.transcript_parser import TranscriptParser


def _user_item(*texts: str) -> dict:
    return {
        "type": "response_item",
        "payload": {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": t} for t in texts],
        },
    }


CONTEXT = (
    "# AGENTS.md instructions for /repo\n\n<INSTRUCTIONS>\nbe nice\n</INSTRUCTIONS>",
    "<environment_context>\n  <cwd>/repo</cwd>\n</environment_context>",
)


def test_context_only_message_is_dropped():
    assert TranscriptParser.parse_message(_user_item(*CONTEXT)) is None


def test_real_user_text_survives_next_to_context():
    parsed = TranscriptParser.parse_message(_user_item(CONTEXT[1], "привет"))
    assert parsed is not None
    assert parsed.message_type == "user"
    assert parsed.text == "привет"


def test_plain_user_message_unchanged():
    parsed = TranscriptParser.parse_message(_user_item("fix the parser"))
    assert parsed is not None and parsed.text == "fix the parser"
