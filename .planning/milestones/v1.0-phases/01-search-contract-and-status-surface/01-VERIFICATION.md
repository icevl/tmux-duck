---
phase: 01-search-contract-and-status-surface
verified: 2026-05-21T14:14:06Z
status: passed
score: 30/30 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 0/1
  gaps_closed:
    - "MVP-mode Phase 1 goal is a valid User Story in ROADMAP.md"
  gaps_remaining: []
  regressions: []
---

# Phase 1: Search Contract and Status Surface Verification Report

**Phase Goal:** As a Codi Web UI user, I want to call search-facing backend surfaces with stable provenance and honest readiness semantics, so that later indexing can become searchable without misleading or blocking existing open-session workflows.
**Verified:** 2026-05-21T14:14:06Z
**Status:** passed
**Re-verification:** Yes - after roadmap goal fix commit `d4d70fc`

## User Flow Coverage

User story: "As a Codi Web UI user, I want to call search-facing backend surfaces with stable provenance and honest readiness semantics, so that later indexing can become searchable without misleading or blocking existing open-session workflows."

| Step | Expected | Evidence | Status |
|---|---|---|---|
| Authenticate | Existing Web UI auth protects the new search surfaces. | `src/codexbot/web/api.py:574-583` uses `Depends(require_auth)` for both search routes; `tests/codexbot/test_web_api.py:107-114` proves unauthenticated calls receive 401. | VERIFIED |
| Call status | Authenticated Web UI callers can request search status and receive an honest typed readiness response. | `src/codexbot/web/api.py:574-579` calls the lightweight provider; `tests/codexbot/test_web_api.py:117-150` verifies 200, `state == "missing"`, `available is False`, `scope == "open_sessions"`, and current open-session counters. | VERIFIED |
| Submit search request | Authenticated callers can submit bounded search requests without implying real retrieval exists yet. | `src/codexbot/web/api.py:581-588` accepts `SearchRequest` and delegates to `search_client.search`; `tests/codexbot/test_web_api.py:153-189` verifies typed 200 `not_ready`, empty results, and echoed limits. | VERIFIED |
| Reject invalid request | Oversized or out-of-range request values are rejected before retrieval work exists. | `src/codexbot/search/contracts.py:140-150` sets query and result bounds; `tests/codexbot/test_web_api.py:192-206` verifies 422 for invalid bodies. | VERIFIED |
| Preserve future searchability | Provenance, identity, derived state, and import boundaries make later indexing searchable without misleading or blocking current open-session flows. | `src/codexbot/search/contracts.py:33-163`, `src/codexbot/search/state.py:19-49`, `src/codexbot/search/client.py:24-61`, and `tests/codexbot/test_search_contracts.py:57-272` verify stable contracts, derived-state boundaries, and no heavy request-path imports. | VERIFIED |

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | User can call authenticated search/status surfaces that return structured missing or unavailable responses without importing embedding models in FastAPI handlers. | VERIFIED | Routes exist at `src/codexbot/web/api.py:574-588`, require auth, return typed DTO dumps, and focused pytest verifies auth/status/search behavior. Heavy import grep found no request-path model/index imports. |
| 2 | Every planned indexed item has stable provenance for runtime, session ID when known, transcript source, transcript offset or index, role/content type, and optional tool identifier. | VERIFIED | `TranscriptProvenance` defines all required fields in `src/codexbot/search/contracts.py:33-47`; tests assert them at `tests/codexbot/test_search_contracts.py:57-74`. |
| 3 | Current tmux `window_id` is represented only as mutable routing metadata, while transcript provenance is the row identity for indexed content. | VERIFIED | `SearchRowIdentity` excludes `window_id`, cwd, name, status, pinned, and sort order at `src/codexbot/search/contracts.py:49-75`; `SearchRoutingMetadata` carries them at `src/codexbot/search/contracts.py:78-88`; tests assert separation at `tests/codexbot/test_search_contracts.py:76-110`. |
| 4 | Codi treats search state as a derived cache that can be rebuilt from transcript/session state and does not write search progress into `monitor_state.json`. | VERIFIED | `search_dir()` resolves to `codexbot_dir() / "search"` at `src/codexbot/search/state.py:19-26`; status/search only read generation metadata, and tests prove `monitor_state.json` remains byte-for-byte unchanged at `tests/codexbot/test_search_state.py:125-148`. |
| 5 | Search contract models preserve stable transcript provenance for every planned indexed chunk row. | VERIFIED | `TranscriptProvenance`, `SearchRowIdentity`, and `SearchHit` connect source message provenance to chunk identity in `contracts.py:33-75` and `contracts.py:121-128`. |
| 6 | Chunk row identity is derived from transcript provenance plus chunk index, not current tmux routing or display metadata. | VERIFIED | `SearchRowIdentity.from_provenance()` copies only provenance fields and `chunk_index` at `contracts.py:61-75`; tests vary routing metadata without changing identity at `test_search_contracts.py:76-110`. |
| 7 | Search request DTOs bound user query text and requested result counts before any retrieval work exists. | VERIFIED | `SearchRequest.query` is 1..500, `limit` is 1..50, and `hits_per_session` is 1..10 at `contracts.py:140-145`; unit and API tests cover invalid values. |
| 8 | D-01: The primary indexed unit is a chunk-level search row tied back to a stable transcript message. | VERIFIED | `SearchRowIdentity` includes transcript coordinates and `chunk_index`; `SearchHit` includes both `identity` and `provenance`; `test_row_identity_supports_multiple_chunks_for_one_transcript_message` verifies multiple chunks. |
| 9 | D-02: The contract includes transcript source offset/cursor and parser index/sequence where available. | VERIFIED | `transcript_source`, `transcript_offset`, and `transcript_index` are present in both provenance and row identity at `contracts.py:38-40` and `contracts.py:53-55`. |
| 10 | D-03: Current tmux window_id, window name, cwd, session status, and pinned/sort metadata are mutable routing/display metadata, not row identity. | VERIFIED | Routing-only fields are isolated in `SearchRoutingMetadata`; identity tests explicitly assert these fields are absent from `SearchRowIdentity.model_dump()`. |
| 11 | D-04: Indexed item taxonomy is runtime-neutral with runtime, role, content_type, optional tool_name, and source event kind. | VERIFIED | Runtime-neutral fields are defined on `TranscriptProvenance` at `contracts.py:36-46`; the test fixture uses these fields without Codex/Claude raw-record shapes. |
| 12 | D-06: Search lifecycle states are exactly missing, building, partial, ready, stale, degraded, and unavailable. | VERIFIED | `SEARCH_INDEX_STATES` and `SearchIndexState` define exactly the seven states at `contracts.py:10-28`; `test_lifecycle_vocabulary_matches_phase_contract` verifies exact equality. |
| 13 | D-08: Request-path code imports only lightweight search contracts/stubs and no model, embedding, worker, or index packages. | VERIFIED | `src/codexbot/web/api.py:61-62` imports only `search.client` and `SearchRequest`; AST import-boundary test at `test_search_contracts.py:254-272` passes. |
| 14 | D-11: Generation metadata includes schema_version, generation_id, created_at, and active/inactive state. | VERIFIED | `SearchGenerationMetadata` defines those four fields at `contracts.py:91-98`; state reader enforces current schema and active generation at `state.py:40-49`. |
| 15 | Search runtime state is reserved under `$CODEXBOT_DIR/search/` and does not mutate Codi authoritative session or monitor state. | VERIFIED | `state.py:19-26` uses `codexbot_dir() / "search"`; `client.py` performs no writes; monitor-state isolation test passes. |
| 16 | First-run missing-index status is represented as a typed normal response with no secrets, transcript content, or raw local transcript paths. | VERIFIED | `client.get_status()` returns `SearchStatusResponse(state="missing", available=False)` when no generation exists; `test_missing_index_status_serializes_as_safe_typed_json` checks no secret/path/transcript leakage. |
| 17 | The search provider can answer status/search calls without importing or executing worker, embedding, retrieval, or LanceDB code. | VERIFIED | `client.py:5-11` imports only contracts and state; grep for forbidden model/index imports under `src/codexbot/web/api.py` and `src/codexbot/search` returned no matches. |
| 18 | D-05: Search status and search stub surfaces return structured missing/unavailable or empty responses until worker and retrieval phases exist. | VERIFIED | Provider returns `missing` when no generation exists and `unavailable` when active metadata exists but no query backend exists; `search()` returns empty typed `not_ready` response. |
| 19 | D-07: First-run missing/not-ready search states are typed normal responses, not 404 or 503 transport failures. | VERIFIED | API tests verify authenticated `GET /api/search/status` and `POST /api/search` return 200 with typed missing/not-ready bodies. |
| 20 | D-09: Search-owned runtime state is reserved under `$CODEXBOT_DIR/search/`. | VERIFIED | `search_dir()` returns `codexbot_dir() / "search"` and tests verify both configured and default paths. |
| 21 | D-10: Search never writes to `monitor_state.json`; search watermarks, leases, retries, generation metadata, and progress live in search-owned state. | VERIFIED | Search package has no `monitor_state`, `MonitorState`, or `atomic_write_json` imports; test proves status/search do not create or mutate `monitor_state.json`. |
| 22 | D-11: Rebuildable index generations carry schema_version, generation_id, created_at, and an active/inactive marker. | VERIFIED | `SearchGenerationMetadata` and `read_generation_metadata()` satisfy this; tests reject invalid, inactive, and schema-mismatched metadata. |
| 23 | Authenticated Web UI callers can request search status and receive typed missing/not-ready semantics. | VERIFIED | `GET /api/search/status` is authenticated and returns typed missing state with counters in tests. |
| 24 | Authenticated Web UI callers can submit a bounded search request and receive a typed not-ready search response. | VERIFIED | `POST /api/search` is authenticated, validates `SearchRequest`, and returns typed `not_ready` response in tests. |
| 25 | Unauthenticated callers cannot discover search status or transcript/search metadata. | VERIFIED | `tests/codexbot/test_web_api.py:107-114` verifies 401 for unauthenticated status and search calls. |
| 26 | FastAPI request handlers import only lightweight search contracts/provider modules. | VERIFIED | `web/api.py:61-62` imports only lightweight search modules, and the static import-boundary test passes. |
| 27 | D-05: Phase 1 defines both authenticated search status and search stub surfaces. | VERIFIED | `GET /api/search/status` and `POST /api/search` are both present and protected by `Depends(require_auth)`. |
| 28 | D-07: Search routes return typed 200 responses for first-run missing/not-ready states. | VERIFIED | Focused pytest command passed all status/search route assertions, including typed 200 first-run responses. |
| 29 | D-08: FastAPI request handlers import only lightweight search contracts and client stubs, not LanceDB, torch, transformers, sentence-transformers, or embedding/indexing code. | VERIFIED | No forbidden imports found by AST test or direct grep across request-path search files. |
| 30 | D-12: Open-session filtering and counters are derived at query/status time from current SessionManager/tmux window state. | VERIFIED | `_search_open_session_count()` calls `tmux_manager.list_windows()` per request at `web/api.py:566-572`; route tests monkeypatch current tmux windows and verify open-session counters. |

