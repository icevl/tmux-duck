# Stack Research

**Domain:** local hybrid search over active Codex/Claude session transcripts
**Project:** Codi Web UI session search
**Researched:** 2026-05-21
**Confidence:** HIGH for index stack, MEDIUM for final embedding model until Mac mini benchmarks run

## Recommendation

Use **LanceDB OSS** as the persisted local hybrid-search index, backed by a
small **SQLite durable queue/status database**, and keep all embedding/indexing
inside a separate Python worker process. The Codi API should enqueue transcript
chunks and proxy search requests to that worker over a local-only boundary
(loopback HTTP or a Unix socket) so normal FastAPI startup, WebSockets,
Telegram delivery, and transcript monitoring never import Torch or wait on
embedding work.

Default the first implementation to **Qwen/Qwen3-Embedding-0.6B** through
`sentence-transformers`, using normalized embeddings and LanceDB hybrid search
(vector + BM25 FTS + RRF reranking). It is the best default candidate because
it is instruction-aware, Apache-2.0, 0.6B parameters, supports 32K token input,
uses 1024-dimensional embeddings, and supports Matryoshka-style truncation for
smaller stored vectors. Treat it as a benchmarked default, not a hard-coded
forever choice: if the target Mac mini struggles during backfill, switch to a
smaller ONNX-backed model variant described below.

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| LanceDB OSS | 0.30.2 | Local persisted vector, metadata, full-text, and hybrid search index | It directly supports Python local tables, vector search, BM25 full-text search, hybrid queries, and reranking/RRF in one embedded store. This avoids hand-building vector + FTS fusion across two engines. | HIGH |
| SQLite + WAL | SQLite 3.50.4 in current Python runtime; use `aiosqlite` 0.22.1 if async access is needed | Durable ingestion queue, backfill status, chunk high-water marks, and worker lease/heartbeat state | Codi already treats runtime transcript state as rebuildable local files. SQLite is ideal for a small cross-process queue/status DB and keeps startup non-blocking when the LanceDB index is absent. | HIGH |
| Python search worker process | Python 3.12+ | Owns embedding model, LanceDB connection, backfill, live batch flushing, and query embedding | Process isolation is the important stack decision. The main FastAPI process should not import Torch or hold the embedding model. A separate worker protects UI and Telegram responsiveness. | HIGH |
| Sentence Transformers | 5.5.1 | Primary local embedding runtime | Official docs support local model loading, device selection, normalized embeddings, ONNX backend/export paths, and `truncate_dim` for Matryoshka models. It is the most direct supported path for Qwen3 embedding models. | HIGH |
| PyTorch | 2.12.0 | Backend for Qwen3 embedding inference on CPU or Apple Silicon MPS | PyTorch has official MPS support for Apple Silicon. Use it only in the worker and cap worker concurrency/batch size. | MEDIUM |
| Transformers | 5.9.0 current; require `>=4.51,<6` | Model loader compatibility for Qwen3 | Qwen3 embedding model cards require recent Transformers support; Sentence Transformers 5.5.1 allows Transformers `<6`. | HIGH |
| Qwen/Qwen3-Embedding-0.6B | HF model updated 2026-04-20; 0.6B params, 1024 dims, 32K context | Default semantic embedding model to benchmark first | Strong modern general retrieval model, instruction-aware, Apache-2.0, small enough for a Mac mini worker compared with 4B/8B models. | MEDIUM |

### Supporting Libraries

