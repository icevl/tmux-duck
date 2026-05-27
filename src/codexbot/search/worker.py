"""Local search worker CLI skeleton.

Phase 2 establishes the process boundary and status state. Real transcript
backfill, generation activation, and retrieval are added by later plans.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Sequence

from .backfill import materialize_initial_backfill, new_generation_id
from .contracts import (
    SearchBackfillDocument,
    SearchBackfillManifest,
    SearchCounters,
    SearchRoutingMetadata,
    SearchRowIdentity,
    SearchWorkerStatus,
    TranscriptProvenance,
)
from .index import (
    existing_row_ids,
    materialize_generation_index,
    row_id_for_identity,
    upsert_index_documents,
)
from .live import read_generation_documents, upsert_generation_documents
from .queue import (
    clear_queue_errors,
    complete_items,
    fail_items,
    lease_ready_items,
    ready_item_count,
    record_queue_error,
    sanitize_error,
)
from .state import (
    activate_generation,
    generations_dir,
    read_generation_manifest,
    read_generation_metadata,
    search_dir,
    write_worker_status,
)

PAUSE_POLL_SLEEP_SECONDS = 1.0
PAUSE_FLAG_FILENAME = "pause"


def _pause_flag_path() -> Path:
    return search_dir() / PAUSE_FLAG_FILENAME


def _find_resumable_generation() -> SearchBackfillManifest | None:
    """Pick the freshest generation that finished its discover step but
    didn't get a state.json marker. If a previous run was killed during
    embedding its manifest + documents.jsonl + partial LanceDB sit on
    disk untouched, and we can pick up where it left off."""
    root = generations_dir()
    if not root.exists():
        return None
    candidates: list[tuple[str, SearchBackfillManifest]] = []
    for entry in sorted(root.iterdir(), reverse=True):
        if not entry.is_dir():
            continue
        manifest = read_generation_manifest(entry.name)
        if manifest is None or not manifest.completed:
            continue
        candidates.append((entry.name, manifest))
    if not candidates:
        return None
    return candidates[0][1]


def _purge_other_generations(keep_generation_id: str) -> None:
    """After a successful activate_generation, delete every generation
    directory except the one we just activated. Previous runs accumulated
    one dir per kill; this keeps the search/ tree clean."""
    root = generations_dir()
    if not root.exists():
        return
    for entry in root.iterdir():
        if entry.name == keep_generation_id or not entry.is_dir():
            continue
        try:
            shutil.rmtree(entry)
            logger.info("purged orphan search generation %s", entry.name)
        except OSError as exc:
            logger.warning("could not purge %s: %s", entry, exc)


logger = logging.getLogger(__name__)
LIVE_BATCH_SIZE = 32
LIVE_FLUSH_INTERVAL_SECONDS = 60.0
_last_live_flush_at: datetime | None = None


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _failed_error_summary(exc: BaseException) -> str:
    return sanitize_error(exc)


def _running_status(
    current_task: str,
    *,
    counters: SearchCounters | None = None,
) -> SearchWorkerStatus:
    return SearchWorkerStatus(
        status="running",
        current_task=current_task,
        heartbeat_at=_now_iso(),
        counters=counters,
    )


def _run_generation_task(current_task: str) -> None:
    """Materialize and activate a fresh generation for a local worker task."""
    write_worker_status(_running_status(current_task))
    try:
        # Resume the previous run if we find a manifest-but-no-state.json
        # generation on disk. That happens whenever the worker was killed
        # mid-embedding; without resume every restart re-embeds from
        # zero into a brand-new generation_id.
        resumable = _find_resumable_generation()
        if resumable is not None:
            manifest = resumable
            documents = read_generation_documents(manifest.generation.generation_id)
            already_indexed = existing_row_ids(manifest.generation.generation_id)
            pending = [
                doc
                for doc in documents
                if row_id_for_identity(doc.identity) not in already_indexed
            ]
            existing_count = len(documents) - len(pending)
            logger.info(
                "search_worker_resuming generation=%s already=%d remaining=%d",
                manifest.generation.generation_id,
                existing_count,
                len(pending),
            )
        else:
            manifest = asyncio.run(materialize_initial_backfill())
            pending = None
            existing_count = 0

        # Snapshot counters so the UI sees discovered totals before embedding
        # starts, then tick indexed_chunks as each embedding batch lands.
        # The fresh heartbeat on every callback also keeps the bot-side
        # status publisher from flipping the footer to "stale" while a
        # multi-minute embedding pass is in flight.
        base = manifest.counters
        total_chunks = manifest.document_count

        def _write_progress(processed: int, total: int, *, paused: bool) -> None:
            counters = SearchCounters(
                open_sessions=base.open_sessions,
                indexed_sessions=base.indexed_sessions if processed >= total > 0 else 0,
                indexed_chunks=processed,
                total_chunks=total or total_chunks,
                queued_items=base.queued_items,
                failed_items=base.failed_items,
            )
            write_worker_status(
                SearchWorkerStatus(
                    status="running",
                    current_task=current_task,
                    heartbeat_at=_now_iso(),
                    counters=counters,
                    paused=paused,
                )
            )

        def progress(processed_local: int, _total_local: int) -> None:
            # Park here while the supervisor's pause flag is up so the
            # embedding doesn't compete with the user's active tmux work.
            # We refresh the heartbeat each loop so request-path code
            # doesn't decide we've died.
            #
            # `processed_local` is the count for the current pending list;
            # add `existing_count` so the UI shows the absolute progress
            # across the full generation (resume-friendly).
            absolute_processed = existing_count + processed_local
            flag = _pause_flag_path()
            paused_already_logged = False
            while flag.exists():
                if not paused_already_logged:
                    logger.info(
                        "search_worker_paused processed=%d total=%d",
                        absolute_processed,
                        total_chunks,
                    )
                    paused_already_logged = True
                _write_progress(absolute_processed, total_chunks, paused=True)
                time.sleep(PAUSE_POLL_SLEEP_SECONDS)
            _write_progress(absolute_processed, total_chunks, paused=False)

        progress(0, len(pending) if pending is not None else total_chunks)
        if pending is not None and not pending:
            # Resume found a fully-embedded generation; just activate.
            pass
        else:
            materialize_generation_index(
                manifest.generation.generation_id,
                documents=pending,  # None = read from jsonl (cold start)
                progress_cb=progress,
            )
        activate_generation(manifest)
        _purge_other_generations(manifest.generation.generation_id)
        try:
            clear_queue_errors()
        except Exception:  # noqa: BLE001
            logger.exception("search_clear_queue_errors_failed")
    except Exception as exc:
        logger.exception("search_generation_task_failed task=%s", current_task)
        write_worker_status(
            SearchWorkerStatus(
                status="failed",
                current_task=current_task,
                heartbeat_at=_now_iso(),
                recent_error=_failed_error_summary(exc),
            )
        )
        raise

    write_worker_status(
        SearchWorkerStatus(
            status="completed",
            current_task=current_task,
            heartbeat_at=_now_iso(),
            counters=manifest.counters,
        )
    )


def run_initial_backfill() -> None:
    """Materialize and activate an initial backfill generation."""
    _run_generation_task("initial_backfill")


def run_rebuild() -> None:
    """Materialize and activate a fresh explicit rebuild generation."""
    _run_generation_task("rebuild")


def _smoke_document() -> SearchBackfillDocument:
    provenance = TranscriptProvenance(
        runtime="codex",
        session_id="smoke-session",
        transcript_source="smoke-transcript",
        transcript_offset=0,
        transcript_index=0,
        role="assistant",
        content_type="text",
        source_event_kind="smoke",
        timestamp=_now_iso(),
    )
    return SearchBackfillDocument(
        identity=SearchRowIdentity.from_provenance(provenance, chunk_index=0),
        provenance=provenance,
        routing=SearchRoutingMetadata(
            window_id="@smoke",
            name="smoke",
            cwd="/",
            runtime="codex",
            session_id="smoke-session",
            status="active",
        ),
        text="Codi local search smoke test for Qwen embedding and LanceDB index.",
        timestamp=provenance.timestamp,
        source_order=0,
        chunk_index=0,
        chunk_count=1,
    )


def run_smoke_search_index() -> int:
    """Embed a tiny local batch and materialize a one-row local index."""
    generation_id = f"smoke-{new_generation_id()}"
    started = time.monotonic()
    try:
        metadata = materialize_generation_index(
            generation_id,
            documents=[_smoke_document()],
        )
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "generation_id": generation_id,
                    "error": sanitize_error(exc),
                },
                ensure_ascii=False,
            )
        )
        return 1

    elapsed_ms = int((time.monotonic() - started) * 1000)
    from .state import generation_lancedb_dir

    print(
        json.dumps(
            {
                "ok": True,
                "generation_id": generation_id,
                "model_id": metadata.model_id,
                "vector_dimension": metadata.vector_dimension,
                "table_name": metadata.table_name,
                "index_path": str(generation_lancedb_dir(generation_id)),
                "elapsed_ms": elapsed_ms,
            },
            ensure_ascii=False,
        )
    )
    return 0


def _seconds_since_flush(now: datetime) -> float:
    if _last_live_flush_at is None:
        return 0.0
    return max(0.0, (now - _last_live_flush_at).total_seconds())


_live_drain_count: int = 0
# Compact the active LanceDB table every N successful drains. Each
# merge_insert creates a new version; without periodic compaction the
# version count grows linearly and merge eventually fails with a
# DataFusion "Spill has sent an error" because the join across hundreds
# of fragments can't spill to disk fast enough. 30 keeps total versions
# well under 100 between sweeps and stays cheap.
LIVE_COMPACT_EVERY = 30


def _compact_active_generation(generation_id: str) -> None:
    """Vacuum the active LanceDB table — compact fragments, prune old
    versions. Best-effort: errors are logged and swallowed because a failed
    compaction shouldn't block the live drain loop."""
    from datetime import timedelta

    from .index import connect_lancedb

    try:
        table = connect_lancedb(generation_id).open_table("chunks")
        table.optimize(cleanup_older_than=timedelta(seconds=0))
    except Exception:  # noqa: BLE001
        logger.exception("search_live_compact_failed gen=%s", generation_id)


