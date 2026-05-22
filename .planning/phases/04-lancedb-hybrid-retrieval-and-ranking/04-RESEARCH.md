# Phase 4: LanceDB Hybrid Retrieval and Ranking - Research

**Researched:** 2026-05-22
**Status:** Complete

## Research Question

What needs to be known to plan Phase 4 well: local LanceDB hybrid retrieval,
Qwen3 embedding integration, exact-first ranking, backend result contracts,
degraded lexical behavior, and validation coverage for open-session Codi
search.

## Source Notes

Primary sources checked:

- LanceDB hybrid search docs:
  `https://docs.lancedb.com/search/hybrid-search`
- LanceDB native FTS docs:
  `https://lancedb.github.io/lancedb/fts/`
- LanceDB merge insert/update docs:
  `https://docs.lancedb.com/tables/update`
- LanceDB Python API docs:
  `https://lancedb.github.io/lancedb/python/python/`
- Qwen3 Embedding GitHub docs:
  `https://github.com/QwenLM/Qwen3-Embedding`
- Qwen3-Embedding-0.6B Hugging Face model card:
  `https://huggingface.co/Qwen/Qwen3-Embedding-0.6B`

Relevant findings:

- LanceDB supports local embedded databases via `lancedb.connect(path)` and
  table search via vector, FTS, and `query_type="hybrid"`.
- LanceDB FTS is BM25-based. Native Lance FTS uses
  `table.create_fts_index("text", use_tantivy=False)`, and phrase queries need
  `with_position=True`, at the cost of larger index size and indexing time.
- LanceDB hybrid search combines vector and FTS results and can use explicit
  `.vector(query_vector).text(query_text)` when the application owns embedding.
- LanceDB table upserts use `merge_insert("id").when_matched_update_all()
  .when_not_matched_insert_all().execute(rows)`. A scalar index on the join
  column can avoid full-table scans.
- Qwen3-Embedding-0.6B is a 0.6B text embedding model with 32K context and up
  to 1024-dimensional vectors. It supports MRL/custom dimensions and
  instruction-aware queries.
- Qwen docs recommend Sentence Transformers with `transformers>=4.51.0` and
  `sentence-transformers>=2.7.0`; query-side instructions improve retrieval
  quality, while documents do not need the same instruction prefix.

## Codebase Findings

### Existing Search Foundation

- `src/codexbot/search/contracts.py` already defines stable transcript
  provenance, row identity, routing metadata, search status, grouped results,
  nested hits, request DTOs, and outcomes.
- `src/codexbot/search/backfill.py` already produces deterministic
  `SearchBackfillDocument` chunks from current open sessions.
- `src/codexbot/search/live.py` already upserts live documents into
  `generations/<id>/documents.jsonl` and hides stale transcript sources.
- `src/codexbot/search/worker.py` already owns backfill, rebuild, and live
  drain commands; this is the right place to add index materialization and live
  LanceDB upserts.
- `src/codexbot/search/client.py` is the dependency-light request-path provider.
  It must not import LanceDB, torch, transformers, or sentence-transformers at
  module import time.
- `src/codexbot/web/api.py` already exposes authenticated `/api/search/status`
  and `/api/search` through the lightweight client.

### Existing Testing Pattern

- Search tests use `tmp_path`, `monkeypatch.setenv("CODEXBOT_DIR", str(tmp))`,
  fake tmux/session objects, JSONL fixtures, and direct module calls.
- Current import-boundary tests already list heavy import roots:
  `lancedb`, `sentence_transformers`, `torch`, and `transformers`.
- Plan tasks should extend tests before implementation when possible; this repo
  has good coverage for contracts, state, worker, live queue, web API status,
  and backfill behavior.

## Recommended Architecture

### Storage Shape

Use one LanceDB table per active generation, stored under
`CODEXBOT_DIR/search/generations/<generation_id>/lancedb` or an equivalent
generation-owned directory. The table should be chunk-level and keyed by a
stable string row id derived from `SearchRowIdentity`.