**Score:** 30/30 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `src/codexbot/search/contracts.py` | Runtime-neutral Pydantic DTOs for provenance, identity, request, status, generation, routing metadata, and responses | VERIFIED | Exists, substantive, exported by `src/codexbot/search/__init__.py`, used by provider/API/tests, and covered by contract tests. |
| `tests/codexbot/test_search_contracts.py` | Contract, identity, input-bound, and import-boundary regression tests | VERIFIED | Exists and passed in focused pytest; includes AST import-boundary checks. |
| `src/codexbot/search/state.py` | Search-owned state namespace and generation metadata helpers | VERIFIED | Exists, substantive, uses `codexbot_dir() / "search"`, and is consumed by `client.py`. |
| `src/codexbot/search/client.py` | Lightweight typed provider for missing-index status and search responses | VERIFIED | Exists, substantive, dependency-light, and consumed by API routes. |
| `tests/codexbot/test_search_state.py` | State namespace, monitor isolation, and typed missing-index provider tests | VERIFIED | Exists and passed in focused pytest. |
| `src/codexbot/web/api.py` | Authenticated `GET /api/search/status` and `POST /api/search` route wiring | VERIFIED | Search routes are present, authenticated, provider-wired, and before the SPA fallback. |
| `tests/codexbot/test_web_api.py` | Auth, typed response, validation, and route smoke tests for search/status API | VERIFIED | Relevant search API tests passed in focused pytest. |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `src/codexbot/search/contracts.py` | `src/codexbot/transcript_parser.py` | Field alignment with `ParsedEntry` transcript offset/index/content/tool fields | WIRED | `gsd-sdk query verify.key-links` found required field patterns; grep confirmed parser and monitor emit the same provenance fields. |
| `src/codexbot/search/contracts.py` | `src/codexbot/session.py` | `SearchRoutingMetadata` mirrors mutable `WindowState` fields without entering `SearchRowIdentity` | WIRED | Key-link verifier found patterns; manual check confirmed identity/routing separation. |
| `src/codexbot/search/state.py` | `src/codexbot/utils.py` | `codexbot_dir() / "search"` | WIRED | `state.py` imports `codexbot_dir` and resolves the reserved search namespace. |
| `src/codexbot/search/client.py` | `src/codexbot/search/contracts.py` | `SearchStatusResponse` and `SearchResponse` construction | WIRED | `client.py` constructs typed status and search DTOs. |
| `src/codexbot/web/api.py` | `src/codexbot/search/client.py` | `get_status` and `search` provider calls from authenticated routes | WIRED | Routes call `search_client.get_status()` and `search_client.search()`. |
| `src/codexbot/web/api.py` | `src/codexbot/search/contracts.py` | `SearchRequest` request body validation | WIRED | `POST /api/search` accepts `SearchRequest`, and API tests verify 422 validation. |
| `tests/codexbot/test_web_api.py` | `src/codexbot/web/api.py` | FastAPI TestClient auth and response assertions | WIRED | Search route tests exercise auth, typed status/search, validation, redaction, and counters. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `src/codexbot/web/api.py` | `open_session_count` | `await tmux_manager.list_windows()` inside `_search_open_session_count()` | Yes - current tmux window count when available; `None` on expected listing failure | FLOWING |
| `src/codexbot/web/api.py` | `SearchRequest req` | FastAPI/Pydantic request body validation | Yes - bounded request DTO reaches provider | FLOWING |
| `src/codexbot/search/client.py` | `generation` | `read_generation_metadata()` from `src/codexbot/search/state.py` | Yes - active current-schema generation when present; missing/invalid becomes honest `missing`/`unavailable` status | FLOWING |
| `src/codexbot/search/client.py` | `results` | Intentional Phase 1 stub until later retrieval phases | No real retrieval by design; response includes `outcome="not_ready"` and status state to avoid "no matches" ambiguity | VERIFIED AS INTENTIONAL |
| `src/codexbot/search/contracts.py` | `SearchRowIdentity` | `TranscriptProvenance` plus `chunk_index` | Yes - stable transcript fields flow into row identity without mutable routing metadata | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| MVP roadmap goal validates as a User Story | `gsd-sdk query user-story.validate --story "...workflows." --raw` | `valid: true`; role/capability/outcome slots parsed | PASS |
| Plan artifacts exist and are substantive | `gsd-sdk query verify.artifacts ... --raw` for all three plans | 7/7 artifacts passed | PASS |
| Plan key links are wired | `gsd-sdk query verify.key-links ... --raw` for all three plans | 7/7 key links verified | PASS |
| Search contracts/state/API behavior | `uv run pytest tests/codexbot/test_search_contracts.py tests/codexbot/test_search_state.py tests/codexbot/test_web_api.py::test_search_status_requires_auth tests/codexbot/test_web_api.py::test_search_requires_auth tests/codexbot/test_web_api.py::test_search_status_returns_typed_missing tests/codexbot/test_web_api.py::test_search_stub_returns_typed_not_ready tests/codexbot/test_web_api.py::test_search_rejects_oversized_or_out_of_range_request tests/codexbot/test_web_api.py::test_search_responses_do_not_leak_sensitive_fields -q` | `26 passed in 0.55s` | PASS |
| Focused lint | `uv run ruff check src/codexbot/search src/codexbot/web/api.py tests/codexbot/test_search_contracts.py tests/codexbot/test_search_state.py tests/codexbot/test_web_api.py` | `All checks passed!` | PASS |
| Focused type check | `uv run pyright src/codexbot/search src/codexbot/web/api.py` | `0 errors, 0 warnings, 0 informations` | PASS |
| Direct provider semantics | `uv run python -c "from codexbot.search.contracts import SearchRequest; from codexbot.search.client import get_status, search; ..."` | `direct search provider spot-check passed` | PASS |
| Heavy import boundary | `rg -n "lancedb|torch|transformers|sentence_transformers|fastembed|codexbot\\.search\\.(worker|index|retrieval|ranking|queue)" src/codexbot/web/api.py src/codexbot/search` | No matches | PASS |
| Monitor-state isolation scan | `rg -n "monitor_state|state\\.json|MonitorState|config\\.monitor_state_file|atomic_write_json" src/codexbot/search` | No matches | PASS |