def drain_live_queue_once(
    *,
    batch_size: int = LIVE_BATCH_SIZE,
    flush_interval_seconds: float = LIVE_FLUSH_INTERVAL_SECONDS,
    force: bool = False,
    max_attempts: int = 3,
    now: datetime | None = None,
) -> int:
    """Drain one live queue batch into the active generation when flushable."""
    global _last_live_flush_at
    current_time = now or datetime.now(UTC)
    generation = read_generation_metadata()
    if generation is None:
        return 0

    ready = ready_item_count(now=current_time)
    if ready <= 0:
        return 0

    flush_due = _seconds_since_flush(current_time) >= flush_interval_seconds
    if _last_live_flush_at is None and not force and ready < batch_size:
        _last_live_flush_at = current_time
        return 0
    if not force and ready < batch_size and not flush_due:
        return 0

    items = lease_ready_items(
        limit=batch_size,
        lease_owner="search-live-worker",
        now=current_time,
    )
    if not items:
        return 0

    queue_ids = [item.queue_id for item in items]
    try:
        upsert_generation_documents(
            generation.generation_id,
            [item.document for item in items],
        )
        upsert_index_documents(
            generation.generation_id,
            [item.document for item in items],
        )
    except Exception as exc:
        logger.exception("search_live_drain_failed")
        record_queue_error(exc)
        fail_items(queue_ids, exc, max_attempts=max_attempts)
        return 0

    complete_items(queue_ids)
    # A successful drain means whatever was sitting in queue_errors is
    # stale; clearing it stops the footer from surfacing yesterday's
    # transient Spill error after we've actually recovered.
    try:
        clear_queue_errors()
    except Exception:  # noqa: BLE001
        logger.exception("search_clear_queue_errors_failed")
    _last_live_flush_at = current_time
    global _live_drain_count
    _live_drain_count += 1
    if _live_drain_count % LIVE_COMPACT_EVERY == 0:
        _compact_active_generation(generation.generation_id)
    return len(items)


