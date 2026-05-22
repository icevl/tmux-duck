# Phase 4: LanceDB Hybrid Retrieval and Ranking - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-05-22
**Phase:** 4-LanceDB Hybrid Retrieval and Ranking
**Areas discussed:** Hybrid Ranking, Result Payload, Model Ops

---

## Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| Hybrid Ranking | Lock lexical, semantic, metadata weighting and exact-term priority before planning retrieval. | yes |
| Result Payload | Lock session grouping, snippets, labels, filters, timestamps, and Web UI-facing fields. | yes |
| Model Ops | Lock LanceDB schema, Qwen3 validation, local fallback, and degraded search behavior. | yes |

---

## Hybrid Ranking

### Exact Versus Semantic Priority

| Option | Description | Selected |
|--------|-------------|----------|
| Exact First | Exact technical matches get protected priority; semantic can fill gaps and reorder close ties. | yes |
| Blended Score | Lexical, semantic, and metadata scores are normalized into one weighted score for all hits. | |
| Semantic Rerank | Semantic relevance can outrank exact matches when the embedding score is much stronger. | |

**User's choice:** Exact First
**Notes:** Exact technical terms should not be buried by semantic paraphrase matches.

### Metadata Role

| Option | Description | Selected |
|--------|-------------|----------|
| Filter + Boost | Explicit filters constrain results; free-text metadata matches add a bounded boost. | yes |
| Filters Only | Runtime/cwd/status/role fields only narrow results and never affect score. | |
| First-Class Matches | Metadata text competes with transcript hits and can rank sessions even without content matches. | |

**User's choice:** Filter + Boost
**Notes:** Metadata should help ranking, but should not dominate transcript evidence.

### Session Aggregation

| Option | Description | Selected |
|--------|-------------|----------|
| Best + Diversity | Rank primarily by best hit, then add capped boosts for distinct supporting hits. | yes |
| Sum Top Hits | Aggregate the top N hit scores, favoring sessions with repeated or many matches. | |
| Best Hit Only | Session rank is determined only by the single strongest matching chunk. | |

**User's choice:** Best + Diversity
**Notes:** This avoids over-rewarding repeated noisy text.

### Lexical Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| BM25 + Exact Boosts | Use BM25 for recall plus boosts for quoted phrases, paths, symbols, commands, and stack text. | yes |
| Plain BM25 | Use only lexical full-text scoring and avoid special boosts for technical patterns. | |
| Substring Only | Prioritize literal substring matching and leave broader lexical recall out of scope. | |

**User's choice:** BM25 + Exact Boosts
**Notes:** Exact technical matching should anchor retrieval while BM25 provides lexical recall.

---

## Result Payload

### Grouping Identity

| Option | Description | Selected |
|--------|-------------|----------|
| Open Window | Group by current tmux window ID so every result can route safely to an active Web UI session. | yes |
| Runtime Session | Group by Codex/Claude session ID, even when routing through a current window is indirect. | |
| Transcript Source | Group by transcript file/source and let later layers map it back to sessions. | |

**User's choice:** Open Window
**Notes:** Matches the Codi routing contract and Phase 5 session-switching needs.

### Snippet Shape

| Option | Description | Selected |
|--------|-------------|----------|
| Explainable Hit | Return snippet, role/tool label, timestamp or transcript position, source order, and highlight spans when exact matches exist. | yes |
| Compact Snippet | Return only short text plus role label and leave highlights/details for later. | |
| Raw Row Details | Expose full provenance and chunk metadata directly to the UI. | |

**User's choice:** Explainable Hit
**Notes:** Phase 5 should not need to reinterpret raw search rows to explain matches.

### Filter Contract

| Option | Description | Selected |
|--------|-------------|----------|
| Full Contract | Support runtime, cwd/project, role, content type, status, recent activity, window ID, session ID, and pinned state. | yes |
| Core Filters | Support runtime, cwd/project, role, and content type now; defer status/recent/pinned filters. | |
| Search Only | Implement ranking first and leave all filtering for the Web UI phase. | |

**User's choice:** Full Contract
**Notes:** Backend should own filtering semantics before the UI consumes them.

### Score Exposure

| Option | Description | Selected |
|--------|-------------|----------|
| Scores + Labels | Return normalized scores plus match labels like lexical, semantic, metadata, and hybrid for sessions and hits. | yes |
| Labels Only | Return human-readable match labels and hide numeric scores from the API. | |
| Raw Scores | Expose raw backend scores from BM25/vector/metadata channels for debugging and UI display. | |

**User's choice:** Scores + Labels
**Notes:** Normalized scores support ordering/debugging while keeping raw backend scoring internal.

---

## Model Ops

### Index Shape

| Option | Description | Selected |
|--------|-------------|----------|
| Chunk Table | Use one LanceDB chunk table with stable identity, text, vector, metadata columns, and FTS/vector indexes. | yes |
| Split Tables | Keep lexical and vector indexes in separate stores and merge results in Python. | |
| JSONL Primary | Keep generation JSONL as primary query storage and add LanceDB only as an optional vector sidecar. | |

**User's choice:** Chunk Table
**Notes:** Keeps lexical, vector, metadata, and routeable identity together for the MVP.

### Semantic Fallback

| Option | Description | Selected |
|--------|-------------|----------|
| Lexical Degraded | Return lexical and metadata results with a degraded status and clear reason. | yes |
| Unavailable | Treat search as unavailable until semantic retrieval is healthy. | |
| Smaller Fallback Model | Automatically switch to a smaller local embedding model when Qwen3 is unhealthy. | |

**User's choice:** Lexical Degraded
**Notes:** Local search should remain useful when semantic retrieval is unhealthy.

### Live Index Updates

| Option | Description | Selected |
|--------|-------------|----------|
| Same Worker Flush | The existing 32-item or 60-second live worker flush also embeds/upserts LanceDB rows. | yes |
| Periodic Rebuild | Live JSONL convergence continues, and LanceDB is refreshed only by periodic rebuilds. | |
| Query Overlay | Query the active LanceDB generation plus a separate live overlay until the next rebuild. | |

**User's choice:** Same Worker Flush
**Notes:** Carries forward the Phase 3 live queue batching contract.

### Readiness Gate

| Option | Description | Selected |
|--------|-------------|----------|
| Validated Ready | Block readiness on fixtures proving ranking plus local model/index smoke performance within safe limits. | yes |
| Functional Ready | Accept correct query behavior if tests pass, and tune performance in Phase 6. | |
| Config Ready | Ship provider/config hooks now and defer local embedding validation entirely. | |

**User's choice:** Validated Ready
**Notes:** Phase 4 should prove the local model/index path is viable before claiming readiness.

---

## the agent's Discretion

- Exact LanceDB APIs, table/index file names, column names, normalized score
  formulas, BM25/exact boost constants, embedding batch sizes, timeout values,
  and fixture organization are left to implementation planning.

## Deferred Ideas

- None.
