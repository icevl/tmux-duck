"""Durable SQLite-backed connector configuration and thread→window map.

Mirrors the raw-``sqlite3`` style used by ``search/queue.py`` (no ORM).
Two tables:

  - ``connectors`` — one row per configured connector. ``config_json``
    holds the type-specific payload (credentials, custom instructions,
    default runtime, default cwd, approval policy).
  - ``connector_sessions`` — maps a connector's external conversation id
    (e.g. a Slack ``channel:thread_ts``) to the tmux window that backs it,
    so a thread keeps talking to the same agent.

The database file is created with ``0600`` permissions because it stores
bot credentials, matching how ``web_ui_secret`` is persisted.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..utils import codexbot_dir

CONNECTORS_SCHEMA_VERSION = 1
CONNECTORS_DB_FILENAME = "connectors.sqlite"


def connectors_db_path() -> Path:
    """Return the connector-owned SQLite database path."""
    return codexbot_dir() / CONNECTORS_DB_FILENAME


@dataclass(frozen=True)
class ConnectorRecord:
    """One configured connector row."""

    id: str
    type: str
    name: str
    enabled: bool
    config: dict[str, Any]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SessionMapping:
    """A connector's external conversation bound to a tmux window."""

    connector_id: str
    external_id: str
    window_id: str
    runtime: str
    cwd: str
    created_at: str
    last_activity_at: str | None = None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or connectors_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    created = not db_path.exists()
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    _init_schema(conn)
    if created:
        try:
            os.chmod(db_path, 0o600)
        except OSError:
            pass
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS connectors (
            id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 0,
            config_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS connector_sessions (
            connector_id TEXT NOT NULL,
            external_id TEXT NOT NULL,
            window_id TEXT NOT NULL,
            runtime TEXT NOT NULL,
            cwd TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_activity_at TEXT,
            PRIMARY KEY (connector_id, external_id),
            FOREIGN KEY (connector_id) REFERENCES connectors(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_connector_sessions_window
            ON connector_sessions(window_id);
        """
    )
    # Migration for databases created before last_activity_at existed.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(connector_sessions)")}
    if "last_activity_at" not in cols:
        conn.execute("ALTER TABLE connector_sessions ADD COLUMN last_activity_at TEXT")
        conn.execute(
            "UPDATE connector_sessions SET last_activity_at = created_at "
            "WHERE last_activity_at IS NULL"
        )
    conn.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES('schema_version', ?)",
        (str(CONNECTORS_SCHEMA_VERSION),),
    )
    conn.commit()


def _row_to_record(row: sqlite3.Row) -> ConnectorRecord:
    try:
        config = json.loads(row["config_json"])
    except (json.JSONDecodeError, TypeError):
        config = {}
    if not isinstance(config, dict):
        config = {}
    return ConnectorRecord(
        id=row["id"],
        type=row["type"],
        name=row["name"],
        enabled=bool(row["enabled"]),
        config=config,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _row_to_mapping(row: sqlite3.Row) -> SessionMapping:
    return SessionMapping(
        connector_id=row["connector_id"],
        external_id=row["external_id"],
        window_id=row["window_id"],
        runtime=row["runtime"],
        cwd=row["cwd"],
        created_at=row["created_at"],
        last_activity_at=row["last_activity_at"],
    )


# --- connectors CRUD -------------------------------------------------------


def list_connectors(
    *, enabled_only: bool = False, path: Path | None = None
) -> list[ConnectorRecord]:
    """Return configured connectors ordered by creation time."""
    conn = _connect(path)
    try:
        if enabled_only:
            rows = conn.execute(
                "SELECT * FROM connectors WHERE enabled = 1 ORDER BY created_at"
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM connectors ORDER BY created_at"
            ).fetchall()
        return [_row_to_record(r) for r in rows]
    finally:
        conn.close()


def get_connector(
    connector_id: str, *, path: Path | None = None
) -> ConnectorRecord | None:
    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT * FROM connectors WHERE id = ?", (connector_id,)
        ).fetchone()
        return _row_to_record(row) if row else None
    finally:
        conn.close()


def create_connector(
    *,
    type: str,
    name: str,
    config: dict[str, Any],
    enabled: bool = False,
    path: Path | None = None,
) -> ConnectorRecord:
    now = _now_iso()
    connector_id = f"conn_{uuid.uuid4().hex[:12]}"
    conn = _connect(path)
    try:
        conn.execute(
            """
            INSERT INTO connectors(id, type, name, enabled, config_json,
                                   created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                connector_id,
                type,
                name,
                1 if enabled else 0,
                json.dumps(config, ensure_ascii=False),
                now,
                now,
            ),
        )
        conn.commit()
    finally:
        conn.close()
    record = get_connector(connector_id, path=path)
    assert record is not None
    return record


def update_connector(
    connector_id: str,
    *,
    name: str | None = None,
    config: dict[str, Any] | None = None,
    enabled: bool | None = None,
    path: Path | None = None,
) -> ConnectorRecord | None:
    """Patch a connector. Only the provided fields change."""
    sets: list[str] = []
    params: list[Any] = []
    if name is not None:
        sets.append("name = ?")
        params.append(name)
    if config is not None:
        sets.append("config_json = ?")
        params.append(json.dumps(config, ensure_ascii=False))
    if enabled is not None:
        sets.append("enabled = ?")
        params.append(1 if enabled else 0)
    if not sets:
        return get_connector(connector_id, path=path)
    sets.append("updated_at = ?")
    params.append(_now_iso())
    params.append(connector_id)
    conn = _connect(path)
    try:
        cur = conn.execute(
            f"UPDATE connectors SET {', '.join(sets)} WHERE id = ?",
            params,
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
    finally:
        conn.close()
    return get_connector(connector_id, path=path)


def delete_connector(connector_id: str, *, path: Path | None = None) -> bool:
    conn = _connect(path)
    try:
        cur = conn.execute("DELETE FROM connectors WHERE id = ?", (connector_id,))
        conn.commit()
        return cur.rowcount > 0
    finally:
        conn.close()


# --- thread→window mapping -------------------------------------------------


def get_session_mapping(
    connector_id: str, external_id: str, *, path: Path | None = None
) -> SessionMapping | None:
    conn = _connect(path)
    try:
        row = conn.execute(
            """
            SELECT * FROM connector_sessions
            WHERE connector_id = ? AND external_id = ?
            """,
            (connector_id, external_id),
        ).fetchone()
        return _row_to_mapping(row) if row else None
    finally:
        conn.close()


def upsert_session_mapping(
    *,
    connector_id: str,
    external_id: str,
    window_id: str,
    runtime: str,
    cwd: str,
    path: Path | None = None,
) -> None:
    conn = _connect(path)
    try:
        now = _now_iso()
        conn.execute(
            """
            INSERT INTO connector_sessions(connector_id, external_id, window_id,
                                           runtime, cwd, created_at,
                                           last_activity_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(connector_id, external_id) DO UPDATE SET
                window_id = excluded.window_id,
                runtime = excluded.runtime,
                cwd = excluded.cwd,
                last_activity_at = excluded.last_activity_at
            """,
            (connector_id, external_id, window_id, runtime, cwd, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def touch_session_mapping_by_window(
    window_id: str, *, path: Path | None = None
) -> None:
    """Bump last_activity_at for the mapping owning ``window_id``."""
    conn = _connect(path)
    try:
        conn.execute(
            "UPDATE connector_sessions SET last_activity_at = ? WHERE window_id = ?",
            (_now_iso(), window_id),
        )
        conn.commit()
    finally:
        conn.close()


def delete_session_mapping(
    connector_id: str, external_id: str, *, path: Path | None = None
) -> None:
    conn = _connect(path)
    try:
        conn.execute(
            """
            DELETE FROM connector_sessions
            WHERE connector_id = ? AND external_id = ?
            """,
            (connector_id, external_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_session_mappings(
    connector_id: str, *, path: Path | None = None
) -> list[SessionMapping]:
    """All conversation→window mappings owned by a connector."""
    conn = _connect(path)
    try:
        rows = conn.execute(
            "SELECT * FROM connector_sessions WHERE connector_id = ?",
            (connector_id,),
        ).fetchall()
        return [_row_to_mapping(r) for r in rows]
    finally:
        conn.close()


def find_mapping_by_window(
    window_id: str, *, path: Path | None = None
) -> SessionMapping | None:
    """Reverse lookup: which connector conversation owns this window."""
    conn = _connect(path)
    try:
        row = conn.execute(
            "SELECT * FROM connector_sessions WHERE window_id = ? LIMIT 1",
            (window_id,),
        ).fetchone()
        return _row_to_mapping(row) if row else None
    finally:
        conn.close()


__all__ = [
    "CONNECTORS_DB_FILENAME",
    "CONNECTORS_SCHEMA_VERSION",
    "ConnectorRecord",
    "SessionMapping",
    "connectors_db_path",
    "create_connector",
    "delete_connector",
    "delete_session_mapping",
    "find_mapping_by_window",
    "get_connector",
    "get_session_mapping",
    "list_connectors",
    "list_session_mappings",
    "touch_session_mapping_by_window",
    "update_connector",
    "upsert_session_mapping",
]