async def run_live_loop(*, poll_interval_seconds: float = 1.0) -> None:
    """Continuously drain live queue work until cancelled."""
    while True:
        try:
            drain_live_queue_once()
        except Exception as exc:
            logger.exception("search_live_loop_iteration_failed")
            record_queue_error(exc)
        await asyncio.sleep(poll_interval_seconds)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="codexbot-search-worker")
    parser.add_argument(
        "command",
        nargs="?",
        default="initial-backfill",
        choices=(
            "initial-backfill",
            "rebuild",
            "live-loop",
            "live-drain-once",
            "smoke-search-index",
            "benchmark",
        ),
    )
    args, remaining = parser.parse_known_args(argv)

    if args.command == "initial-backfill":
        try:
            run_initial_backfill()
        except Exception:
            return 1
        return 0
    if args.command == "rebuild":
        try:
            run_rebuild()
        except Exception:
            return 1
        return 0
    if args.command == "live-drain-once":
        try:
            drain_live_queue_once(force=True)
        except Exception:
            return 1
        return 0
    if args.command == "live-loop":
        try:
            asyncio.run(run_live_loop())
        except KeyboardInterrupt:
            return 0
        except Exception:
            return 1
        return 0
    if args.command == "smoke-search-index":
        return run_smoke_search_index()
    if args.command == "benchmark":
        from .benchmark import main as benchmark_main

        return benchmark_main(remaining)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())


__all__ = [
    "LIVE_BATCH_SIZE",
    "LIVE_FLUSH_INTERVAL_SECONDS",
    "drain_live_queue_once",
    "main",
    "run_initial_backfill",
    "run_live_loop",
    "run_rebuild",
    "run_smoke_search_index",
]
