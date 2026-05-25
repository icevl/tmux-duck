# AI Integration Specification - Phase 06: Operational Hardening and Model Tuning

## Phase Overview

**Phase Goal**: Search remains locally reliable under worker failures, resource limits, model validation, and degraded semantic availability.

**AI System Type**: Local hybrid retrieval and semantic search over Codex/Claude session transcripts.

**Description**:
Codi indexes open Codex and Claude tmux-backed sessions into a local search corpus. The system combines lexical retrieval for exact command/path/error matching with local semantic embeddings for paraphrase and task-level session discovery. Search must stay isolated from chat, terminal, Telegram, WebSocket, and session-list hot paths, and must degrade to lexical behavior when semantic embedding or the vector index is unavailable.

---

## 1. AI System Scope

### What AI Does

- Embeds transcript chunks from Codex and Claude sessions using a local Sentence Transformers model.
- Stores normalized vectors and chunk metadata in LanceDB alongside lexical-searchable text.
- Retrieves relevant chunks for a user query using exact lexical signals, semantic similarity, and custom ranking/labeling.
- Reports search readiness, degraded mode, queue lag, worker health, and indexing progress to the Web UI.

### What AI Does NOT Do

- It does not generate user-facing answers from retrieved chunks.
- It does not summarize, rewrite, or mutate session history.
- It does not choose or switch sessions automatically.
- It does not run model work inside FastAPI/WebSocket request handlers.
- It does not replace lexical search; exact technical matches remain first-class.

### Critical Failure Modes

1. **Hot-path blocking**: model import, model loading, embedding, or index rebuild work blocks chat, terminal, Telegram, WebSocket, or the session list.
2. **Exact-match regression**: semantic ranking hides a relevant command, path, issue key, file name, traceback, or tmux/window identifier.
3. **Stale readiness**: the UI reports search as ready while the worker is stalled, the queue is lagging, or the index generation is stale.
4. **Silent semantic failure**: model/runtime/index errors produce missing results without an explicit lexical-only degraded status.
5. **Status leakage**: worker errors, eval output, or UI status expose raw secrets, tokens, or sensitive transcript fragments.

---

## 1b. Domain Context

### Business / Domain Background

Codi is a local bridge between tmux-based Codex/Claude sessions and browser/Telegram front ends. Users keep many active development sessions open and need to find the right window by task, command, error, file path, or recent conversation. The search feature is a local productivity and operations tool: wrong or stale results waste time and can send a user back into the wrong agent session.

### Domain-Specific Quality Criteria

| Criterion | Good | Bad | Stakes | Source |
| --- | --- | --- | --- | --- |
| Exact technical recall | Queries for paths, commands, issue keys, errors, or session IDs return the matching session near the top with exact-match labels. | Semantic results outrank or hide exact matches. | Users reopen the wrong session or miss the real failure context. | Codi maintainer review, transcript fixtures |
| Semantic session relevance | Paraphrases such as "the search indexing work" find the right recent sessions even if exact words differ. | Results are topically broad, stale, or from unrelated windows. | Session switching becomes unreliable for long-lived work. | Sanitized Codex/Claude histories |
| Freshness and readiness truthfulness | UI status shows worker heartbeat, queue lag, indexed/open session counts, backfill progress, and degraded states. | UI says ready while worker/index is stale or failing. | Users trust incomplete results and stop debugging the actual search path. | Phase 6 success criteria |
| Local resource isolation | Embedding throughput, batch size, memory, and chunk size stay inside Mac-mini-friendly limits without affecting Codi hot paths. | Backfill or model loading causes UI latency, dropped WebSockets, or slow terminal/chat delivery. | Local deployment quality regresses across the whole app. | Phase 6 success criteria and local benchmark |
| Privacy-safe status | Status and eval artifacts expose sanitized error classes and counts, not raw transcript secrets. | Tokens, local paths with secrets, or raw stack snippets leak through UI status/logs. | Local secret exposure in the browser or logs. | Security review |

### Known Domain Failure Patterns

- Exact commands and paths are rare tokens; dense embeddings alone may under-rank them.
- Long tool outputs can dominate chunks and drown out the conversational turn that gives the work context.
- A completed backfill can become stale as sessions keep receiving messages.
- Local embedding models can be unavailable on first start because weights are not downloaded or `local_files_only` is enabled.
- Model dependency drift can break Qwen loading even when lexical search and LanceDB still work.

### Regulatory / Compliance Context

There is no external regulatory framework for this local-only feature. The relevant constraints are local privacy, secret hygiene, and keeping search failures isolated from the core Codi control plane.

### Domain Expert Evaluation

Domain review should involve:

- A Codi maintainer who understands tmux window routing and transcript ingestion.
- A power user with many concurrent Codex/Claude sessions.
- A privacy/security reviewer for error/status redaction.