### Probe Execution

| Probe | Command | Result | Status |
|---|---|---|---|
| n/a | `find scripts -path '*/tests/probe-*.sh' -type f` and phase plan/summary probe grep | No conventional or declared phase probes found. | SKIPPED |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| CORP-03 | `01-01-PLAN.md` | Codi stores stable provenance for every indexed item, including runtime, session ID when known, transcript source, transcript offset or index, role/content type, and optional tool identifier. | SATISFIED | `TranscriptProvenance` includes every listed field and tests assert field coverage. REQUIREMENTS traceability maps CORP-03 to Phase 1. |
| CORP-04 | `01-01-PLAN.md` | Codi uses transcript provenance as indexed row identity and uses current tmux `window_id` only as mutable routing metadata. | SATISFIED | `SearchRowIdentity` excludes mutable routing fields; `SearchRoutingMetadata` contains `window_id`; tests prove identity is stable while routing changes. REQUIREMENTS traceability maps CORP-04 to Phase 1. |
| CORP-06 | `01-02-PLAN.md` | Codi treats the search index as derived and rebuildable from transcript/session state, not as a source of truth. | SATISFIED | Search state is reserved under `$CODEXBOT_DIR/search`, generation metadata is optional/rebuildable, and tests prove status/search do not mutate `monitor_state.json`. REQUIREMENTS traceability maps CORP-06 to Phase 1. |
| OPS-02 | `01-03-PLAN.md` | Codi exposes authenticated search and search-status API surfaces without importing embedding models in request handlers. | SATISFIED | `GET /api/search/status` and `POST /api/search` require auth; focused tests verify 401/200/422 behavior; static and grep checks find no model/index imports. REQUIREMENTS traceability maps OPS-02 to Phase 1. |

