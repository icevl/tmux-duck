"""Regression tests for Claude transcript-path derivation.

Bug: on macOS `Path.resolve()` rewrites `/Users/…` to the data-volume firmlink
`/System/Volumes/Data/Users/…`, but Claude Code names its project dir from the
firmlink-visible `/Users/…` path. Deriving the transcript path from the resolved
form pointed at a nonexistent directory, so a session's messages never streamed
to the web UI. The fix strips the firmlink prefix before encoding.
"""

from __future__ import annotations

from codexbot.session import (
    _encode_claude_cwd,
    _strip_macos_firmlink,
    claude_transcript_path,
)


def test_strip_macos_firmlink() -> None:
    assert _strip_macos_firmlink("/System/Volumes/Data/Users/mike/x") == "/Users/mike/x"
    # Already-plain paths and Linux paths are untouched.
    assert _strip_macos_firmlink("/Users/mike/x") == "/Users/mike/x"
    assert _strip_macos_firmlink("/home/wavix/dev/mono") == "/home/wavix/dev/mono"
    # Only the exact firmlink prefix is stripped, not a lookalike.
    assert _strip_macos_firmlink("/System/Volumes/DataX/y") == "/System/Volumes/DataX/y"


def test_encode_matches_claude_dir_after_strip() -> None:
    firmlink = "/System/Volumes/Data/Users/mike/Projects/claude-smalltv"
    assert (
        _encode_claude_cwd(_strip_macos_firmlink(firmlink))
        == "-Users-mike-Projects-claude-smalltv"
    )


def test_claude_transcript_path_uses_plain_project_dir() -> None:
    p = claude_transcript_path(
        "910b65bd", "/System/Volumes/Data/Users/mike/Projects/claude-smalltv"
    )
    assert p is not None
    assert p.parent.name == "-Users-mike-Projects-claude-smalltv"
    assert p.name == "910b65bd.jsonl"


def test_claude_transcript_path_empty_inputs() -> None:
    assert claude_transcript_path("", "/Users/mike/x") is None
    assert claude_transcript_path("sid", "") is None
