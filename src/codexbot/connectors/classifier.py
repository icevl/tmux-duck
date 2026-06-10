"""Classify an agent tool call as a read or a mutating write.

Used by the write-gate: reads pass through untouched, writes are routed to
an external approver (Slack). Tool names cover both Claude Code (``Edit``,
``Write``, ``Bash`` …) and Codex (``apply_patch``, ``shell`` …). For shell
commands the verdict is conservative — anything not clearly read-only is
treated as a write so the safe default is "ask".
"""

from __future__ import annotations

import re
import shlex
from typing import Any, Literal

Action = Literal["read", "write"]

# Tools that never mutate state.
READ_TOOLS = {
    "Read",
    "Glob",
    "Grep",
    "LS",
    "NotebookRead",
    "WebFetch",
    "WebSearch",
    "TodoWrite",  # internal task list only
}

# Tools that always mutate the workspace.
WRITE_TOOLS = {
    "Edit",
    "Write",
    "MultiEdit",
    "NotebookEdit",
    "apply_patch",  # Codex file edits
}

# Shell tool names across runtimes.
SHELL_TOOLS = {"Bash", "shell", "local_shell"}

# First-token allowlist of read-only shell programs.
_READ_PROGRAMS = {
    "ls",
    "cat",
    "head",
    "tail",
    "less",
    "more",
    "bat",
    "grep",
    "rg",
    "egrep",
    "fgrep",
    "ag",
    "find",
    "fd",
    "tree",
    "stat",
    "file",
    "wc",
    "realpath",
    "dirname",
    "basename",
    "readlink",
    "pwd",
    "cd",
    "echo",
    "printf",
    "whoami",
    "id",
    "hostname",
    "date",
    "which",
    "type",
    "env",
    "uname",
    "printenv",
    "ps",
    "top",
    "df",
    "du",
    "free",
    "diff",
    "cmp",
    "sort",
    "uniq",
    "cut",
    "awk",
    "sed",
    "tr",
    "nl",
    "tac",
    "rev",
    "comm",
    "paste",
    "strings",
    "md5sum",
    "sha256sum",
    "sha1sum",
    "xxd",
    "od",
    "hexdump",
    "base64",
    "fold",
    "expand",
    "join",
    "look",
    "jq",
    "yq",
    "column",
}

# Command wrappers that precede the real command; stripped before classifying.
_WRAPPERS = {"sudo", "doas", "env", "command", "nohup", "xargs"}

# Read-only git subcommands (their common form). Anything else → write.
_GIT_READ_SUBCOMMANDS = {
    "status", "diff", "log", "show", "branch", "remote", "blame", "ls-files",
    "rev-parse", "rev-list", "describe", "name-rev", "merge-base",
    "for-each-ref", "symbolic-ref", "show-ref", "ls-tree", "ls-remote",
    "cat-file", "reflog", "shortlog", "whatchanged", "var", "grep",
    "count-objects", "cherry", "range-diff", "diff-tree", "diff-index",
}

# Substrings that force a write verdict even inside an otherwise read command
# (redirection, in-place edits, chained mutations). Note: no bare "service "
# here — it false-matched `docker service ls`; daemon control is handled by
# the program dispatch below instead.
_WRITE_SIGNALS = (
    "|& tee",
    " tee ",
    "rm ",
    "rmdir",
    "mv ",
    "cp ",
    "sed -i",
    "sed --in-place",
    "truncate",
    "dd ",
    "mkfs",
    "chmod",
    "chown",
    "reboot",
    "shutdown",
)

# A redirection whose target is a real file is a write. Redirects to /dev/*
# (e.g. `2>/dev/null`) and fd duplications (`2>&1`) are not.
_REDIR_RE = re.compile(r'(?:^|\s)\d*&?>>?\s*("?)([^\s"&|;<>]+)')


def _rejoin(tokens: list[str]) -> str:
    """Rebuild a command string from tokens.

    A single token already IS the command string (the remote/inner command was
    one quoted arg) — return it verbatim so it re-parses as a command. Multiple
    tokens are re-quoted with shlex.join so per-token grouping survives.
    """
    if len(tokens) == 1:
        return tokens[0]
    return shlex.join(tokens)


def _has_file_redirect(cmd: str) -> bool:
    for match in _REDIR_RE.finditer(cmd):
        target = match.group(2)
        if target and not target.startswith("/dev/"):
            return True
    return False


# Service/daemon control programs → always write.
_SERVICE_CONTROL = {"systemctl", "launchctl", "service", "svcadm", "rc-service"}

