"""Tests for the connectors layer: store CRUD, write-gate classifier,
hook-artifact generation, and the manager's hot-reload lifecycle.

These exercise everything that doesn't require a live Slack connection.
The conftest points CODEXBOT_DIR at a temp dir, so the manager test (which
uses the default store path) stays isolated from the real database.
"""

from __future__ import annotations

import pytest

from codexbot.connectors import store
from codexbot.connectors.base import (
    BaseConnector,
    register_connector_type,
)
from codexbot.connectors.classifier import classify_action
from codexbot.connectors.manager import ConnectorManager


# --- classifier ------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_name,tool_input,expected",
    [
        ("Read", {}, "read"),
        ("Grep", {}, "read"),
        ("Glob", {}, "read"),
        ("Edit", {"file_path": "/x"}, "write"),
        ("Write", {}, "write"),
        ("MultiEdit", {}, "write"),
        ("apply_patch", {}, "write"),
        ("Bash", {"command": "ls -la"}, "read"),
        ("Bash", {"command": "cat foo.txt"}, "read"),
        ("Bash", {"command": "git status"}, "read"),
        ("Bash", {"command": "git diff HEAD~1"}, "read"),
        ("Bash", {"command": "git rev-parse --show-toplevel"}, "read"),
        ("Bash", {"command": "git merge-base main HEAD"}, "read"),
        ("Bash", {"command": "git checkout -b feature"}, "write"),
        ("Bash", {"command": "FOO=1 grep x f"}, "read"),
        ("Bash", {"command": "rm -rf build"}, "write"),
        ("Bash", {"command": "git commit -m x"}, "write"),
        ("Bash", {"command": "git push"}, "write"),
        ("Bash", {"command": "echo hi > out.txt"}, "write"),
        ("Bash", {"command": "sed -i s/a/b/ f"}, "write"),
        ("Bash", {"command": 'psql -c "DROP TABLE users"'}, "write"),
        ("Bash", {"command": "npm install"}, "write"),
        ("Bash", {"command": "systemctl restart nginx"}, "write"),
        ("Bash", {"command": "curl http://x"}, "write"),
        # docker swarm / read subcommands must not be flagged as writes
        ("Bash", {"command": "docker service ls"}, "read"),
        ("Bash", {"command": "docker ps"}, "read"),
        ("Bash", {"command": "docker node ls"}, "read"),
        ("Bash", {"command": "docker service scale web=3"}, "write"),
        ("Bash", {"command": "docker run -d nginx"}, "write"),
        # ssh classifies the remote command it runs
        ("Bash", {"command": "ssh qa2 docker service ls"}, "read"),
        ("Bash", {"command": "ssh -p 2222 user@qa2 docker ps"}, "read"),
        ("Bash", {"command": "ssh qa2 rm -rf /tmp/x"}, "write"),
        ("Bash", {"command": "ssh qa2"}, "write"),  # bare login → conservative
        ("Bash", {"command": "service nginx restart"}, "write"),
        # compound commands: all-read → read, any-write → write
        ("Bash", {"command": "cd /x && grep foo docs/ | head -40"}, "read"),
        ("Bash", {"command": "cat a 2>/dev/null; echo hi; ls"}, "read"),
        ("Bash", {"command": "grep x f && rm -rf /y"}, "write"),
        ("Bash", {"command": "cd /x && echo done > out.txt"}, "write"),
        ("Bash", {"command": "sudo grep x /var/log/y"}, "read"),
        ("Bash", {"command": "sed -n '1,80p' f.md | grep -i lcr | head -60"}, "read"),
        ("Bash", {"command": "sed 's/a/b/' file"}, "read"),
        ("Bash", {"command": "sed -i 's/a/b/' file"}, "write"),
        # DB clients: read-only SQL passes, DML/DDL gates
        ("Bash", {"command": 'mysql db -e "SELECT id FROM users WHERE id=1"'}, "read"),
        (
            "Bash",
            {"command": 'mysql db -e "SELECT created_at, updated_at FROM t"'},
            "read",
        ),
        ("Bash", {"command": 'psql -c "SHOW TABLES"'}, "read"),
        ("Bash", {"command": 'mysql db -e "UPDATE users SET x=1"'}, "write"),
        ("Bash", {"command": 'mysql db -e "DROP TABLE t"'}, "write"),
        (
            "Bash",
            {"command": 'ssh qa1 "mysql wavix_p -e \\"SELECT email FROM users\\""'},
            "read",
        ),
        ("UnknownTool", {}, "write"),
        ("Bash", {}, "write"),  # empty command → safe default
    ],
)
def test_classify_action(tool_name, tool_input, expected):
    assert classify_action(tool_name, tool_input) == expected


