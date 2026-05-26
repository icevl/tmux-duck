"""Durable SQLite-backed live search queue state."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from .contracts import (
    SearchBackfillDocument,
    SearchQueueItemStatus,
    SearchQueueSnapshot,
    SearchRowIdentity,
)
from .state import queue_db_path

QUEUE_SCHEMA_VERSION = 1
DEFAULT_LEASE_SECONDS = 300
DEFAULT_MAX_ATTEMPTS = 3
MAX_ERROR_LENGTH = 500


@dataclass(frozen=True)
class SearchQueueItem:
    """One leased or inspectable live search queue row."""

    queue_id: str
    identity: SearchRowIdentity
    document: SearchBackfillDocument
    status: SearchQueueItemStatus
    attempts: int
    lease_owner: str | None
    lease_expires_at: str | None
    available_at: str | None
    last_error: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class TranscriptWatermark:
    """Last safely queued transcript coordinate for one transcript source."""

    runtime: str
    session_id: str | None
    transcript_source: str
    transcript_offset: int | None
    transcript_index: int | None
    updated_at: str


def _now_iso(now: datetime | None = None) -> str:
    value = now or datetime.now(UTC)
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _identity_json(identity: SearchRowIdentity) -> str:
    return json.dumps(
        identity.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def queue_id_for_identity(identity: SearchRowIdentity) -> str:
    """Return the stable lifecycle queue id for a transcript-derived row."""
    digest = hashlib.sha256(_identity_json(identity).encode("utf-8")).hexdigest()
    return f"q_{digest}"


def queue_id_for_document(document: SearchBackfillDocument) -> str:
    """Return the stable lifecycle queue id for a document payload."""
    return queue_id_for_identity(document.identity)


def sanitize_error(error: BaseException | str) -> str:
    """Return a bounded status-safe error summary."""
    if isinstance(error, BaseException):
        text = f"{type(error).__name__}: {str(error).splitlines()[0] if str(error) else 'search queue error'}"
    else:
        lines = [line.strip() for line in str(error).splitlines() if line.strip()]
        if lines and lines[0].startswith("Traceback"):
            text = "search error"
        else:
            text = lines[0] if lines else "search queue error"
    text = re.sub(
        r"(\b[A-Z0-9_]*(?:TOKEN|SECRET|PASSWORD|KEY)[A-Z0-9_]*\b)\s*=\s*\S+",
        r"\1=[secret]",
        text,
    )
    text = re.sub(
        r"\b[A-Z0-9_]*(TOKEN|SECRET|PASSWORD|KEY)[A-Z0-9_]*\b", "[secret]", text
    )
    text = text.replace("secret", "[redacted]")
    text = re.sub(r"(?<!\w)/(?:[^\s:]+/?)+", "[path]", text)
    return text[:MAX_ERROR_LENGTH]


def _connect(path: Path | None = None) -> sqlite3.Connection:
    db_path = path or queue_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA journal_mode = WAL")
    _init_schema(conn)
    return conn


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS queue_items (
            queue_id TEXT PRIMARY KEY,
            identity_json TEXT NOT NULL,
            document_json TEXT NOT NULL,
            status TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            lease_owner TEXT,
            lease_expires_at TEXT,
            available_at TEXT,
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_queue_ready
            ON queue_items(status, available_at, lease_expires_at, created_at);

        CREATE TABLE IF NOT EXISTS transcript_watermarks (
            runtime TEXT NOT NULL,
            transcript_source TEXT NOT NULL,
            session_id TEXT,
            transcript_offset INTEGER,
            transcript_index INTEGER,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (runtime, transcript_source)
        );

        CREATE TABLE IF NOT EXISTS queue_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            error TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS stale_sources (
            transcript_source TEXT PRIMARY KEY,
            runtime TEXT NOT NULL,
            session_id TEXT,
            stale_at TEXT NOT NULL
        );
        """
    )
    conn.execute(
        "INSERT OR REPLACE INTO metadata(key, value) VALUES('schema_version', ?)",
        (str(QUEUE_SCHEMA_VERSION),),
    )
    conn.commit()


