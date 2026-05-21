# Phase 1: Search Contract and Status Surface - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution
> agents. Decisions are captured in CONTEXT.md - this log preserves the
> alternatives considered.

**Date:** 2026-05-21
**Phase:** 1-Search Contract and Status Surface
**Areas discussed:** Search Item Identity, Status/API Shape, Derived-State Boundary

---

## Search Item Identity

| Decision | Options Presented | Selected |
|----------|-------------------|----------|
| Primary indexed unit | Message chunk rows; Whole messages; Whole turns | Message chunk rows |
| Transcript position fields | Offset + index; Index only; Timestamp based | Offset + index |
| tmux window data in DTOs | Mutable route metadata; Part of identity; Response only | Mutable route metadata |
| Indexed content taxonomy | Role + content type; Role only; Runtime-specific types | Role + content type |

**User's choice:** Recommended options for all four identity questions.
**Notes:** The contract should support precise chunks while preserving
message-level transcript provenance and keeping current `window_id` as mutable
routing metadata.

---

## Status/API Shape

| Decision | Options Presented | Selected |
|----------|-------------------|----------|
| API surface | Status + search stub; Status only; Full search DTOs only | Status + search stub |
| Status vocabulary | Full lifecycle enum; Simple ready flag; Worker-specific states | Full lifecycle enum |
| Missing/unavailable HTTP behavior | 200 status typed state; 503 for search; 404 until built | 200 status typed state |
| Model/index import boundary | Hard boundary; Soft convention; No constraint | Hard boundary |

**User's choice:** Recommended options for all four Status/API questions.
**Notes:** Phase 1 should allow the Web UI to call status/search safely before
worker/retrieval phases exist, without importing heavy model/index libraries in
FastAPI handlers.

---

## Derived-State Boundary

| Decision | Options Presented | Selected |
|----------|-------------------|----------|
| Search-owned state location | CODEXBOT_DIR/search; Alongside monitor_state; Repo-local .planning | CODEXBOT_DIR/search |
| Relationship to `monitor_state.json` | No writes ever; Reuse offsets; Mirror state | No writes ever |
| Rebuild generation metadata | Schema + generation; Schema only; No metadata yet | Schema + generation |
| Open-session filtering | At query/status time; Only at ingest time; Only in frontend | At query/status time |

**User's choice:** Recommended options for all four derived-state questions.
**Notes:** Search state must remain derived and rebuildable. Existing monitor
state remains authoritative for delivery offsets and must not be mutated by
search indexing.

## the agent's Discretion

None.

## Deferred Ideas

None.