Recommended table columns:

- `row_id`: deterministic stable row key from serialized `SearchRowIdentity`
- `text`: chunk text
- `vector`: embedding vector, initially 1024 dimensions for
  Qwen3-Embedding-0.6B unless validation selects a lower MRL dimension
- `runtime`, `session_id`, `transcript_source`, `transcript_offset`,
  `transcript_index`, `role`, `content_type`, `tool_name`, `tool_use_id`,
  `source_order`, `chunk_index`, `chunk_count`, `timestamp`
- `window_id`, `cwd`, `name`, `status`, `pinned`, `sort_order` as mutable
  routing/display metadata

Create indexes:

- FTS index on `text`; use `with_position=True` if exact phrase highlighting or
  phrase matching is implemented through LanceDB FTS, otherwise keep it off
  initially to reduce local index cost.
- Vector index on `vector` once enough rows exist. For tiny test fixtures,
  flat search may be acceptable.
- Scalar index on `row_id` before merge insert/upsert if LanceDB supports it in
  the installed version.

### Embedding Provider

Add a provider boundary such as `src/codexbot/search/embedding.py` that lazy
imports Sentence Transformers only inside worker/query operations. The provider
should:

- Default model id: `Qwen/Qwen3-Embedding-0.6B`.
- Use query instruction text for query embeddings, e.g. a Codi-specific
  retrieval instruction about finding relevant Codex/Claude session transcript
  chunks.
- Not instruction-prefix document chunks.
- Normalize vectors if the selected model does not already produce normalized
  output; use cosine or dot similarity consistently with LanceDB.
- Expose dimension in index metadata and fail fast if an active table's vector
  dimension does not match the configured embedder.
- Support configuration for model id, local cache path, batch size, max length,
  and optional output dimension, but avoid Web UI tuning in this phase.

### Retrieval Provider

Add a retrieval/index module under `src/codexbot/search/`, but keep
`search.client` dependency-light. A safe pattern is:

- `search.client.search()` imports the retrieval provider inside the function
  body or calls through a lazy provider factory.
- If heavy imports fail or semantic retrieval is unhealthy, return lexical plus
  metadata results with `state="degraded"` and a clear reason.
- If no active generation/index exists, preserve existing typed missing or
  unavailable responses.

### Ranking Strategy

Implement exact-first hybrid ranking in app code instead of relying only on
LanceDB's default hybrid reranker:

- Use LanceDB FTS for BM25 lexical candidates.
- Use LanceDB vector search for semantic candidates.
- Merge candidates by stable row id.
- Boost exact technical matches for quoted phrases, paths, commands, symbols,
  stack-trace-like text, and ticket IDs.
- Apply metadata filters before ranking when explicit filters are present.
- Apply metadata text matches as capped boosts, not as standalone dominance.
- Group final rows by current open `window_id`.
- Session score = best hit score plus capped support from distinct additional
  hits.
- Return bounded hits per session with match labels: `lexical`, `semantic`,
  `metadata`, and `hybrid`.

### Result Payload Changes

Extend contracts rather than replacing them:

- Add missing request filters: `window_id`, `session_id`, `pinned`,
  `recent_after` or `recent_seconds`, and possibly `name` if needed for
  metadata matching.
- Add highlight span DTOs for exact text ranges inside snippets.
- Add per-hit fields for labels/source order if existing `SearchHit.outcomes`
  is not enough.
- Keep raw backend scores internal. Expose normalized scores only.

### Worker Integration

The worker should maintain both existing generation JSONL and the LanceDB table:

- Initial backfill/rebuild: materialize generation JSONL, then build the LanceDB
  table from `SearchBackfillDocument` rows before search is `ready`.
- Live drain: after queue rows are leased and generation JSONL upsert succeeds,
  embed/upsert matching LanceDB rows in the same 32-item or 60-second flush.
