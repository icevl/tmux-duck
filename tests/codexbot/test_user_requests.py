"""The Requests panel lists only the user's own prompts."""

from codexbot.web.api import user_requests


def test_keeps_only_user_prompts_in_order():
    messages = [
        {
            "role": "user",
            "content_type": "text",
            "text": " first ",
            "timestamp": "t1",
            "transcript_offset": 10,
            "transcript_index": 0,
        },
        {"role": "assistant", "content_type": "text", "text": "reply"},
        {"role": "user", "content_type": "tool_result", "text": "ok"},
        {"role": "assistant", "content_type": "local_command", "text": "❯ `/model`"},
        {
            "role": "user",
            "content_type": "text",
            "text": "[Request interrupted by user]",
        },
        {"role": "user", "content_type": "text", "text": "   "},
        {
            "role": "user",
            "content_type": "text",
            "text": "second",
            "timestamp": "t2",
            "transcript_offset": 40,
            "transcript_index": 1,
        },
    ]
    assert user_requests(messages) == [
        {
            "text": "first",
            "timestamp": "t1",
            "transcript_offset": 10,
            "transcript_index": 0,
        },
        {
            "text": "second",
            "timestamp": "t2",
            "transcript_offset": 40,
            "transcript_index": 1,
        },
    ]