def _row_to_item(row: sqlite3.Row) -> SearchQueueItem:
    identity_raw = json.loads(row["identity_json"])
    document_raw = json.loads(row["document_json"])
    return SearchQueueItem(
        queue_id=row["queue_id"],
        identity=SearchRowIdentity(**identity_raw),
        document=SearchBackfillDocument(**document_raw),
        status=row["status"],
        attempts=row["attempts"],
        lease_owner=row["lease_owner"],
        lease_expires_at=row["lease_expires_at"],
        available_at=row["available_at"],
        last_error=row["last_error"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def enqueue_document(document: SearchBackfillDocument) -> str:
    """Persist one live document idempotently and return its queue id."""
    [queue_id] = enqueue_documents([document])
    return queue_id


def enqueue_documents(documents: list[SearchBackfillDocument]) -> list[str]:
    """Persist live documents idempotently without requeueing failed/done rows."""
    if not documents:
        return []
    now = _now_iso()
    queue_ids: list[str] = []
    with _connect() as conn:
        for document in documents:
            queue_id = queue_id_for_document(document)
            queue_ids.append(queue_id)
            identity_json = _identity_json(document.identity)
            document_json = json.dumps(
                document.model_dump(mode="json"),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            conn.execute(
                """
                INSERT INTO queue_items (
                    queue_id, identity_json, document_json, status, attempts,
                    lease_owner, lease_expires_at, available_at, last_error,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, 'queued', 0, NULL, NULL, NULL, NULL, ?, ?)
                ON CONFLICT(queue_id) DO UPDATE SET
                    identity_json = excluded.identity_json,
                    document_json = excluded.document_json,
                    updated_at = excluded.updated_at
                """,
                (queue_id, identity_json, document_json, now, now),
            )
    return queue_ids


def ready_item_count(*, now: datetime | None = None) -> int:
    """Return the number of queue rows currently claimable by a worker."""
    now_iso = _now_iso(now)
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM queue_items
            WHERE
                (status = 'queued' AND (available_at IS NULL OR available_at <= ?))
                OR (status = 'leased' AND lease_expires_at IS NOT NULL AND lease_expires_at <= ?)
            """,
            (now_iso, now_iso),
        ).fetchone()
    return int(row["count"] if row is not None else 0)


def lease_ready_items(
    *,
    limit: int,
    lease_owner: str | None = None,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: datetime | None = None,
) -> list[SearchQueueItem]:
    """Claim ready rows, including expired leases, for bounded worker processing."""
    if limit <= 0:
        return []
    now_dt = now or datetime.now(UTC)
    now_iso = _now_iso(now_dt)
    lease_expires_at = _now_iso(now_dt + timedelta(seconds=lease_seconds))
    owner = lease_owner or f"worker-{uuid.uuid4().hex}"
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT queue_id
            FROM queue_items
            WHERE
                (status = 'queued' AND (available_at IS NULL OR available_at <= ?))
                OR (status = 'leased' AND lease_expires_at IS NOT NULL AND lease_expires_at <= ?)
            ORDER BY created_at ASC, queue_id ASC
            LIMIT ?
            """,
            (now_iso, now_iso, limit),
        ).fetchall()
        queue_ids = [row["queue_id"] for row in rows]
        if not queue_ids:
            return []
        placeholders = ",".join("?" for _ in queue_ids)
        conn.execute(
            f"""
            UPDATE queue_items
            SET status = 'leased',
                lease_owner = ?,
                lease_expires_at = ?,
                attempts = attempts + 1,
                updated_at = ?
            WHERE queue_id IN ({placeholders})
            """,
            (owner, lease_expires_at, now_iso, *queue_ids),
        )
        leased_rows = conn.execute(
            f"""
            SELECT *
            FROM queue_items
            WHERE queue_id IN ({placeholders})
            ORDER BY created_at ASC, queue_id ASC
            """,
            (*queue_ids,),
        ).fetchall()
    return [_row_to_item(row) for row in leased_rows]


def complete_items(queue_ids: list[str]) -> int:
    """Mark queue rows as done after their documents were upserted."""
    if not queue_ids:
        return 0
    now = _now_iso()
    placeholders = ",".join("?" for _ in queue_ids)
    with _connect() as conn:
        cursor = conn.execute(
            f"""
            UPDATE queue_items
            SET status = 'done',
                lease_owner = NULL,
                lease_expires_at = NULL,
                last_error = NULL,
                updated_at = ?
            WHERE queue_id IN ({placeholders})
            """,
            (now, *queue_ids),
        )
    return int(cursor.rowcount)


def fail_item(
    queue_id: str,
    error: BaseException | str,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> Literal["queued", "failed", "missing"]:
    """Release a row for retry or move it to failed/dead-letter state."""
    now = _now_iso()
    safe_error = sanitize_error(error)
    with _connect() as conn:
        row = conn.execute(
            "SELECT attempts FROM queue_items WHERE queue_id = ?",
            (queue_id,),
        ).fetchone()
        if row is None:
            return "missing"
        attempts = int(row["attempts"])
        status = "failed" if attempts >= max_attempts else "queued"
        conn.execute(
            """
            UPDATE queue_items
            SET status = ?,
                lease_owner = NULL,
                lease_expires_at = NULL,
                available_at = NULL,
                last_error = ?,
                updated_at = ?
            WHERE queue_id = ?
            """,
            (status, safe_error, now, queue_id),
        )
        conn.execute(
            "INSERT INTO queue_errors(error, created_at) VALUES(?, ?)",
            (safe_error, now),
        )
    return status


def fail_items(
    queue_ids: list[str],
    error: BaseException | str,
    *,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> None:
    """Apply the same failure to a batch of leased rows."""
    for queue_id in queue_ids:
        fail_item(queue_id, error, max_attempts=max_attempts)


def requeue_failed_items(*, limit: int | None = None) -> int:
    """Explicitly requeue failed rows for manual retry/rebuild controls."""
    now = _now_iso()
    with _connect() as conn:
        if limit is None:
            cursor = conn.execute(
                """
                UPDATE queue_items
                SET status = 'queued',
                    attempts = 0,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    available_at = ?,
                    last_error = NULL,
                    updated_at = ?
                WHERE status = 'failed'
                """,
                (now, now),
            )
            return int(cursor.rowcount)

        rows = conn.execute(
            """
            SELECT queue_id
            FROM queue_items
            WHERE status = 'failed'
            ORDER BY updated_at ASC, queue_id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        queue_ids = [row["queue_id"] for row in rows]
        if not queue_ids:
            return 0
        placeholders = ",".join("?" for _ in queue_ids)
        cursor = conn.execute(
            f"""
            UPDATE queue_items
            SET status = 'queued',
                attempts = 0,
                lease_owner = NULL,
                lease_expires_at = NULL,
                available_at = ?,
                last_error = NULL,
                updated_at = ?
            WHERE queue_id IN ({placeholders})
            """,
            (now, now, *queue_ids),
        )
    return int(cursor.rowcount)


def read_queue_item(queue_id: str) -> SearchQueueItem | None:
    """Read one queue row for tests, diagnostics, or retry tooling."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM queue_items WHERE queue_id = ?",
            (queue_id,),
        ).fetchone()
    if row is None:
        return None
    return _row_to_item(row)


def get_queue_snapshot(*, now: datetime | None = None) -> SearchQueueSnapshot:
    """Return a safe queue status summary without transcript payloads."""
    now_dt = now or datetime.now(UTC)
    with _connect() as conn:
        counts = {
            row["status"]: int(row["count"])
            for row in conn.execute(
                "SELECT status, COUNT(*) AS count FROM queue_items GROUP BY status"
            ).fetchall()
        }
        oldest_row = conn.execute(
            """
            SELECT created_at
            FROM queue_items
            WHERE status = 'queued'
            ORDER BY created_at ASC
            LIMIT 1
            """
        ).fetchone()
        error_row = conn.execute(
            """
            SELECT error
            FROM queue_errors
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        failed_row = conn.execute(
            """
            SELECT last_error
            FROM queue_items
            WHERE status = 'failed' AND last_error IS NOT NULL
            ORDER BY updated_at DESC
            LIMIT 1
            """
        ).fetchone()
        stale_row = conn.execute(
            "SELECT COUNT(*) AS count FROM stale_sources"
        ).fetchone()

    oldest_queued_at = oldest_row["created_at"] if oldest_row is not None else None
    oldest_dt = _parse_iso(oldest_queued_at)
    oldest_age = (
        max(0.0, (now_dt.astimezone(UTC) - oldest_dt).total_seconds())
        if oldest_dt is not None
        else None
    )
    recent_error = None
    if error_row is not None:
        recent_error = error_row["error"]
    elif failed_row is not None:
        recent_error = failed_row["last_error"]

    return SearchQueueSnapshot(
        queued_items=counts.get("queued", 0),
        leased_items=counts.get("leased", 0),
        failed_items=counts.get("failed", 0),
        oldest_queued_at=oldest_queued_at,
        oldest_queued_age_seconds=oldest_age,
        recent_error=recent_error,
        stale_sources=int(stale_row["count"] if stale_row is not None else 0),
    )


def record_queue_error(error: BaseException | str) -> str:
    """Persist a sanitized producer/worker error for status reporting."""
    safe_error = sanitize_error(error)
    now = _now_iso()
    with _connect() as conn:
        conn.execute(
            "INSERT INTO queue_errors(error, created_at) VALUES(?, ?)",
            (safe_error, now),
        )
    return safe_error


def clear_queue_errors() -> None:
    """Drop the recent-error log. Called after a successful drain so the
    status footer stops surfacing yesterday's transient failure."""
    with _connect() as conn:
        conn.execute("DELETE FROM queue_errors")


def read_watermark(runtime: str, transcript_source: str) -> TranscriptWatermark | None:
    """Read the last safe queue coordinate for a transcript source."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM transcript_watermarks
            WHERE runtime = ? AND transcript_source = ?
            """,
            (runtime, transcript_source),
        ).fetchone()
    if row is None:
        return None
    return TranscriptWatermark(
        runtime=row["runtime"],
        session_id=row["session_id"],
        transcript_source=row["transcript_source"],
        transcript_offset=row["transcript_offset"],
        transcript_index=row["transcript_index"],
        updated_at=row["updated_at"],
    )


def upsert_watermark(
    *,
    runtime: str,
    session_id: str | None,
    transcript_source: str,
    transcript_offset: int | None,
    transcript_index: int | None,
) -> None:
    """Persist the last transcript coordinate after queue enqueue succeeds."""
    now = _now_iso()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO transcript_watermarks (
                runtime, transcript_source, session_id, transcript_offset,
                transcript_index, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(runtime, transcript_source) DO UPDATE SET
                session_id = excluded.session_id,
                transcript_offset = excluded.transcript_offset,
                transcript_index = excluded.transcript_index,
                updated_at = excluded.updated_at
            """,
            (
                runtime,
                transcript_source,
                session_id,
                transcript_offset,
                transcript_index,
                now,
            ),
        )


def replace_stale_sources(
    sources: list[tuple[str, str, str | None]],
) -> None:
    """Replace stale-source markers with `(transcript_source, runtime, session_id)`."""
    now = _now_iso()
    with _connect() as conn:
        conn.execute("DELETE FROM stale_sources")
        conn.executemany(
            """
            INSERT INTO stale_sources(transcript_source, runtime, session_id, stale_at)
            VALUES (?, ?, ?, ?)
            """,
            [
                (source, runtime, session_id, now)
                for source, runtime, session_id in sources
            ],
        )


def list_stale_sources() -> set[str]:
    """Return transcript sources currently marked stale."""
    with _connect() as conn:
        rows = conn.execute("SELECT transcript_source FROM stale_sources").fetchall()
    return {row["transcript_source"] for row in rows}


def is_source_stale(transcript_source: str) -> bool:
    """Return whether a transcript source is marked stale."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT 1 FROM stale_sources WHERE transcript_source = ?",
            (transcript_source,),
        ).fetchone()
    return row is not None


def parse_document(raw: str) -> SearchBackfillDocument | None:
    """Parse one persisted document row, ignoring invalid historical lines."""
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return None
        return SearchBackfillDocument(**payload)
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
        return None


def delete_queue_items_by_window(window_id: str) -> int:
    """Remove queue items whose document was enqueued for a tmux window
    that has since been killed. Scans every queued row's JSON because
    window_id is buried inside `document_json`; acceptable since session
    deletion is rare. Returns the number of rows removed."""
    if not window_id:
        return 0
    target_ids: list[str] = []
    with _connect() as conn:
        cur = conn.execute("SELECT queue_id, document_json FROM queue_items")
        for queue_id, document_json in cur:
            try:
                doc = json.loads(document_json)
            except (TypeError, ValueError):
                continue
            routing = doc.get("routing") if isinstance(doc, dict) else None
            if isinstance(routing, dict) and routing.get("window_id") == window_id:
                target_ids.append(queue_id)
        if target_ids:
            conn.executemany(
                "DELETE FROM queue_items WHERE queue_id = ?",
                [(qid,) for qid in target_ids],
            )
            conn.commit()
    return len(target_ids)


__all__ = [
    "DEFAULT_LEASE_SECONDS",
    "DEFAULT_MAX_ATTEMPTS",
    "QUEUE_SCHEMA_VERSION",
    "SearchQueueItem",
    "TranscriptWatermark",
    "complete_items",
    "delete_queue_items_by_window",
    "enqueue_document",
    "enqueue_documents",
    "fail_item",
    "fail_items",
    "get_queue_snapshot",
    "is_source_stale",
    "lease_ready_items",
    "list_stale_sources",
    "parse_document",
    "queue_id_for_document",
    "queue_id_for_identity",
    "read_queue_item",
    "read_watermark",
    "ready_item_count",
    "record_queue_error",
    "replace_stale_sources",
    "requeue_failed_items",
    "sanitize_error",
    "upsert_watermark",
]