# `docker <verb>` read-only subcommands.
_DOCKER_READ_VERBS = {
    "ps",
    "images",
    "version",
    "info",
    "logs",
    "stats",
    "top",
    "port",
    "diff",
    "history",
    "events",
    "inspect",
    "search",
}
# `docker <noun> <action>` — these nouns are read only for these actions.
_DOCKER_NOUNS = {
    "service",
    "node",
    "stack",
    "network",
    "volume",
    "container",
    "config",
    "secret",
    "system",
    "image",
    "context",
    "swarm",
    "plugin",
}
_DOCKER_NOUN_READ_ACTIONS = {"ls", "ps", "inspect", "logs", "df"}

# DB clients: classify by the SQL they run (read-only SELECT/SHOW/… vs DML/DDL).
_DB_CLIENTS = {
    "mysql",
    "mariadb",
    "psql",
    "sqlite3",
    "clickhouse-client",
    "mongosh",
    "cqlsh",
    "duckdb",
}
_SQL_WRITE_RE = re.compile(
    r"\b(insert|update|delete|drop|alter|create|truncate|replace|merge|"
    r"grant|revoke|rename|call|load\s+data|lock|unlock)\b",
    re.IGNORECASE,
)
_SQL_READ_RE = re.compile(
    r"\b(select|show|describe|desc|explain|with|pragma|use|count)\b",
    re.IGNORECASE,
)


def _classify_db(args: list[str]) -> Action:
    """Read if the SQL is SELECT/SHOW/…, write if it contains any DML/DDL."""
    blob = " ".join(args)
    if _SQL_WRITE_RE.search(blob):
        return "write"
    if _SQL_READ_RE.search(blob):
        return "read"
    return "write"  # interactive client / no recognizable query → ask


def classify_action(
    tool_name: str,
    tool_input: dict[str, Any] | None,
    extra_reads: tuple[str, ...] | frozenset[str] | list[str] = (),
) -> Action:
    """Return ``"read"`` or ``"write"`` for a tool call.

    ``extra_reads`` is a list of additional first-word commands (e.g. custom
    tools like ``rtk``) the operator trusts as read-only.
    """
    if tool_name in READ_TOOLS:
        return "read"
    if tool_name in WRITE_TOOLS:
        return "write"
    if tool_name in SHELL_TOOLS:
        command = ""
        if isinstance(tool_input, dict):
            command = str(tool_input.get("command") or tool_input.get("cmd") or "")
        return classify_shell(command, extra_reads)
    # Unknown tool → safe default is to ask.
    return "write"


def classify_shell(
    command: str,
    extra_reads: tuple[str, ...] | frozenset[str] | list[str] = (),
) -> Action:
    """Classify a shell command. Compound commands (``;`` ``&&`` ``|`` …) are
    split and each part classified — write if ANY part writes. Conservative:
    an unrecognized command ⇒ write.
    """
    cmd = command.strip()
    if not cmd:
        return "write"
    extra = {e.strip() for e in extra_reads if e and e.strip()}
    segments = [s for s in _split_top_level(cmd) if s.strip()]
    if not segments:
        return "write"
    verdicts = [_classify_segment(s, extra) for s in segments]
    return "write" if any(v == "write" for v in verdicts) else "read"


def _classify_segment(segment: str, extra: set[str]) -> Action:
    cmd = segment.strip()
    if not cmd:
        return "read"
    low = cmd.lower()
    if any(sig in low for sig in _WRITE_SIGNALS):
        return "write"
    if _has_file_redirect(cmd):
        return "write"

    try:
        tokens = shlex.split(cmd)
    except ValueError:
        return "write"
    tokens = _strip_prefix(tokens)
    if not tokens:
        return "read"
    program = tokens[0].split("/")[-1]
    args = tokens[1:]

    # ssh: classify the remote command it would run.
    if program == "ssh":
        remote = _ssh_remote_command(args)
        return classify_shell(remote, tuple(extra)) if remote else "write"

    if program in {"docker", "podman"}:
        return _classify_docker(args)

    if program in _DB_CLIENTS:
        return _classify_db(args)

    if program in _SERVICE_CONTROL:
        return "write"

    if program == "git":
        sub = args[0] if args else ""
        if sub in _GIT_READ_SUBCOMMANDS:
            return "read"
        return "write"

    # sh/bash -c '<cmd>' → classify the wrapped command.
    if program in {"sh", "bash", "zsh", "dash", "ash"}:
        inner = _shell_c_command(args)
        return classify_shell(inner) if inner is not None else "write"

    if program in _READ_PROGRAMS or program in extra:
        return "read"

    # Mutating package/DB/build verbs → write.
    if re.search(
        r"\b(install|update|upgrade|migrate|drop|delete|insert|"
        r"alter|truncate|create|push|commit|publish|deploy|restart)\b",
        low,
    ):
        return "write"

    return "write"