def test_extra_read_commands_allowlist():
    cmd = 'cd /x && rtk grep -ri "LCR" docs/ 2>/dev/null | head -40'
    # rtk is unknown → write by default
    assert classify_action("Bash", {"command": cmd}) == "write"
    # …but trusted via extra_reads → read
    assert classify_action("Bash", {"command": cmd}, ("rtk",)) == "read"


def test_markdown_table_becomes_block_kit_table():
    from codexbot.connectors.slack import build_message_blocks

    md = (
        "Services:\n\n"
        "| Service | Replicas |\n"
        "|---------|----------|\n"
        "| auth | 1/1 |\n"
        "| sip | global |\n\n"
        "Done."
    )
    blocks = build_message_blocks(md)
    assert blocks is not None
    kinds = [b["type"] for b in blocks]
    assert kinds == ["section", "table", "section"]
    table = blocks[1]
    assert len(table["rows"]) == 3  # header + 2 data rows
    assert [c["text"] for c in table["rows"][0]] == ["Service", "Replicas"]
    assert [c["text"] for c in table["rows"][1]] == ["auth", "1/1"]
    assert all(c["type"] == "raw_text" for row in table["rows"] for c in row)


def test_combined_instructions_always_appends_baked():
    from codexbot.connectors.bridge import BAKED_INSTRUCTIONS, combined_instructions

    # baked guidance is always present
    assert combined_instructions("") == BAKED_INSTRUCTIONS
    out = combined_instructions("Check docs/ first.")
    assert out.startswith("Check docs/ first.")
    assert out.endswith(BAKED_INSTRUCTIONS)
    assert "AskUserQuestion" in out


def test_no_table_returns_none():
    from codexbot.connectors.slack import build_message_blocks

    assert build_message_blocks("just prose, no table here") is None
    # a pipe without a separator row is not a table
    assert build_message_blocks("a | b but no separator") is None


def test_compound_split_preserves_grep_pattern():
    from codexbot.connectors.classifier import classify_shell

    # the escaped pipe inside the grep pattern must not split the command
    assert classify_shell('grep "a\\|b\\|c" file', ("rtk",)) == "read"


def test_docker_exec_and_shell_c_unwrapping():
    from codexbot.connectors.classifier import classify_shell as cs

    # SELECT reached via docker exec / sh -c is still a read
    assert cs(r"""docker exec abc mysql -e "SELECT 1" """) == "read"
    assert cs(r"""docker exec abc sh -lc 'mysql -e "SELECT id FROM t"' """) == "read"
    assert cs(r"""sh -lc 'mysql -e "SELECT 1"' """) == "read"
    assert (
        cs(r"""ssh -p 1355 host "docker exec abc sh -lc 'mysql -e \"SELECT 1\"'" """)
        == "read"
    )
    # but mutations through the same wrappers stay writes
    assert cs("docker exec abc rm -rf /data") == "write"
    assert cs('bash -c "rm -rf /x"') == "write"
    assert cs('docker exec abc psql -c "UPDATE t SET x=1"') == "write"


# --- store CRUD ------------------------------------------------------------


@pytest.fixture
def db(tmp_path):
    return tmp_path / "connectors.sqlite"


def test_connector_crud_roundtrip(db):
    rec = store.create_connector(
        type="slack",
        name="My bot",
        config={"cwd": "/work", "bot_token": "xoxb-x"},
        enabled=True,
        path=db,
    )
    assert rec.enabled is True
    assert rec.config["cwd"] == "/work"

    fetched = store.get_connector(rec.id, path=db)
    assert fetched is not None
    assert fetched.name == "My bot"

    assert len(store.list_connectors(path=db)) == 1
    assert len(store.list_connectors(enabled_only=True, path=db)) == 1

    updated = store.update_connector(rec.id, name="Renamed", enabled=False, path=db)
    assert updated is not None
    assert updated.name == "Renamed"
    assert updated.enabled is False
    assert len(store.list_connectors(enabled_only=True, path=db)) == 0

    assert store.delete_connector(rec.id, path=db) is True
    assert store.get_connector(rec.id, path=db) is None
    assert store.delete_connector(rec.id, path=db) is False


