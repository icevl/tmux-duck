"""Tests for the scoped file-download path resolver.

`resolve_scoped_path` is the security boundary for the /api/file endpoint: it
must only ever hand back an existing regular file located inside an allowed
root, and must resist `..` traversal and symlink escapes.
"""

from __future__ import annotations

import os
from pathlib import Path

from codexbot.web.api import resolve_scoped_path


def test_file_inside_root_resolves(tmp_path: Path) -> None:
    f = tmp_path / "diagrams" / "x.html"
    f.parent.mkdir()
    f.write_text("<html></html>")
    assert resolve_scoped_path(str(f), [tmp_path]) == f.resolve()


def test_file_outside_root_rejected(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("nope")
    assert resolve_scoped_path(str(outside), [root]) is None


def test_traversal_is_blocked(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("nope")
    sneaky = str(root / ".." / "secret.txt")
    assert resolve_scoped_path(sneaky, [root]) is None


def test_symlink_escape_is_blocked(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("nope")
    link = root / "link.txt"
    os.symlink(outside, link)
    # resolve() follows the symlink to outside the root → rejected.
    assert resolve_scoped_path(str(link), [root]) is None


def test_directory_is_not_a_file(tmp_path: Path) -> None:
    d = tmp_path / "sub"
    d.mkdir()
    assert resolve_scoped_path(str(d), [tmp_path]) is None


def test_missing_file_returns_none(tmp_path: Path) -> None:
    assert resolve_scoped_path(str(tmp_path / "nope.html"), [tmp_path]) is None


def test_empty_path_returns_none(tmp_path: Path) -> None:
    assert resolve_scoped_path("", [tmp_path]) is None


def test_multiple_roots(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    f = b / "file.md"
    f.write_text("# hi")
    assert resolve_scoped_path(str(f), [a, b]) == f.resolve()