---

## 2. Framework Decision

### Selected Framework

**Direct local retrieval stack: Sentence Transformers + LanceDB + SQLite queue**

### Version

- Embedding model: `Qwen/Qwen3-Embedding-0.6B`
- Embedding runtime: `sentence-transformers>=2.7.0`
- Vector and hybrid index: `lancedb>=0.21.0` (current lockfile resolves LanceDB 0.30.x)
- Queue/status persistence: SQLite and JSON files under `CODEXBOT_DIR`
- Python: project-supported Python 3.12+

Phase 6 should verify that the active environment satisfies the Qwen runtime requirements before accepting Qwen as the default model. In practice, that means recording the loaded model id, embedding dimension, normalization policy, query instruction, batch size, and the resolved `transformers`/`sentence-transformers` versions in the benchmark output.

### Why This Framework

Codi already owns session discovery, transcript parsing, chunking, queueing, status APIs, and ranking behavior. A direct retrieval stack keeps those contracts explicit and avoids a large agent/RAG framework in the hot path. LanceDB provides local embedded storage with vector search and FTS support, while Sentence Transformers provides a local embedding interface that can run on a Mac mini without cloud calls.

### Alternatives Considered

| Alternative | Why Not Selected |
| --- | --- |
| LlamaIndex | Adds ingestion/retrieval abstractions that duplicate Codi's existing session, queue, and ranking contracts. Useful for prototyping, but too much framework surface for this local bridge. |
| LangChain | Broad orchestration framework with unnecessary agent/tool abstractions for this retrieval-only system. It also makes hot-path boundaries less obvious. |
| FAISS | Strong vector search library, but vector-only. It would still require separate lexical search, metadata/status persistence, queue handling, and more operational glue. |
| SQLite FTS only | Useful degraded path, but it cannot support semantic session discovery for paraphrased task queries. |
| Cloud embeddings | Easier operations in some deployments, but conflicts with Codi's local/private deployment model and introduces network cost/latency/failure modes. |

### Vendor Lock-in Assessment

Lock-in is low to moderate. LanceDB and Sentence Transformers are open-source local libraries. The default model id points to Hugging Face, but Codi already exposes model and dimension overrides through `CODEXBOT_SEARCH_MODEL_ID` and `CODEXBOT_SEARCH_VECTOR_DIM`. Lexical degraded search must remain available when the model is missing or replaced.

---

## 3. Framework Quick Reference

### Installation

```bash
uv add "lancedb>=0.21.0" "sentence-transformers>=2.7.0"
uv run python -c "import lancedb, sentence_transformers; print(lancedb.__version__, sentence_transformers.__version__)"
```

For Phase 6 validation, also record the active `transformers` version before accepting Qwen as the default model.

### Core Imports

```python
from sentence_transformers import SentenceTransformer

import lancedb
```

### Entry Point Pattern

```python
from codexbot.search.embedding import EmbeddingConfig
from codexbot.search.paths import generation_lancedb_dir


def build_embedding_model(config: EmbeddingConfig) -> SentenceTransformer:
    return SentenceTransformer(config.model_id, local_files_only=config.local_files_only)


def embed_documents(model: SentenceTransformer, texts: list[str], config: EmbeddingConfig) -> list[list[float]]:
    vectors = model.encode(
        texts,
        batch_size=config.batch_size,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    return vectors.tolist()


def upsert_chunks(generation_id: str, rows: list[dict]) -> None:
    db = lancedb.connect(str(generation_lancedb_dir(generation_id)))
    table = db.open_table("chunks")
    table.merge_insert("row_id").when_matched_update_all().when_not_matched_insert_all().execute(rows)
```

### Key Abstractions

- `EmbeddingConfig`: model id, vector dimension, batch size, and local-files behavior.
- `EmbeddingProvider`: lazily owns the Sentence Transformers model and produces normalized document/query vectors.
- `SearchBackfillDocument`: stable chunk payload passed from transcript indexing to the worker.
- LanceDB `chunks` table: stores `row_id`, text, vector, window/session metadata, sequence offsets, and timestamps.
- SQLite queue: durable indexing work queue with leases, attempts, and sanitized failure details.
- Search status response: worker heartbeat, queue snapshot, current generation, indexed/open sessions, and degraded state.

### Common Pitfalls

- Loading Sentence Transformers in a FastAPI import path or WebSocket handler.
- Treating Qwen's 32K input window as an acceptable chunk size; Codi needs much smaller operational chunks.
- Forgetting that some embedding models distinguish query and document prompts. Current Codi behavior uses an explicit query instruction; Phase 6 should validate whether `encode_query`/`encode_document` improves or changes ranking.
- Changing vector dimension without rebuilding the LanceDB generation.
- Reporting raw exception text to the UI instead of sanitized worker errors.
- Accepting fake-embedder tests as proof that Qwen runs on the target host.