def _strip_prefix(tokens: list[str]) -> list[str]:
    """Drop leading env assignments and command wrappers (sudo/env/…)."""
    changed = True
    while changed and tokens:
        changed = False
        while tokens and "=" in tokens[0] and not tokens[0].startswith("-"):
            tokens = tokens[1:]
            changed = True
        if tokens and tokens[0].split("/")[-1] in _WRAPPERS:
            tokens = tokens[1:]
            changed = True
            while tokens and tokens[0].startswith("-"):
                tokens = tokens[1:]
    return tokens


def _split_top_level(cmd: str) -> list[str]:
    """Split a command on top-level ``;`` ``&&`` ``||`` ``|`` and newlines.

    Operators inside quotes or ``$( )`` / backticks are ignored, so a grep
    pattern like ``"a\\|b"`` is never split.
    """
    segments: list[str] = []
    buf: list[str] = []
    i, n = 0, len(cmd)
    sq = dq = False
    depth = 0
    while i < n:
        c = cmd[i]
        two = cmd[i : i + 2]
        # Backslash escape (outside single quotes): keep the next char literal
        # so `\"` inside ssh "... \"SQL\"" doesn't prematurely close a quote.
        if c == "\\" and not sq and i + 1 < n:
            buf.append(cmd[i : i + 2])
            i += 2
            continue
        if sq:
            buf.append(c)
            if c == "'":
                sq = False
            i += 1
            continue
        if dq:
            buf.append(c)
            if c == '"':
                dq = False
            i += 1
            continue
        if c == "'":
            sq = True
            buf.append(c)
            i += 1
            continue
        if c == '"':
            dq = True
            buf.append(c)
            i += 1
            continue
        if two == "$(" or c == "`":
            depth += 1
            buf.append(two if two == "$(" else c)
            i += 2 if two == "$(" else 1
            continue
        if c == "(":
            depth += 1
            buf.append(c)
            i += 1
            continue
        if c == ")":
            depth = max(0, depth - 1)
            buf.append(c)
            i += 1
            continue
        if depth > 0:
            buf.append(c)
            i += 1
            continue
        if two in ("&&", "||"):
            segments.append("".join(buf))
            buf = []
            i += 2
            continue
        if c in (";", "|", "\n"):
            segments.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    if buf:
        segments.append("".join(buf))
    return segments


def _ssh_remote_command(args: list[str]) -> str:
    """Extract the remote command from `ssh [opts] host <command…>` args."""
    value_flags = {
        "-p",
        "-i",
        "-o",
        "-l",
        "-F",
        "-L",
        "-R",
        "-D",
        "-E",
        "-b",
        "-c",
        "-m",
        "-O",
        "-S",
        "-W",
        "-J",
        "-Q",
    }
    i = 0
    while i < len(args):
        tok = args[i]
        if tok.startswith("-"):
            i += 2 if tok in value_flags else 1
        else:
            break  # this token is the host (or user@host)
    # shlex.join re-quotes so nested command grouping survives re-parsing.
    return _rejoin(args[i + 1 :])  # everything after the host


def _classify_docker(args: list[str]) -> Action:
    """Classify a docker/podman invocation (read subcommands vs mutations)."""
    i = 0
    while i < len(args) and args[i].startswith("-"):
        i += 1
    if i >= len(args):
        return "read"  # bare `docker` prints help
    sub = args[i]
    rest = args[i + 1 :]
    if sub in _DOCKER_READ_VERBS:
        return "read"
    if sub in _DOCKER_NOUNS:
        j = 0
        while j < len(rest) and rest[j].startswith("-"):
            j += 1
        action = rest[j] if j < len(rest) else ""
        return "read" if action in _DOCKER_NOUN_READ_ACTIONS else "write"
    if sub == "exec":
        inner = _docker_exec_command(rest)
        return classify_shell(inner) if inner else "write"
    return "write"


def _docker_exec_command(tokens: list[str]) -> str:
    """Extract the command from `docker exec [opts] <container> <cmd…>`."""
    value_flags = {"-e", "--env", "-u", "--user", "-w", "--workdir", "--env-file"}
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok.startswith("-"):
            i += 2 if tok in value_flags else 1
        else:
            break  # the container name
    return _rejoin(tokens[i + 1 :])


_SHELL_C_RE = re.compile(r"-[a-z]*c")


def _shell_c_command(args: list[str]) -> str | None:
    """Return the command string from `sh/bash -c '<cmd>'` (or -lc/-ic), else None."""
    for idx, arg in enumerate(args):
        if _SHELL_C_RE.fullmatch(arg) and idx + 1 < len(args):
            return args[idx + 1]
    return None


__all__ = ["Action", "classify_action", "classify_shell", "READ_TOOLS", "WRITE_TOOLS"]
