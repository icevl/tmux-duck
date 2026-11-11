"""Instructions Codi gives the agents it launches about its own chat.

The user reads the session in Codi's web UI / Telegram, not in the terminal,
so agents need to know how to put an image in front of them. Claude gets
this via ``--append-system-prompt-file``, Codex via ``developer_instructions``
(added alongside its own instructions, not replacing them).
"""

from __future__ import annotations

import shlex
from pathlib import Path

from .utils import codexbot_dir

# One line, no double quotes or backslashes: Codex takes it as a TOML string.
CHAT_INSTRUCTIONS = (
    "The user follows this session in Codi, a chat UI (web and Telegram) that "
    "mirrors your replies. To show the user an image - a screenshot of the app "
    "or game you are working on, a render, a chart - save it as PNG, JPEG, "
    "WebP or GIF and put its absolute path in your reply as Markdown, e.g. "
    "![Main menu after the change](/absolute/path/screenshot.png); Codi shows "
    "it in the chat. Images you open with your image viewing tool are shown "
    "to the user too. When the user asks to see how something looks, take a "
    "screenshot and show it this way."
)


def claude_instructions_file() -> Path:
    """The instructions as a file for Claude, rewritten only when changed."""
    path = codexbot_dir() / "agent" / "codi-chat.md"
    text = CHAT_INSTRUCTIONS + "\n"
    try:
        if path.read_text(encoding="utf-8") == text:
            return path
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def codex_instructions_flag() -> str:
    """``-c developer_instructions="..."`` for the Codex command line."""
    return f"-c {shlex.quote(f'developer_instructions="{CHAT_INSTRUCTIONS}"')}"