| Library | Version | Purpose | When to Use | Confidence |
|---------|---------|---------|-------------|------------|
| `lancedb` | 0.30.2 | Python API for LanceDB local tables and hybrid search | Required for V1. Keep LanceDB writes centralized in the worker. | HIGH |
| `aiosqlite` | 0.22.1 | Async wrapper around SQLite queue/status DB | Use from FastAPI routes or monitor listeners when enqueueing work without blocking the event loop. Worker can also use sync `sqlite3` if simpler. | HIGH |
| `sentence-transformers` | 5.5.1 | Embedding runtime for Qwen3 and other HF sentence embedding models | Required for the default embedding path. Import lazily inside worker startup. | HIGH |
| `torch` | 2.12.0 | Tensor backend for Qwen3 | Required by `sentence-transformers`. Configure device as `mps` when available, otherwise CPU. | MEDIUM |
| `fastembed` | 0.8.0 | ONNX Runtime embedding fallback | Do not install by default for Qwen. Use if benchmarks show Qwen3 is too slow/heavy and a supported ONNX model such as BGE small is good enough. | MEDIUM |
| `numpy` | Transitive (`lancedb` requires `>=1.24`) | Vector arrays and LanceDB input | No direct design issue, but pin only if resolver conflicts appear. | HIGH |
| `pyarrow` | Transitive (`lancedb` requires `>=16`) | Lance/LanceDB columnar storage dependency | Expect a larger install footprint. This is the main packaging cost of LanceDB. | HIGH |

### Embedding Model Choices

| Model | Role | Why | Caveat | Recommendation |
|-------|------|-----|--------|----------------|
| `Qwen/Qwen3-Embedding-0.6B` | Default V1 candidate | Best fit for "modern, local, technical transcript search": 0.6B, 1024 dims, 32K context, instruction-aware, MRL, Apache-2.0, supported by Sentence Transformers. | Heavier than ONNX small models. It has no ONNX files in the official HF repo today, so the default path is PyTorch unless the project exports/quantizes locally. | Use first on Mac mini 16GB+; benchmark batch sizes 4, 8, 16, 32 and 512 vs 1024 stored dimensions. |
| `Alibaba-NLP/gte-modernbert-base` | Balanced lower-latency fallback | Apache-2.0, sentence-transformers compatible, ONNX-tagged, smaller than Qwen3 0.6B, good for general technical text. | Not specifically a code retrieval model. | Use if Qwen3 backfill/query latency is too high. |
| `jinaai/jina-embeddings-v2-base-code` | Low-memory code-heavy fallback | Apache-2.0, ONNX-tagged, code-oriented, much more downloaded than newer niche code models. | Older and uses custom code/trust surface; benchmark before adopting. | Consider if search relevance for stack traces, commands, and code snippets beats gte-modernbert/Qwen on Codi fixtures. |
| `BAAI/bge-code-v1` | Code-search validation candidate | Strong code retrieval claims and Apache-2.0. | 2B parameters and `trust_remote_code=True`; too heavy for Mac mini V1 default. | Benchmark only if Qwen3 fails on code-heavy queries and the target machine has enough memory. |
| `Qwen/Qwen3-Embedding-4B` / `8B` | Future high-accuracy option | Higher-capacity same family. | Too large for a responsive Mac mini self-hosted app and unnecessary for open-session transcript search. | Do not use in V1. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `uv lock` / `uv sync` | Dependency resolution | Add search packages in a dedicated group/extra or normal dependencies only after install-size impact is accepted. Keep worker imports lazy either way. |
| Small benchmark script | Model/backend validation | Benchmark fixture queries from real Codex/Claude transcripts before freezing model choice. Track backfill docs/sec, query p95, memory, and top-5 relevance. |
| Existing Codi verification commands | Regression safety | Continue using `uv run ruff check src/ tests/`, `uv run pyright src/codexbot/`, `/tmp/codexbot-venv/bin/pytest -q`, and `pnpm --dir web-ui build`. |
| `sqlite3` CLI | Queue/status inspection | Useful for checking stuck backfill leases, pending item counts, and last indexed transcript offsets. |

## Installation

Recommended Python package shape:

```bash
# Core search/index stack
uv add "lancedb>=0.30.2,<0.31" "aiosqlite>=0.22.1,<1"

# Default embedding worker stack
uv add "sentence-transformers>=5.5.1,<6" "transformers>=4.51,<6" "torch>=2.12,<3"

# Optional low-memory ONNX fallback, only if chosen after benchmarking
uv add "fastembed>=0.8,<1"
```

Packaging recommendation:

- If search becomes always-on in Codi, put `lancedb` and `aiosqlite` in normal
  dependencies and keep `sentence-transformers`/`torch` imported only by the
  worker.
- If install size is a concern, create `[project.optional-dependencies].search`
  for the embedding stack and have launchd/Docker search-enabled installs run
  with that extra.
