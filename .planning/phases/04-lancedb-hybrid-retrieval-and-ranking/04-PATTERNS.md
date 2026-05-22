# Phase 04: LanceDB Hybrid Retrieval and Ranking - Pattern Map

**Mapped:** 2026-05-22
**Files analyzed:** 14
**Analogs found:** 14 / 14

## Scope Guard

Phase 4 is backend retrieval/indexing only. The executor must not add browser
search controls, result panes, session navigation UX, Telegram search commands,
closed-session search, advanced query syntax, or Web UI model tuning controls.

Embedding, LanceDB writes, retrieval queries, and index maintenance stay in
worker/provider modules under `src/codexbot/search/`. FastAPI request modules
may import lightweight contracts/client code only.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `pyproject.toml` | dependency/config | local search dependencies and script exposure | existing project dependency and worker script entries | exact |
| `src/codexbot/search/contracts.py` | model | request filters, highlights, labels, status | existing search DTOs in same file | exact |
| `src/codexbot/search/state.py` | utility | generation-owned LanceDB/index paths and metadata | existing generation/status/queue path helpers | exact |
| `src/codexbot/search/index.py` | storage service | LanceDB table create/open/upsert/index | `src/codexbot/search/live.py` document upsert plus `state.py` paths | role-match |
| `src/codexbot/search/embedding.py` | provider | lazy local embedding model load and vectorization | `src/codexbot/search/worker.py` process boundary | role-match |
| `src/codexbot/search/retrieval.py` | query service | lexical/vector/hybrid candidates, filters, ranking | `src/codexbot/search/client.py` status provider and `live.py` stale filtering | role-match |
| `src/codexbot/search/ranking.py` | algorithm | exact boosts, score normalization, session grouping | `src/codexbot/search/contracts.py` result DTOs | role-match |
| `src/codexbot/search/worker.py` | worker service | backfill/rebuild/live index materialization | existing worker commands and live drain loop | exact |
| `src/codexbot/search/client.py` | request-safe facade | lazy retrieval call and degraded fallback | existing missing/building/unavailable provider | exact |
| `src/codexbot/web/api.py` | route | authenticated status/search wrapper | existing `/api/search` routes | exact |
| `tests/codexbot/test_search_contracts.py` | test | DTO bounds/import boundaries | existing contract tests | exact |
| `tests/codexbot/test_search_index.py` | test | LanceDB/index/embedding provider behavior | `test_search_worker.py` and `test_search_state.py` | role-match |
| `tests/codexbot/test_search_retrieval.py` | test | ranking/filter/snippet fixtures | `test_search_backfill.py` fixtures and `test_web_api.py` response checks | role-match |
| `tests/codexbot/test_search_worker.py` | test | worker build/live upsert lifecycle | existing worker generation/live drain tests | exact |

## Pattern Assignments

### Request-Path Import Boundary

**Analogs:** `tests/codexbot/test_search_contracts.py`,
`src/codexbot/web/api.py`, `src/codexbot/search/client.py`

Existing tests parse imports and reject heavy modules in request-path code.
Preserve that pattern by allowing heavy modules only in `index.py`,
`embedding.py`, `retrieval.py`, `ranking.py`, and worker-invoked functions.

Apply to Phase 4:

- Extend `SEARCH_IMPLEMENTATION_MODULES` if new search submodules are allowed.
- Keep `web/api.py` imports unchanged except for lightweight contracts.
- Lazy-import retrieval providers from inside `search.client.search()`.
- Add regression tests that importing `codexbot.search.client` does not import
  `lancedb`, `torch`, `transformers`, or `sentence_transformers`.

### Generation-Owned Derived State

**Analogs:** `src/codexbot/search/state.py`,
`src/codexbot/search/backfill.py`, `src/codexbot/search/live.py`

Current generation artifacts live under `CODEXBOT_DIR/search/generations/<id>`.
The LanceDB directory and index metadata should be sibling artifacts owned by
the same generation, not global mutable state.

Apply to Phase 4:

- Add path helpers such as `generation_lancedb_dir(generation_id)` and
  `generation_index_metadata_path(generation_id)`.
- Keep existing `documents.jsonl` as rebuildable source material.
- Activate readiness only when the generation manifest and index metadata agree
  on schema version, generation id, model id, vector dimension, and completed
  index state.

### Chunk-Level Row Identity

**Analogs:** `SearchBackfillDocument`,
`SearchRowIdentity.from_provenance()`, `queue_id_for_document()`

Phase 4 should not invent a new identity scheme. LanceDB rows should use a
stable `row_id` string derived from serialized `SearchRowIdentity` so backfill
and live updates upsert the same logical row.

Apply to Phase 4:

- Store full identity/provenance fields in table columns for filtering and
  response reconstruction.
- Use `merge_insert("row_id")` for idempotent upserts.
- Add tests proving a routing-only change updates metadata but does not create
  a second search row.

### Worker-Owned Index Build

**Analogs:** `src/codexbot/search/worker.py`,
`src/codexbot/search/supervisor.py`, `tests/codexbot/test_search_worker.py`

The worker already owns initial backfill, rebuild, and live queue drain. Phase
4 should extend this boundary rather than creating a new request-path indexer.

Apply to Phase 4:

- Initial backfill/rebuild should build the LanceDB table after generation
  documents are materialized and before search reports `ready`.
- Live drain should upsert LanceDB rows in the same batch as generation JSONL
  upserts.
- Index failures should leave queue rows retryable/failed and surface degraded
  status, without blocking Web UI/Telegram delivery.

### Ranking Fixtures

**Analogs:** `tests/codexbot/test_search_backfill.py`,
`tests/codexbot/test_search_live_queue.py`,
`tests/codexbot/test_web_api.py`

Use tiny synthetic documents and fake providers. Do not depend on the real
Qwen model for most ranking tests; reserve the real model for a smoke command.

Apply to Phase 4:

- Fixture dimensions: exact path/command/stack/symbol matches, semantic
  paraphrase, repeated noisy text, Codex record, Claude record, metadata-only
  boost, stale-source filtering, and open-window grouping.
- Use fake vector scores for deterministic hybrid ranking tests.
- Assert result ordering, labels, snippets, highlights, hit bounds, session
  grouping by `window_id`, and filters.

## Pattern Map Complete

This map is sufficient for Phase 4 planning and execution.