No orphaned Phase 1 requirements were found: `.planning/REQUIREMENTS.md` maps only CORP-03, CORP-04, CORP-06, and OPS-02 to Phase 1, and all four appear in plan frontmatter.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---|---|---|---|
| `src/codexbot/search/client.py` | 15 | `"search query backend is not available"` | INFO | Intentional honest Phase 1 unavailable status when active generation metadata exists but no retrieval backend exists yet. Not a stub gap because API response exposes `not_ready`/`unavailable` semantics. |
| `src/codexbot/web/api.py` | 1684 | `dev_placeholder` | INFO | Pre-existing static bundle fallback from commit `a7512c0`, unrelated to Phase 1 search route implementation and not a search placeholder. |

No `TBD`, `FIXME`, or `XXX` debt markers were found in the phase-modified search/API/test files.

### Human Verification Required

None. The phase delivers backend contract/API behavior, and the relevant user-story outcome is covered by automated API, contract, state-isolation, import-boundary, lint, type, and direct provider checks.

### Gaps Summary

No blocking gaps remain. The previous verification blocker was the non-User-Story roadmap goal; commit `d4d70fc` corrected the authoritative Phase 1 goal, and `gsd-sdk query user-story.validate` now returns `valid: true`.

Disconfirmation pass:

- Partial requirement candidate checked: active generation metadata without a query backend could have misleadingly reported `ready`; current provider reports `state="unavailable"`, `available=False`, and `outcome="not_ready"`.
- Misleading test candidate checked: the API tests do not merely assert 200/empty results; they assert status state, outcome, limits, auth, validation, redaction, and counters.
- Uncovered error path candidate checked: tmux listing errors are caught in `_search_open_session_count()` and omit counters without exposing exception text or blocking status/search responses.

---

_Verified: 2026-05-21T14:14:06Z_
_Verifier: the agent (gsd-verifier)_