---

## 4. Implementation Guidance

### Architecture Pattern

Keep model work in the search worker/backfill lane. Request handlers should read status, enqueue work, or query an existing index. If semantic search fails, return lexical-only degraded results and a clear status rather than blocking or failing unrelated Codi features.

### Model Configuration

Required default metadata to record:

- `model_id`: `Qwen/Qwen3-Embedding-0.6B`
- `vector_dim`: `1024`
- `batch_size`: current default and benchmark-selected value
- `normalize_embeddings`: `true`
- `query_instruction`: the active instruction string or prompt version
- `document_instruction`: none unless Phase 6 adopts `encode_document`
- `local_files_only`: active value
- runtime package versions: `sentence-transformers`, `transformers`, `torch`, `lancedb`

### Tool Use

- LanceDB stores vectors, text, and chunk metadata per index generation.
- SQLite stores queue items and leasing state so worker crashes do not lose indexing work.
- JSON status files expose coarse worker health to the API without requiring LanceDB reads on every UI poll.
- Pytest uses fake embedders for deterministic failure isolation; Phase 6 adds opt-in local Qwen smoke and benchmark fixtures.

### State Management

Search state lives under `CODEXBOT_DIR`:

- `search/queue.sqlite`: durable indexing queue.
- `search/generations/<generation_id>/`: LanceDB table and metadata for one generation.
- `search/current_generation`: pointer to the active generation.
- Worker status JSON: heartbeat, mode, backfill progress, recent sanitized errors, and benchmark/model metadata.

State updates must be monotonic from the UI perspective: a stale heartbeat or failed worker cannot leave the status looking ready.

### Context Window Management

Chunk transcript history by message/turn boundaries with bounded text size. Preserve metadata for window id, runtime, transcript session id, role, sequence, timestamp, and source offsets. Avoid mixing many unrelated tool outputs into one chunk. Long tool outputs should be truncated or split in a way that keeps exact terms searchable without overwhelming semantic relevance.

---

## 4b. AI Coding Best Practices

### Structured Inputs / Outputs

```python
from typing import Literal

from pydantic import BaseModel, Field


class SearchEvalCase(BaseModel):
    query: str
    expected_window_id: str
    required_terms: list[str] = Field(default_factory=list)
    expected_labels: list[Literal["exact", "semantic", "hybrid"]] = Field(default_factory=list)
    max_query_latency_ms: int = 300


class SearchEvalResult(BaseModel):
    case_id: str
    passed: bool
    rank: int | None
    mode: Literal["hybrid", "lexical_degraded", "unavailable"]
    latency_ms: float
    failure_reason: str | None = None
```

Use typed eval cases so expected exact terms, expected windows, and degraded-mode behavior are reviewable in code instead of encoded in free-form assertions.

### Async-First Design

- Do not run embedding or model downloads in FastAPI request handlers.
- Use bounded worker loops, leases, and cancellation-safe shutdown.
- Use short API status reads and precomputed snapshots instead of expensive index scans.
- Keep UI polling lightweight and avoid per-keystroke model calls.

### Prompt Discipline

The active query instruction is part of the retrieval contract. Version it in metadata and benchmark output. Do not prefix documents with the same instruction unless an eval proves it improves the domain fixtures. Evaluate `encode_query`/`encode_document` against the current explicit instruction before changing default behavior.

### Context Management

Preserve enough transcript coordinates to explain why a result matched. Result rendering should include session/window identity, role, nearby timestamp/order, and a short matched excerpt. Do not expose entire transcript chunks in status endpoints.

### Cost / Latency Awareness

This is a local deployment, so cost is CPU/RAM/UI responsiveness rather than API spend. Benchmark initial model load, docs/sec, batch size, peak memory, index size, query p50/p95, and lexical fallback latency on the target Mac mini class host.

---

## 5. Evaluation Strategy

### Eval Dimensions

| Dimension | Priority | Method | Pass Criteria |
| --- | --- | --- | --- |
| Exact technical recall | Critical | Code eval over sanitized transcript fixtures | Queries containing paths, commands, errors, issue keys, and window ids return the expected session in top 3 and retain exact-match labels. |
| Semantic session relevance | High | Human-reviewed fixture set plus automated top-k checks | Paraphrase/task queries return the expected active session in top 5 without pushing exact matches down when exact terms exist. |
| Freshness/status truthfulness | Critical | Unit/integration tests with simulated stale heartbeat, queue lag, and worker failure | UI/API status moves to degraded/unavailable and never reports ready for stale generations. |
| Failure isolation | Critical | Tests with fake failing/slow embedder and LanceDB errors | Search degrades while session list, WebSocket, terminal, Telegram, and chat routes stay usable. |
| Privacy and redaction | High | Security-focused code tests and review | Status and eval artifacts contain sanitized error classes/counts and no raw secrets or transcript fragments. |
| Mac-mini resource envelope | High | Opt-in local benchmark | Batch size/chunk size/model defaults meet recorded throughput, memory, and query-latency thresholds without observable Codi hot-path impact. |