def test_session_mapping(db):
    rec = store.create_connector(type="slack", name="b", config={}, path=db)
    store.upsert_session_mapping(
        connector_id=rec.id,
        external_id="C1:1.23",
        window_id="@7",
        runtime="claude",
        cwd="/w",
        path=db,
    )
    m = store.get_session_mapping(rec.id, "C1:1.23", path=db)
    assert m is not None and m.window_id == "@7" and m.runtime == "claude"

    # upsert is idempotent on (connector, external) and updates the window
    store.upsert_session_mapping(
        connector_id=rec.id,
        external_id="C1:1.23",
        window_id="@9",
        runtime="claude",
        cwd="/w",
        path=db,
    )
    assert store.get_session_mapping(rec.id, "C1:1.23", path=db).window_id == "@9"

    assert store.find_mapping_by_window("@9", path=db).external_id == "C1:1.23"
    assert len(store.list_session_mappings(rec.id, path=db)) == 1

    store.delete_session_mapping(rec.id, "C1:1.23", path=db)
    assert store.get_session_mapping(rec.id, "C1:1.23", path=db) is None


def test_session_mapping_activity_timestamp(db):
    import time as _time

    rec = store.create_connector(type="slack", name="b", config={}, path=db)
    store.upsert_session_mapping(
        connector_id=rec.id,
        external_id="C1:1",
        window_id="@1",
        runtime="codex",
        cwd="/w",
        path=db,
    )
    first = store.get_session_mapping(rec.id, "C1:1", path=db).last_activity_at
    assert first  # stamped on upsert

    _time.sleep(0.01)
    store.touch_session_mapping_by_window("@1", path=db)
    bumped = store.get_session_mapping(rec.id, "C1:1", path=db).last_activity_at
    assert bumped >= first  # ISO-8601 (same format) sorts chronologically


