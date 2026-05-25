---
status: passed
phase: 04-lancedb-hybrid-retrieval-and-ranking
verified_at: 2026-05-22T18:02:00Z
requirements:
  - SRCH-02
  - SRCH-04
  - SRCH-05
  - SRCH-06
  - RETR-01
  - RETR-02
  - RETR-03
  - RETR-04
  - RETR-05
  - RETR-06
  - RETR-07
  - RETR-08
  - OPS-01
score: 12/12
---

# Phase 04 Verification: LanceDB Hybrid Retrieval and Ranking

## Verdict

Status: passed

Phase 4 achieved the backend goal: Codi can search active generation-backed open sessions with exact-first lexical results, completed-index ready status, hybrid semantic candidate support, degraded lexical fallback, grouped routeable results, and worker-owned local index materialization.

## Requirement Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| SRCH-02 | passed | Search remains scoped to active generation/open-session documents and stale sources are filtered in retrieval fixtures. |
| SRCH-04 | passed | `SearchSessionResult` groups nested hits by `routing.window_id`; Web API fixture returns grouped payloads. |
| SRCH-05 | passed | Ranking applies capped metadata boosts and metadata-only matches do not create top results. |
| SRCH-06 | passed | Backend filters cover runtime, cwd, role, content type, status, window ID, session ID, pinned, and recent time. |
| RETR-01 | passed | Lexical degraded retrieval covers exact paths, quoted/technical terms, commands, stack-like text, symbols, and ticket-like matches. |
| RETR-02 | passed | Completed index metadata plus semantic score provider supports semantic paraphrase retrieval. |
| RETR-03 | passed | Hybrid candidate merge labels hits as `hybrid` when lexical and semantic channels match the same row. |
| RETR-04 | passed | Embedding provider defaults to `Qwen/Qwen3-Embedding-0.6B` and records model metadata. |
| RETR-05 | passed | Embedding/index work is local provider code with fakeable tests and no cloud API provider. |
| RETR-06 | passed | Hits expose normalized scores, bounded snippets, outcomes, source order, timestamps, and match labels. |
| RETR-07 | passed | Highlight DTO validates exact snippet spans and rejects invalid offsets. |
| RETR-08 | passed | Ranking fixtures protect exact technical matches over weaker semantic/repeated text. |
| OPS-01 | passed | FastAPI/search client import boundaries stay free of LanceDB, torch, transformers, and sentence-transformers at import time. |

## Must-Have Verification

| Decision | Status | Evidence |
|----------|--------|----------|
| D-01 exact technical matches protected | passed | `test_lexical_exact_technical_match_returns_grouped_highlighted_result` and hybrid score merge. |
| D-02 metadata filters/boosts bounded | passed | `test_lexical_filters_narrow_backend_results` and `test_metadata_only_matches_do_not_create_top_result`. |
| D-03 best hit plus capped diversity | passed | `session_results_from_candidates` caps support from additional hits. |
| D-04 BM25-style/exact lexical scaffolding | passed | `ranking.py` token/phrase/technical label scoring and `bm25_like_term_weight`. |
| D-05 group by open window ID | passed | Retrieval groups by `SearchRoutingMetadata.window_id`; stale source test hides closed rows. |
| D-06 snippets, labels, timestamps, source order, highlights | passed | `SearchHit` contract and retrieval fixtures. |
| D-07 full backend filter contract | passed | `SearchRequest` and retrieval filter tests. |
| D-08 normalized scores/no raw backend scores | passed | Contract/API tests assert no raw score fields. |
| D-09 chunk-level local table metadata | passed | `index.py` row conversion and `SearchIndexMetadata` tests. |
| D-10 semantic failures degrade | passed | `test_semantic_failure_returns_safe_lexical_degraded_results`. |
| D-11 live worker flush upserts index before done | passed | Worker tests patch index upsert and fail queue rows when index upsert fails. |
| D-12 readiness gated by fixtures and smoke helper | passed | Ready-status fixtures, full test suite, and `smoke-search-index` command coverage. |

## Automated Validation

- `uv run pytest tests/codexbot/test_search_retrieval.py tests/codexbot/test_search_index.py tests/codexbot/test_search_worker.py tests/codexbot/test_web_api.py -q` - passed, 72 tests.
- `uv run pytest tests/codexbot/test_search_contracts.py tests/codexbot/test_search_state.py tests/codexbot/test_search_live_queue.py tests/codexbot/test_search_backfill.py -q` - passed, 39 tests.
- `uv run ruff check src/ tests/` - passed.
- `uv run ruff format --check src/ tests/` - passed.
- `uv run pyright src/codexbot/` - passed.
- `uv run pytest -q` - passed, 560 tests, 2 existing PTB deprecation warnings.
- `gsd-sdk query verify.schema-drift 04` - passed, no schema drift detected.

## Environment Notes

- `/tmp/codexbot-venv/bin/pytest -q` could not run because `/tmp/codexbot-venv/bin/pytest` does not exist in this environment. The full suite was run with `uv run pytest -q`.
- The real `codexbot-search-worker smoke-search-index` command was not executed against Qwen because that would download/load the model in this environment. Unit tests verify the command shape with fake materialization; live host smoke remains an operational validation item.

## Human Verification

None required for Phase 4 backend implementation.

## Gaps

None.