### Eval Tooling

Primary tooling:

```bash
uv run pytest tests/codexbot/test_search_*.py -q
uv run python -m codexbot.search.worker --help
# Phase 6 should add an opt-in benchmark command over sanitized fixtures.
uv run python -m codexbot.search.benchmark --fixtures tests/fixtures/search --model Qwen/Qwen3-Embedding-0.6B
```

Optional experiment tracing:

- Arize Phoenix can be used locally for retrieval/ranking experiments if useful, but it is not required in the production path.
- Production-quality telemetry should first be structured JSON metrics and the existing Web UI/auth status surfaces.

### Reference Dataset

Build a sanitized fixture set from real Codi transcript shapes:

- 8-10 exact technical queries: file paths, shell commands, tracebacks, issue ids, tmux window ids.
- 8-10 semantic/paraphrase queries: "the LanceDB indexing work", "mobile terminal buttons", "GSD choices in Web UI".
- 4-6 degraded-state cases: missing model, failed embedding, stale heartbeat, lagging queue, failed LanceDB read.
- 3-5 privacy cases: synthetic secrets in transcript/error text that must not appear in status or benchmark summaries.

Each case should include expected window/session id, required matched terms where relevant, expected mode, acceptable rank, and latency budget.

---

## 6. Guardrails & Monitoring

### Online Guardrails

- Search worker failures must set degraded status and must not raise through unrelated Web UI or Telegram routes.
- Semantic errors must fall back to lexical degraded search when lexical data is available.
- Worker heartbeat age and queue lag must be visible and must change readiness status when stale.
- Status endpoints must sanitize exception text before exposing it to the browser.
- Request-path tests should fail if heavy model imports or embedding calls move into API/WebSocket handlers.

### Offline Guardrails

- Benchmark every accepted model/default change against the sanitized fixture set.
- Track exact-recall top-k, semantic top-k, p95 query latency, docs/sec, peak memory, failed queue item count, and stale-source count.
- Require a local Qwen smoke test before claiming Qwen readiness on a new deployment.
- Keep lexical-only degraded behavior passing even when Sentence Transformers or LanceDB vector search is unavailable.

### Production Monitoring

Default monitoring surface:

- `/api/search/status` and Web UI status: heartbeat age, mode, queue lag, oldest queued age, failed items, open sessions, indexed sessions, generation id, backfill progress, recent sanitized errors.
- Structured benchmark output: model metadata, package versions, chunking parameters, throughput, memory, and latency.

Suggested alert thresholds:

- Worker heartbeat age exceeds 120 seconds while search is enabled.
- Oldest queued item age exceeds 300 seconds.
- Any failed queue item remains unresolved after retries.
- Semantic fallback rate rises above the recorded baseline.
- Search query p95 exceeds the benchmark budget for the selected Mac-mini profile.
- Indexed open-session count differs from live open-session count for more than one refresh interval after backfill settles.

Smart sampling:

- Sample failed/degraded queries, zero-result technical queries, high-latency queries, and first queries after model or generation changes.
- Never sample raw secret-bearing chunks into long-lived status or shared artifacts.

---

## 7. Implementation Checklist

- [x] Framework selected and justified
- [x] Domain context documented
- [x] Evaluation dimensions defined
- [x] Guardrails specified
- [x] Monitoring plan included
- [x] Structured input/output examples provided
- [x] Failure modes identified

---

## Sources

- Existing Codi search implementation: `src/codexbot/search/embedding.py`, `index.py`, `retrieval.py`, `ranking.py`, `queue.py`.
- Phase context: `.planning/phases/06-operational-hardening-and-model-tuning/06-CONTEXT.md`.
- UI contract: `.planning/phases/06-operational-hardening-and-model-tuning/06-UI-SPEC.md`.
- Prior stack research: `.planning/research/STACK.md`, `.planning/research/PITFALLS.md`.
- Prior LanceDB/Qwen phase research: `.planning/phases/04-lancedb-hybrid-retrieval-and-ranking/04-RESEARCH.md`.
- Sentence Transformers documentation, queried through Context7.
- LanceDB documentation, queried through Context7.
- Qwen model page: `https://huggingface.co/Qwen/Qwen3-Embedding-0.6B`.
