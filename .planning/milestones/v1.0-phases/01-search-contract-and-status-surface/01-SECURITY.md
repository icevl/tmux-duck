---
phase: 01
slug: search-contract-and-status-surface
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-21
register_authored_at_plan_time: true
---

# Phase 01 - Security

Per-phase security contract: threat register, accepted risks, and audit trail.

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Authenticated Web UI API | Browser callers reach local FastAPI search endpoints through the existing Web UI cookie auth dependency. | Search status and bounded search request/response JSON. |
| Search request validation | User-controlled search text and result limits enter Pydantic DTOs before provider handling. | Query text, limit, hits-per-session, and optional metadata filters. |
| Search provider response | FastAPI routes expose search readiness and missing/not-ready search responses while retrieval is intentionally absent. | State, reason, counters, generation metadata, empty result groups. |
| Derived search state | Search generation metadata is read from `CODEXBOT_DIR/search`, separate from Codi authoritative session and monitor state. | Rebuildable generation metadata only. |
| Request-path imports | FastAPI handlers may import lightweight search contracts/provider code, but not worker, index, retrieval, ranking, queue, embedding, or model packages. | Python module dependencies on the hot request path. |

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-01-01 | Information Disclosure | `GET /api/search/status`, `POST /api/search` | mitigate | Both routes use existing `Depends(require_auth)`. Tests prove unauthenticated status and search calls return 401. | closed |
| T-01-02 | Denial of Service | `SearchRequest` body | mitigate | `SearchRequest` bounds query text to 1..500 characters, `limit` to 1..50, and `hits_per_session` to 1..10. Unit and API tests verify oversized/out-of-range inputs fail validation. | closed |
| T-01-03 | Information Disclosure | Search status and search response JSON | mitigate | Status/search responses expose typed state, reason, scope, counters, generation metadata, and empty result structures only. Tests reject secret env names, raw transcript fields, monitor-state filenames, local temp paths, and model/import details. | closed |
| T-01-04 | Tampering | Search row identity and derived state helpers | mitigate | `SearchRowIdentity` excludes mutable tmux routing/display fields, and search state helpers read only `CODEXBOT_DIR/search/generation.json`. Tests prove routing metadata changes do not alter identity and status/search do not create or mutate `monitor_state.json`. | closed |
| T-01-05 | Denial of Service | FastAPI/search request-path imports | mitigate | Request-path search modules import only lightweight contracts/provider code. Static AST tests and source grep reject LanceDB, torch, transformers, sentence-transformers, FastEmbed, and search worker/index/retrieval/ranking/queue imports. | closed |

Status: open, closed
Disposition: mitigate, accept, transfer

## Evidence

| Control | Evidence |
|---------|----------|
| Authenticated route protection | `src/codexbot/web/api.py:574-588`; `tests/codexbot/test_web_api.py::test_search_status_requires_auth`; `tests/codexbot/test_web_api.py::test_search_requires_auth` |
| Request bounds | `src/codexbot/search/contracts.py:140-150`; `tests/codexbot/test_search_contracts.py::test_search_request_bounds_reject_oversized_inputs`; `tests/codexbot/test_web_api.py::test_search_rejects_oversized_or_out_of_range_request` |
| Safe typed responses | `src/codexbot/search/client.py:24-61`; `tests/codexbot/test_search_state.py::test_missing_index_status_serializes_as_safe_typed_json`; `tests/codexbot/test_web_api.py::test_search_responses_do_not_leak_sensitive_fields` |
| Identity and state tamper controls | `src/codexbot/search/contracts.py:49-88`; `src/codexbot/search/state.py:19-49`; `tests/codexbot/test_search_contracts.py::test_row_identity_excludes_mutable_window_metadata`; `tests/codexbot/test_search_state.py::test_search_state_does_not_modify_monitor_state` |
| Import-boundary controls | `src/codexbot/web/api.py:61-62`; `tests/codexbot/test_search_contracts.py::test_web_search_boundary_has_no_heavy_imports`; source grep for forbidden heavy/search implementation imports returned no matches. |

## Verification Commands

```bash
uv run pytest tests/codexbot/test_search_contracts.py::test_search_request_bounds_reject_oversized_inputs tests/codexbot/test_search_contracts.py::test_row_identity_excludes_mutable_window_metadata tests/codexbot/test_search_contracts.py::test_web_search_boundary_has_no_heavy_imports tests/codexbot/test_search_state.py::test_search_state_does_not_modify_monitor_state tests/codexbot/test_search_state.py::test_missing_index_status_serializes_as_safe_typed_json tests/codexbot/test_web_api.py::test_search_status_requires_auth tests/codexbot/test_web_api.py::test_search_requires_auth tests/codexbot/test_web_api.py::test_search_rejects_oversized_or_out_of_range_request tests/codexbot/test_web_api.py::test_search_responses_do_not_leak_sensitive_fields -q
rg -n "lancedb|torch|transformers|sentence_transformers|fastembed|codexbot\\.search\\.(worker|index|retrieval|ranking|queue)" src/codexbot/web/api.py src/codexbot/search
rg -n "monitor_state|MonitorState|config\\.monitor_state_file|atomic_write_json" src/codexbot/search
```

Results on 2026-05-21:

- Focused security tests: 13 passed.
- Heavy import grep: no matches in source request-path files.
- Search monitor-state write grep: no matches in `src/codexbot/search`.

## Accepted Risks Log

No accepted risks.

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-21 | 5 | 5 | 0 | Codex / gsd-secure-phase |

## Sign-Off

- [x] All threats have a disposition: mitigate, accept, or transfer.
- [x] Accepted risks documented in Accepted Risks Log.
- [x] `threats_open: 0` confirmed.
- [x] `status: verified` set in frontmatter.

Approval: verified 2026-05-21
