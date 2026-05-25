---
phase: 02-worker-skeleton-backfill-and-rebuild-path
status: passed
verified_at: 2026-05-21T22:17:00Z
score: 18/18
human_verification: []
---

# Phase 02 Verification

## Goal

Verify that Phase 02 provides a safe asynchronous worker skeleton, parser-backed open-session backfill, explicit rebuild, atomic generation activation, recovery for incomplete generations, and truthful built-but-unqueryable search status.

## Must-Haves Verified

- PASS: Startup schedules initial backfill when no active search generation exists and skips when one exists.
- PASS: Worker status is written under `CODEXBOT_DIR/search` and reports `building` while running.
- PASS: Backfill enumerates current tmux windows and resolves Codex/Claude transcripts through session helpers.
- PASS: Backfill uses parser-level `ParsedEntry` values, not Web UI history DTOs.
- PASS: Text-bearing parser entries produce chunk documents with transcript provenance and stable `chunk_index`.
- PASS: Inactive generation documents and manifests are written under `CODEXBOT_DIR/search/generations`.
- PASS: Explicit local `rebuild` creates and activates a fresh generation.
- PASS: Activation is success-only and atomic: incomplete manifests cannot become active.
- PASS: Incomplete/interrupted generation directories are ignored and rerunnable.
- PASS: Completed Phase 2 status includes active generation metadata and manifest counters.
- PASS: Completed Phase 2 search remains `available=false` and returns typed `not_ready` until retrieval exists.
- PASS: Worker failures degrade search status only and do not mutate authoritative session or monitor state.

## Requirements

- PASS: `INDX-01` search-owned storage and metadata live under `CODEXBOT_DIR/search`.
- PASS: `INDX-02` worker startup is asynchronous and nonblocking.
- PASS: `CORP-01` backfill reads normalized Codex and Claude transcript records through existing runtime transcript parsers rather than Web UI history DTOs or terminal scrollback.
- PASS: `CORP-02` user, assistant, and useful tool/output text-bearing parser entries are converted into indexable chunk documents.
- PASS: `INDX-03` open-session backfill is parser-backed for current Codex and Claude sessions.
- PASS: `INDX-08` rebuild/recovery semantics are local, rerunnable, and activation-safe.

## Automated Validation

- PASS: `uv run ruff check src/ tests/`
- PASS: `uv run ruff format --check src/ tests/`
- PASS: `uv run pyright src/codexbot/`
- PASS: `uv run pytest -q` — 523 passed, 2 warnings

## Notes

The documented `/tmp/codexbot-venv/bin/pytest` binary is absent on this host, so the equivalent working repo test lane `uv run pytest -q` was used for the full suite.