- Do not use `lancedb[embeddings]` as the default dependency. It pulls many
  provider integrations the project does not need. Keep embedding packages
  explicit.

## Recommended Local Data Layout

Use the Codi state directory and keep the index rebuildable:

```text
$CODEXBOT_DIR/
  search/
    queue.sqlite3          # durable ingestion queue, backfill state, status
    lancedb/               # LanceDB database directory
      session_chunks.lance # derived chunks + vectors + metadata
```

Recommended LanceDB row shape:

```text
chunk_id              stable hash(runtime, session_id, window_id, transcript_path, offset/span)
window_id             tmux window id, e.g. @12
runtime               codex | claude
runtime_session_id    Codex/Claude session id when known
cwd                   session cwd for filtering/display
role                  user | assistant | tool | system-ish normalized type
text                  normalized searchable text
snippet_text          shorter display-oriented text
source_path           transcript JSONL path
byte_start/end        transcript offsets where available
message_ts            timestamp from transcript/parser when available
turn_id               normalized turn/message grouping key
vector                embedding, 512 or 1024 dims depending benchmark
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative | Why Not For Codi V1 |
|-------------|-------------|-------------------------|---------------------|
| LanceDB | FAISS (`faiss-cpu` 1.13.2) | Pure vector search at much larger scale where you already have a document store, metadata filters, and separate BM25. | FAISS is a vector similarity library, not a complete hybrid search store. Codi would have to build metadata storage, FTS/BM25, delete/update semantics, persistence, and score fusion itself. |
| LanceDB | SQLite FTS5/BM25 only | Lexical-only search, exact command/error search, or a tiny no-ML fallback mode. | FTS5 has BM25/snippets/highlighting, but no semantic search by itself. Adding `sqlite-vec`/Usearch can work, but hybrid ranking, vector persistence, and update semantics become custom glue. |
| LanceDB | SQLite FTS5 + `sqlite-vec` | If `pyarrow`/LanceDB install footprint is unacceptable and the corpus stays very small. | More manual scoring/fusion code and less mature for this hybrid transcript-search workflow. Keep as fallback research, not default. |
| LanceDB | Direct Tantivy (`tantivy` 0.26.0) | Rust-first lexical search, custom analyzers, or lexical-only index service. | Tantivy is excellent for FTS, but direct Python use does not solve vector search or hybrid fusion. LanceDB already exposes FTS/hybrid without a second index engine. |
| LanceDB | Meilisearch (`meilisearch` Python 0.41.0 plus server) | Larger hosted/multi-user search product needing typo tolerance, facets, operational search APIs, and a dedicated daemon. | Codi is self-hosted/local and already has a backend. Meilisearch adds a server, auth/admin-token handling, process supervision, and embedding integration overhead for a small active-session index. |
| Qwen3-Embedding-0.6B | FastEmbed default BGE small | Low-memory Mac mini, fast backfill, and acceptable semantic quality. | Faster/lighter but less likely to understand mixed natural language, code, logs, and long technical context as well as Qwen3. |
| Qwen3-Embedding-0.6B | Cloud embeddings | Hosted multi-device sync or cloud product with budget for API calls. | Violates local-first scope, adds privacy/network failure modes, and blocks offline search. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| Cloud embedding APIs for V1 | Session transcripts can include secrets, local paths, code, prompts, and tool output. The project explicitly needs local/self-hosted search. | Local Sentence Transformers worker. |
| Running embedding in FastAPI route handlers or monitor callbacks | It can block startup, WebSocket delivery, Telegram sends, and transcript polling. | Durable queue plus separate worker process. |
| Direct synchronous per-message indexing | It couples transcript delivery to model latency and makes bursty sessions feel slow. | Batch 32 queued chunks or flush every 60 seconds, whichever comes first. |
| Qwen3 4B/8B or default reranker in V1 | Large memory/latency cost for a bounded open-session corpus. Reranking can be added later after base hybrid search is useful. | Qwen3-Embedding-0.6B with LanceDB RRF; optional small reranker only after benchmarks. |
| LangChain/LlamaIndex for the core path | Adds framework abstractions around a narrow, local, product-specific feature. Codi already has transcript parsing, state, API, and WebSocket layers. | Direct queue, embedder, LanceDB, and FastAPI integration. |
| `lancedb[embeddings]` as a blanket install | Pulls extra embedding/provider dependencies and obscures what Codi actually runs. | Explicit `lancedb`, `sentence-transformers`, `torch`, and optional `fastembed`. |
| Direct `tantivy` as the primary index | Gives lexical search only and creates another fusion layer. | LanceDB hybrid search. |
| FAISS as the primary index | Vector-only, no native BM25 snippets/status metadata store for this feature. | LanceDB, or SQLite FTS5 as lexical fallback. |
| Meilisearch daemon for V1 | Extra local service, index lifecycle, credentials, and deployment work for a small self-hosted app. | Embedded LanceDB worker. |

## Stack Patterns by Variant

**Default Mac mini, 16GB+ unified memory:**
- Use LanceDB 0.30.2 + Sentence Transformers 5.5.1 + Qwen3-Embedding-0.6B.
- Store 1024-dimensional normalized vectors first, then benchmark 512-dimensional `truncate_dim` if disk/memory grows faster than expected.
- Worker owns a single model instance, one LanceDB writer, and bounded batches.
- Set conservative batch defaults: start with 8 or 16 chunks per embedding batch, allow 32 only if memory is stable.

**Lower-memory Mac mini or slow backfill:**
- Keep LanceDB and SQLite queue unchanged.
- Swap embedder to `gte-modernbert-base` or FastEmbed-supported BGE small after benchmark validation.
- Prefer 384/512-dimensional vectors and smaller chunk sizes.
- Surface degraded mode in the UI as "lexical ready, semantic indexing warming" instead of blocking search.

**Code-heavy quality problem after default benchmark:**
- Test `jinaai/jina-embeddings-v2-base-code` and `BAAI/bge-code-v1` on Codi fixtures.
- Choose Jina if it materially improves code/log/session retrieval without `trust_remote_code` risk becoming unacceptable.
- Treat BGE-Code-v1 as high-quality but heavy; it is a validation candidate, not the default.

**LanceDB install or platform issue:**
- Fallback to SQLite FTS5 for lexical search immediately.
- Add vector search with `sqlite-vec` or Usearch only after measuring the maintenance cost.
- Roadmap this as a fallback implementation, not a parallel default stack.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| Codi Python | 3.12+ | Existing project requires Python >=3.12 and validates 3.12/3.13. Search dependencies must keep that promise. |
| `lancedb` 0.30.2 | `pyarrow>=16`, `pydantic>=1.10`, `numpy>=1.24` | Compatible with FastAPI/Pydantic 2 through the broad Pydantic requirement. Expect larger wheels because of PyArrow. |
| `sentence-transformers` 5.5.1 | `transformers>=4.41,<6`, `torch>=1.11` | Qwen3 needs newer Transformers support, so constrain `transformers>=4.51,<6`. |
| Qwen3-Embedding-0.6B | Sentence Transformers / Transformers | Official model has Sentence Transformers metadata and no ONNX files in the current repo listing. Use PyTorch path first. |
| `fastembed` 0.8.0 | `onnxruntime>=1.17` on Python 3.11/3.12; newer ONNX Runtime for newer Python | Good fallback, but avoid installing alongside Torch unless the fallback is actually selected. |
| `faiss-cpu` 1.13.2 | `numpy>=1.25,<3` | Fine as a vector-only experiment, not the default hybrid store. |

## Operational Defaults

- Main Codi process: enqueue search work only; never load embedding models.
- Worker startup: open/create SQLite queue DB, open/create LanceDB table, report status, then backfill if needed.
- Worker write policy: single writer process for LanceDB; main process does not write to LanceDB directly.
- Live batching: flush when 32 queued chunks accumulate or after 60 seconds.
- Missing index on Codi startup: return empty/lexical-unavailable status to UI, start worker/backfill, keep app usable.
- Rebuild: delete derived LanceDB directory and queue index state, then replay open-session transcripts from parser output.
- Search ranking: use LanceDB hybrid retrieval with RRF first; tune vector-vs-FTS weights only if evaluation shows bad ordering.
- Snippets: store original chunk text and display snippets derived from chunk windows; do not rely only on vector hits.

## Confidence Assessment

| Area | Confidence | Reason |
|------|------------|--------|
| LanceDB as primary hybrid index | HIGH | Official docs verify Python FTS, BM25, hybrid search, vector search, and RRF/reranking support. It matches the local persisted index requirement. |
| SQLite queue/status DB | HIGH | Standard local durable queue pattern; avoids cross-process in-memory queues and keeps index state inspectable/rebuildable. |
| Separate worker process | HIGH | Directly follows Codi architecture constraints and prevents embedding latency from touching existing async delivery paths. |
| Qwen3-Embedding-0.6B default | MEDIUM | Official model specs are strong, but actual Mac mini throughput and memory must be measured on Codi transcript chunks. |
| FastEmbed/gte fallback | MEDIUM | Official docs verify ONNX/CPU embedding paths, but final model quality depends on Codi-specific query fixtures. |
| Not using FAISS/Meilisearch/Tantivy as default | HIGH | Primary-source docs confirm their fit as vector-only, search-server, or lexical-focused options; they add glue or operations Codi does not need for V1. |

## Sources

- Context7 `/websites/lancedb` - verified Python FTS index creation, vector index creation, hybrid search, and reranking/RRF examples.
- LanceDB docs: https://docs.lancedb.com/search/hybrid-search - hybrid search combines vector and full-text search.
- LanceDB docs: https://docs.lancedb.com/search/full-text-search - full-text search uses BM25 keyword retrieval.
- LanceDB docs: https://docs.lancedb.com/reranking - reranking support and Python SDK coverage.
- PyPI `lancedb`: https://pypi.org/project/lancedb/ - current package version 0.30.2 and dependency shape.
- Context7 `/huggingface/sentence-transformers` - verified local embedding inference, ONNX backend/export, normalized embeddings, and `truncate_dim`.
- PyPI `sentence-transformers`: https://pypi.org/project/sentence-transformers/ - current version 5.5.1 and dependency constraints.
- PyPI `torch`: https://pypi.org/project/torch/ - current version 2.12.0.
- PyPI `transformers`: https://pypi.org/project/transformers/ - current version 5.9.0.
- PyTorch MPS docs: https://docs.pytorch.org/docs/stable/notes/mps.html - Apple Silicon MPS backend support.
- Qwen3 Embedding repo: https://github.com/QwenLM/Qwen3-Embedding - model sizes, dimensions, 32K context, MRL, instruction-aware behavior.
- Qwen3-Embedding-0.6B model card: https://huggingface.co/Qwen/Qwen3-Embedding-0.6B - model metadata, license, Sentence Transformers support.
- Context7 `/qdrant/fastembed` - verified ONNX Runtime CPU embedding path and supported-model APIs.
- PyPI `fastembed`: https://pypi.org/project/fastembed/ - current version 0.8.0 and ONNX Runtime dependency shape.
- SQLite FTS5 docs: https://www.sqlite.org/fts5.html - BM25, snippet/highlight, and FTS5 capabilities.
- FAISS docs: https://faiss.ai/ - FAISS is a dense-vector similarity search library with Python wrappers.
- Meilisearch docs: https://www.meilisearch.com/docs/learn/ai_powered_search/difference_full_text_ai_search - Meilisearch hybrid/semantic search behavior and embedder model.
- Hugging Face `BAAI/bge-code-v1`: https://huggingface.co/BAAI/bge-code-v1 - code retrieval claims, 2B size, trust-remote-code usage examples.
- Hugging Face `jinaai/jina-embeddings-v2-base-code`: https://huggingface.co/jinaai/jina-embeddings-v2-base-code - code-oriented embedding alternative.
- Hugging Face `Alibaba-NLP/gte-modernbert-base`: https://huggingface.co/Alibaba-NLP/gte-modernbert-base - smaller ONNX-tagged general embedding alternative.

---
*Stack research for: Codi local hybrid session search*
*Researched: 2026-05-21*