def test_migration_adds_last_activity_column(tmp_path):
    import sqlite3

    db = tmp_path / "old.sqlite"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE connectors(
            id TEXT PRIMARY KEY, type TEXT, name TEXT, enabled INTEGER,
            config_json TEXT, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE connector_sessions(
            connector_id TEXT, external_id TEXT, window_id TEXT, runtime TEXT,
            cwd TEXT, created_at TEXT, PRIMARY KEY(connector_id, external_id)
        );
        """
    )
    conn.execute(
        "INSERT INTO connector_sessions VALUES "
        "('c','e','@1','codex','/w','2020-01-01T00:00:00Z')"
    )
    conn.commit()
    conn.close()

    # _connect runs the migration; created_at backfills last_activity_at.
    m = store.get_session_mapping("c", "e", path=db)
    assert m is not None
    assert m.last_activity_at == "2020-01-01T00:00:00Z"


def test_idle_seconds():
    from datetime import UTC, datetime, timedelta

    from codexbot.connectors.slack import IDLE_TTL_SECONDS, _idle_seconds

    assert _idle_seconds(None) is None
    assert _idle_seconds("not-a-date") is None
    recent = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    assert _idle_seconds(recent) < 5
    old = (datetime.now(UTC) - timedelta(days=6)).isoformat().replace("+00:00", "Z")
    assert _idle_seconds(old) > IDLE_TTL_SECONDS


def test_session_mappings_cascade_on_connector_delete(db):
    rec = store.create_connector(type="slack", name="b", config={}, path=db)
    store.upsert_session_mapping(
        connector_id=rec.id,
        external_id="C1:1",
        window_id="@1",
        runtime="codex",
        cwd="/w",
        path=db,
    )
    store.delete_connector(rec.id, path=db)
    # FK cascade removes the orphaned mapping.
    assert store.list_session_mappings(rec.id, path=db) == []


# --- hook artifacts --------------------------------------------------------


def test_ensure_claude_hook_settings_generates_files():
    import json
    from pathlib import Path

    from codexbot.connectors import approval

    path = approval.ensure_claude_hook_settings()
    data = json.loads(Path(path).read_text())
    hook = data["hooks"]["PreToolUse"][0]
    assert "Edit" in hook["matcher"] and "Bash" in hook["matcher"]
    assert "Read" not in hook["matcher"]  # reads must never hit the gate
    secret = approval.approval_secret()
    script = approval.connectors_state_dir() / "approval_hook.py"
    src = script.read_text()
    assert secret in src
    assert "approve-tool" in src


# --- type registry / drop-in discovery -------------------------------------


def test_auto_discovery_registers_slack():
    from codexbot.connectors.base import CONNECTOR_TYPES
    from codexbot.connectors.manager import _load_connector_implementations

    _load_connector_implementations()
    assert "slack" in CONNECTOR_TYPES


def test_connector_types_expose_schema():
    from codexbot.connectors.base import (
        list_connector_types,
        secret_keys_for_type,
    )
    from codexbot.connectors.manager import _load_connector_implementations

    _load_connector_implementations()
    types = {t["type"]: t for t in list_connector_types()}
    assert "slack" in types
    slack = types["slack"]
    assert slack["label"] == "Slack"
    keys = {f["key"]: f for f in slack["fields"]}
    assert keys["cwd"]["type"] == "directory"
    assert keys["default_runtime"]["type"] == "runtime"
    assert keys["bot_token"]["type"] == "secret"
    assert secret_keys_for_type("slack") == ("bot_token", "app_token")
    assert secret_keys_for_type("does_not_exist") == ()


# --- Slack ACL / read-only -------------------------------------------------


def _slack(config):
    from codexbot.connectors.base import ConnectorContext
    from codexbot.connectors.slack import SlackConnector
    from codexbot.connectors.store import ConnectorRecord

    rec = ConnectorRecord(
        id="c",
        type="slack",
        name="n",
        enabled=True,
        config=config,
        created_at="",
        updated_at="",
    )
    return SlackConnector(rec, ConnectorContext())


def test_acl_use_permission():
    c = _slack({"acl": [{"user": "U1", "write": True}, {"user": "U2", "write": False}]})
    assert c._is_allowed("C1", "U1") is True
    assert c._is_allowed("C1", "U2") is True
    assert c._is_allowed("C1", "U3") is False  # not in non-empty ACL
    # empty ACL → anyone may use
    assert _slack({})._is_allowed("C1", "Uany") is True


def test_acl_write_permission():
    c = _slack({"acl": [{"user": "U1", "write": True}, {"user": "U2", "write": False}]})
    c._last_user["@w"] = "U1"
    assert c._may_write("@w") is True
    c._last_user["@w"] = "U2"
    assert c._may_write("@w") is False  # in ACL but no Write flag
    c._last_user["@w"] = "U3"
    assert c._may_write("@w") is False  # not in ACL


def test_read_only_blocks_all_writes():
    c = _slack({"read_only": True, "acl": [{"user": "U1", "write": True}]})
    c._last_user["@w"] = "U1"
    assert c._may_write("@w") is False  # master switch overrides Write flag


def test_no_driving_user_denies_write():
    c = _slack({"acl": [{"user": "U1", "write": True}]})
    assert c._may_write("@unknown") is False


def test_acl_field_in_schema():
    from codexbot.connectors.slack import SlackConnector

    fields = {f.key: f for f in SlackConnector.config_schema()}
    assert fields["acl"].type == "acl"
    assert fields["read_only"].type == "bool"


# --- manager hot-reload ----------------------------------------------------


_dummy_events: list[tuple[str, str]] = []


@register_connector_type("test_dummy")
class _DummyConnector(BaseConnector):
    async def start(self) -> None:
        _dummy_events.append(("start", self.id))

    async def stop(self) -> None:
        _dummy_events.append(("stop", self.id))


async def test_manager_hot_reload():
    _dummy_events.clear()
    mgr = ConnectorManager()
    rec = store.create_connector(type="test_dummy", name="d", config={}, enabled=False)
    try:
        await mgr.start(monitor=None, bot=None)
        assert mgr.is_running(rec.id) is False  # disabled at boot

        store.update_connector(rec.id, enabled=True)
        await mgr.reload(rec.id)
        assert mgr.is_running(rec.id) is True

        store.update_connector(rec.id, enabled=False)
        await mgr.reload(rec.id)
        assert mgr.is_running(rec.id) is False

        await mgr.stop()
    finally:
        store.delete_connector(rec.id)

    assert ("start", rec.id) in _dummy_events
    assert ("stop", rec.id) in _dummy_events


def test_cli_export_import_roundtrip(tmp_path):
    import json

    from codexbot.connectors import cli

    rec = store.create_connector(
        type="slack",
        name="cli-rt",
        config={"cwd": "/x", "bot_token": "xoxb-secret"},
        enabled=True,
    )
    try:
        out = tmp_path / "c.json"
        assert cli.main(["export", rec.id, "--out", str(out)]) == 0
        data = json.loads(out.read_text())
        assert data["type"] == "slack"
        assert data["config"]["bot_token"] == "xoxb-secret"  # secrets travel

        assert cli.main(["import", str(out)]) == 0
        clones = [c for c in store.list_connectors() if c.name == "cli-rt"]
        assert len(clones) == 2  # original + imported copy
    finally:
        for c in store.list_connectors():
            if c.name == "cli-rt":
                store.delete_connector(c.id)


async def test_manager_unknown_type_is_skipped():
    mgr = ConnectorManager()
    rec = store.create_connector(type="nope_unknown", name="x", config={}, enabled=True)
    try:
        await mgr.start(monitor=None, bot=None)
        # No implementation registered for this type → silently not running.
        assert mgr.is_running(rec.id) is False
        await mgr.stop()
    finally:
        store.delete_connector(rec.id)