- Failure policy: if LanceDB/vector write fails, queue rows should retry and
  status should degrade; normal Codi Web UI and Telegram delivery should keep
  working.

## Plan Implications

Recommended plan split:

1. Contracts, filters, highlight DTOs, lexical/degraded ranking scaffolding, and
   import-boundary tests.
2. LanceDB table/index and Qwen embedding provider, wired into backfill/rebuild
   and live worker upsert.
3. Hybrid query/ranking provider, API integration, ranking fixtures, degraded
   fallback, and local model/index smoke validation.

## Validation Architecture

### Test Dimensions

1. Contract/API shape
   - Search request accepts all Phase 4 filters.
   - Search response returns grouped sessions, bounded hits, normalized scores,
     match labels, snippets, positions/timestamps, and exact highlight spans.

2. Import boundary
   - `src/codexbot/web/api.py` and module import of `src/codexbot/search/client.py`
     do not import LanceDB, torch, transformers, or sentence-transformers.
   - Heavy imports happen only inside worker/retrieval/embedding operations.

3. LanceDB index materialization
   - Generation documents produce a chunk-level LanceDB table under
     `CODEXBOT_DIR/search`.
   - Upsert by `row_id` is idempotent.
   - FTS index exists on `text`; vector column dimension matches model metadata.

4. Retrieval/ranking
   - Exact paths, commands, stack traces, symbols, ticket IDs, and quoted
     phrases outrank weaker semantic matches.
   - Semantic paraphrases find relevant Codex and Claude chunks.
   - Repeated text does not outrank a directly relevant session solely by
     frequency.
   - Metadata filters constrain results; metadata text adds only capped boosts.

5. Degraded behavior
   - Missing/unhealthy semantic model returns lexical plus metadata results with
     `state="degraded"` and a reason.
   - Missing LanceDB/index still returns typed not-ready/unavailable responses.

6. Worker/live behavior
   - Initial backfill/rebuild builds or refreshes the LanceDB table.
   - Live queue drain embeds/upserts rows during the existing 32/60 flush.
   - Queue rows retry or fail safely when index writes fail.

7. Local model smoke
   - A local smoke command embeds a tiny batch with Qwen3-Embedding-0.6B or a
     configured substitute, records vector dimension, runtime, and error state,
     and does not require cloud services.

### Recommended Commands

- Target contracts/API:
  `uv run pytest tests/codexbot/test_search_contracts.py tests/codexbot/test_web_api.py -q`
- Target index/retrieval/worker:
  `uv run pytest tests/codexbot/test_search_index.py tests/codexbot/test_search_retrieval.py tests/codexbot/test_search_worker.py tests/codexbot/test_search_live_queue.py -q`
- Full repo:
  `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/ && uv run pyright src/codexbot/ && /tmp/codexbot-venv/bin/pytest -q`
- Frontend build is not required in Phase 4 unless API TypeScript types are
  changed for Phase 5 prework.

## Risks And Mitigations

- **Dependency bloat:** Sentence Transformers and torch are heavy. Mitigate by
  lazy imports, clear degraded behavior, and keeping request-path imports clean.
- **LanceDB API drift:** Plan should include focused tests for the exact APIs
  used: `connect`, `create_table`, `open_table`, `create_fts_index`,
  `merge_insert`, vector search, FTS search, and hybrid search if used.
- **Mac mini overload:** Keep batch size configurable and add smoke validation
  before readiness. Do not embed synchronously in FastAPI or monitor listener
  paths.
- **Ranking opacity:** Return match labels, normalized scores, and highlight
  spans so future UI work can explain why a session matched.
- **Stale routing:** Always group/filter through current open tmux window state
  and stale-source records, never through transcript source alone.

## Research Complete

Phase 4 is ready for planning with a three-plan split: contracts/ranking
scaffolding, index/materialization, and hybrid query plus validation.
