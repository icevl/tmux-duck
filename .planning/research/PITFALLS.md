# Pitfalls Research

**Domain:** Codi Web UI local hybrid session search
**Researched:** 2026-05-21
**Confidence:** HIGH

This file focuses on mistakes to avoid when adding transcript-backed local hybrid
search to Codi. Phase names are recommendations for roadmap planning:

1. **Phase 1 - Search Contract and Status Surface:** schema, identifiers,
   ingest rules, API contracts, and visible index status.
2. **Phase 2 - Backfill Worker and Rebuild Path:** isolated worker/service,
   async initial index, rebuildability, and search-owned state.
3. **Phase 3 - Live Queue and Convergence:** live indexing queue, batching,
   ordering, idempotency, restart recovery, and session rebinding.
4. **Phase 4 - Hybrid Retrieval and Ranking:** LanceDB FTS/vector indexes,
   filters, ranking, snippets, and query behavior.
5. **Phase 5 - Web UI Search Experience:** search UI, partial-index messaging,
   result navigation, empty states, and user-facing diagnostics.
6. **Phase 6 - Operational Hardening:** resource limits, optimize/maintenance,
   metrics, recovery, and optional model/backend tuning.

## Critical Pitfalls

### Pitfall 1: Index Rows Lack Stable Transcript Identity

**What goes wrong:**
Search returns duplicate hits, stale snippets, or opens the wrong session after a
tmux window is renamed, a runtime session is rebound, or the same message text
appears multiple times. A user clicks a result and lands in the wrong window, or
the worker cannot safely retry because it cannot tell whether a row already
exists.

**Why it happens:**
Codi's primary runtime identity is tmux `window_id`, while transcripts are keyed
by runtime `session_id` and file offsets. It is tempting to key search rows by
display name, cwd, message text, or timestamp because those are visible in the
UI. Those fields are not stable enough for upserts or navigation.

**How to avoid:**
Define the search row key in Phase 1 before building UI or worker code. Use an
idempotent key derived from:

- `runtime`
- `session_id`
- normalized transcript file path or transcript source id
- `transcript_offset`
- `transcript_index`
- `content_type`
- optional `tool_use_id` when present

Keep `window_id` as mutable routing metadata resolved through
`SessionManager.window_states`, not as the durable document identity. Store
`window_id` on rows only as a current-open-session convenience and refresh it
when session state changes.

**Warning signs:**
Rows use cwd, window name, session display name, or message hash as the only
primary key. Tests pass with unique messages but fail when the same command or
error appears twice. A search result stores `@12` without also storing the
runtime session id and transcript position.

**Phase to address:**
Phase 1 - Search Contract and Status Surface.

**Test/verification idea:**
Create a transcript fixture with repeated identical text, duplicate cwd values,
and a tmux rename. Run ingestion twice and assert exactly one row per transcript
position, then assert result navigation resolves the current live `window_id`.

**Confidence:** HIGH. Codi already records `transcript_offset` and
`transcript_index` in parser, monitor, web events, and chat reconciliation.

---

### Pitfall 2: Backfill and Live Indexing Race Each Other

**What goes wrong:**
Messages appended while initial backfill is running are missing, indexed twice,
or appear out of order. Search looks correct after a quiet startup but diverges
under normal use when users keep working during the first index build.

**Why it happens:**
Backfill and live monitoring read the same growing JSONL files through different
timelines. If backfill scans a file while the monitor also enqueues live
`NewMessage` events, neither path alone knows which transcript offsets the other
has covered.

**How to avoid:**
Make convergence an explicit Phase 2/Phase 3 contract:

- At backfill start, record a per-transcript high-water mark such as file size
  and mtime.
- Backfill indexes rows up to that watermark.
- Live listener queues every new parser event even while backfill runs.
- Worker upserts by stable transcript identity, so duplicate work is harmless.
- After backfill, drain queued rows and mark the session covered through the
  highest indexed transcript offset.

Do not block normal Codi usage while this runs. The queue must be able to hold
or persist live work until the worker catches up.

**Warning signs:**
Implementation has a boolean `backfill_done` but no per-session watermark.
Backfill skips live queueing "until initial index completes". Empty results
during backfill are not distinguishable from real misses.

**Phase to address:**
Phase 2 - Backfill Worker and Rebuild Path, then Phase 3 - Live Queue and
Convergence.

**Test/verification idea:**
Use `tmp_path` JSONL transcripts. Start a fake slow backfill, append user,
assistant, and tool-output records while it is paused, then let both paths drain.
Assert every expected transcript position is searchable exactly once and sorted
by transcript order.

**Confidence:** HIGH. The project requirement explicitly says users continue
working during initial indexing and new messages must be queued while backfill
runs.

---

### Pitfall 3: Search Reuses or Mutates `monitor_state.json`

**What goes wrong:**
Adding search causes existing Telegram/WebSocket delivery to replay old messages,
miss new messages, or fast-forward over content. Search may also skip historical
messages because it inherits monitor bootstrap behavior designed for live
notification safety, not full indexing.

**Why it happens:**
`SessionMonitor` persists byte offsets in `monitor_state.json` to avoid
re-sending old messages. Search needs a different offset model: it must backfill
old content, then track its own ingest progress. Sharing state between these two
concerns couples derived search data to user-visible delivery semantics.

**How to avoid:**
Create separate search-owned state under `CODEXBOT_DIR`, for example a search
database and a small metadata table/file for:

- schema version
- embedding model id and dimensions
- per-transcript backfill state
- per-transcript last indexed offset
- queue item status
- last optimize/maintenance time

Use `TranscriptParser` or `SessionManager.get_history_snapshot()` for parsing
semantics, but never write search progress into `MonitorState`.

**Warning signs:**
Search code imports `MonitorState` directly, writes `last_byte_offset`, or calls
`SessionMonitor.set_initial_offset()` to control search ingest. Tests assert
search behavior by inspecting `monitor_state.json`.

**Phase to address:**
Phase 1 - Search Contract and Status Surface, Phase 2 - Backfill Worker and
Rebuild Path.

**Test/verification idea:**
Run backfill against a transcript and snapshot `monitor_state.json` before and
after. Assert it is unchanged. Then append a new line and run
`SessionMonitor.check_for_updates()` to prove normal monitor delivery still sees
the new content.

**Confidence:** HIGH. Codi's existing monitor deliberately fast-forwards during
bootstrap, while search explicitly needs historical open-session backfill.

---

### Pitfall 4: Embedding Work Runs Inside the Main Async Backend

**What goes wrong:**
The Web UI freezes, WebSocket events lag, Telegram delivery stalls, or tmux
commands feel delayed when the embedding model loads or encodes a batch. A local
Mac mini deployment becomes unreliable even though the search result quality is
acceptable.

**Why it happens:**
Embedding a 0.6B model is heavy compared with Codi's existing async control
plane. The main backend already owns FastAPI, WebSocket fanout, tmux operations,
Telegram queues, transcript polling, and terminal bridging. Putting model load
or batch encoding in route handlers, the monitor listener, or the event bus
turns search into a hot-path latency source.

**How to avoid:**
Keep Phase 2 faithful to the project decision: embedding and indexing run in a
separate local service or worker process. The main backend should only enqueue
lightweight work items and expose status. Worker communication should have:

- bounded input queue
- timeout and health status
- batch size controls
- graceful degraded mode when the worker is down
- no imports that load the embedding model in `src/codexbot/web/api.py`,
  `src/codexbot/session_monitor.py`, or app startup

Lexical search can remain available if semantic embedding is temporarily
unavailable.

**Warning signs:**
`SentenceTransformer(...)` or model loading appears in FastAPI route modules,
event listeners, monitor callbacks, or import-time config. A unit test needs to
mock the embedding model just to import Codi modules. WebSocket heartbeat or
`/api/sessions` latency rises during indexing.

**Phase to address:**
Phase 2 - Backfill Worker and Rebuild Path.

**Test/verification idea:**
Use a fake embedder that sleeps or burns CPU during `encode`. While a backfill
batch is active, assert `/api/sessions` and WebSocket message publishing remain
responsive. Add an import smoke test proving backend modules do not load the
model at import time.

**Confidence:** HIGH. Repo concerns already identify large async orchestration
modules and queue/event sensitivity; Qwen3-Embedding-0.6B is documented as a
595.8M parameter/BF16 model.

---

### Pitfall 5: Live Queue Is In-Memory, Unbounded, or Not Idempotent

**What goes wrong:**
Restarting Codi or the worker loses messages that arrived after backfill. A slow
embedding worker lets memory grow without bound. Retried queue items create
duplicate rows. Session rebinding can index old-session messages under a new
window.

**Why it happens:**
Codi already uses in-memory async queues for Telegram and WebSocket fanout, but
search has stronger durability needs because it is a derived store expected to
converge after restarts. Reusing an in-memory `asyncio.Queue` pattern without a
durable ledger creates hidden holes.

**How to avoid:**
Phase 3 should introduce a search-specific queue ledger in the search database
or a dedicated state file. Queue rows should include stable transcript identity,
payload metadata, `enqueued_at`, attempt count, status
(`pending`/`processing`/`done`/`dead_letter`), and worker error text. Enforce the
requested batching policy: flush when 32 queued items accumulate or 60 seconds
passes, whichever comes first. Apply backpressure visibly through status rather
than silently dropping content.

**Warning signs:**
Queue state disappears on restart. There is no attempt count or dead-letter
path. Retry tests require deleting rows manually. Queue depth has no status API
or log metric. Events are keyed only by `window_id`.

**Phase to address:**
Phase 3 - Live Queue and Convergence.

**Test/verification idea:**
Enqueue rows, crash or recreate the worker after marking one item `processing`,
then restart and assert pending/processing work is retried idempotently. Enqueue
the same transcript position twice and assert one indexed row.

**Confidence:** HIGH. The project explicitly requires live batching and
alignment after initial backfill; repo concerns already call out global queue
state and stale task risks.

---

### Pitfall 6: Assuming LanceDB Search Indexes Are Always Fully Current

**What goes wrong:**
Recent messages are slow to search, missing under "fast" query modes, or create
confusing differences between lexical and vector results. The index works in a
demo but degrades after many append batches.

**Why it happens:**
LanceDB supports hybrid search, but FTS and vector indexes have maintenance
semantics. Official docs state that rows added after FTS index creation are not
part of the FTS index until `optimize()`; queries can fall back to scanning
unindexed fragments for completeness, which gets slower as the unindexed tail
grows. Vector indexing also has async behavior where newly added vectors may be
searchable through fallback brute force, while `fast_search` skips unindexed
vectors.

**How to avoid:**
Phase 4 must decide query freshness vs. speed explicitly:

- Do not enable `fast_search` on user-facing "search everything current" paths
  unless the UI labels results as indexed-only/stale.
- Track unindexed row counts or equivalent maintenance signals where the
  selected LanceDB version exposes them.
- Schedule `table.optimize()` on a cadence tied to row changes or modification
  batches.
- Include FTS creation and optimization in rebuild/maintenance operations.
- Surface "live queue lag" and "index maintenance pending" in status.

**Warning signs:**
Search code calls `fast_search` by default. There is no maintenance cadence.
Recent rows only show up in vector results, or only after restart/rebuild. Query
latency grows with every live batch.

**Phase to address:**
Phase 4 - Hybrid Retrieval and Ranking, Phase 6 - Operational Hardening.

**Test/verification idea:**
Create a table, build FTS, add rows after index creation, and verify default
search freshness and latency behavior. Add a test or smoke script that runs the
chosen optimize path and asserts maintenance status returns to clean.

**Confidence:** HIGH for the behavior, based on current LanceDB docs. MEDIUM
for the exact maintenance metric names until the implementation pins and tests a
specific LanceDB version.

---

### Pitfall 7: Hybrid Ranking Misses Exact Technical Queries

**What goes wrong:**
A user searches for an exact file path, error string, command, session id, or
tool name and gets semantically related but useless results. Conversely, broad
natural-language queries return exact lexical matches with poor meaning because
scores are blended naively.

**Why it happens:**
Session search is not generic document search. Codi transcripts contain command
output, stack traces, paths, issue ids, code identifiers, tool names, and short
status fragments. A vector-only query can miss exact terms; a pure BM25 query
can miss paraphrases. Hybrid search also needs metadata filters to avoid mixing
results from closed sessions or wrong runtimes.

**How to avoid:**
Phase 4 should store and query both text and metadata:

- `runtime`, `session_id`, current `window_id`, cwd, timestamp, transcript
  position, role, content type, tool name, and source file path
- scalar filters for currently open sessions and selected runtime/session scope
- hybrid search with both vector and FTS columns
- reranking that preserves exact technical matches for paths, command strings,
  stack traces, and quoted terms
- result snippets derived from original transcript text, not generated summaries

Use LanceDB's explicit vector/text hybrid query pattern if embedding is handled
by a separate worker service.

**Warning signs:**
Search API only accepts a vector query. Results have no `_rowid`/row key or
metadata needed for dedupe/navigation. Tests only cover "meaning" queries, not
exact command/error queries. Filters are applied in React instead of backend
query construction.

**Phase to address:**
Phase 4 - Hybrid Retrieval and Ranking.

**Test/verification idea:**
Build a golden corpus with repeated commands, file paths, stack traces, and
natural-language task descriptions across multiple sessions. Assert exact query
hits appear in the top results, semantic queries still find paraphrases, and
filters prevent closed/wrong-session hits.

**Confidence:** HIGH. LanceDB docs explicitly frame hybrid search as combining
vector and full-text search with reranking, and Codi's corpus is technical.

---

### Pitfall 8: Indexing the Wrong Text

**What goes wrong:**
Search misses useful tool output, indexes duplicated UI-rendered text, stores
Telegram-truncated messages, bloats the database with completion markers, or
creates snippets that do not match the chat view. Users lose trust because the
result preview is not what they see after opening the session.

**Why it happens:**
There are several tempting but wrong text sources: Telegram-rendered messages,
WebSocket payloads after UI reconciliation, terminal pane snapshots, or ad hoc
JSONL parsing. Codi already has a shared `TranscriptParser` because Codex and
Claude transcript shapes are complex and tool-use/tool-result pairing can span
poll cycles.

**How to avoid:**
Phase 1 should define an ingestion policy based on normalized transcript
entries:

- use `TranscriptParser` output or an explicitly shared parser extension
- include user messages, assistant messages, local command output, useful tool
  results, and request/input prompts
- exclude completion markers, status-only entries, empty content, duplicate UI
  echoes, and pure transient terminal chrome
- do not apply Telegram send-layer truncation to search ingestion
- chunk very long tool outputs with bounded overlap and preserve a snippet
  source range

Keep the document text and display snippet tied to transcript provenance.

**Warning signs:**
Search ingestion has its own JSONL parser in a web route or worker. The worker
parses terminal pane text. Rows do not store content type or transcript
position. Indexed text differs from `GET /api/sessions/{window_id}/messages`.

**Phase to address:**
Phase 1 - Search Contract and Status Surface, Phase 4 - Hybrid Retrieval and
Ranking.

**Test/verification idea:**
Use existing transcript parser fixtures plus new search fixtures for tool use,
tool result, local command output, user text, empty output, and completion
records. Assert exactly the expected rows are produced with stable provenance.

**Confidence:** HIGH. The architecture explicitly warns against independent
transcript parsing and confines message truncation to Telegram delivery.

---

### Pitfall 9: UI Treats Partial Backfill as Complete Search

**What goes wrong:**
During first startup, "no results" means "not indexed yet" but the UI presents
it as a real miss. Users repeatedly search, switch sessions, or assume search is
broken. A result may also be stale because the underlying window was killed or
rebound.

**Why it happens:**
Backfill and live indexing are asynchronous by design. Without a status contract
and UI affordances, the frontend can only display normal empty/error states.

**How to avoid:**
Phase 1 should expose status before Phase 5 builds the final UI. At minimum,
return:

- search database missing/initializing/ready
- backfill running/completed/failed
- per-session coverage where feasible
- queued item count and oldest queued age
- last indexed timestamp/offset
- worker health and degraded lexical-only mode

Phase 5 should show compact, non-blocking search state: "Indexing active
sessions", partial badges on results, and an empty state that distinguishes
"still indexing" from "no matches".

**Warning signs:**
The only search API result states are success/error/empty. The UI has a spinner
but no queue depth or coverage. Backfill status is logged but not exposed to the
browser. Search result click does not revalidate that the window is still live.

**Phase to address:**
Phase 1 - Search Contract and Status Surface, Phase 5 - Web UI Search
Experience.

**Test/verification idea:**
Add API tests for status states and frontend build fixtures for missing DB,
backfill running, worker failed, lexical-only degraded mode, and normal complete
search. Result navigation should re-resolve live window state before selecting.

**Confidence:** HIGH. Project requirements explicitly call for index/backfill
status so the Web UI does not confuse users.

---

### Pitfall 10: Embedding Model Is Misused or Over-Provisioned

**What goes wrong:**
Semantic search quality is poor despite using a strong model, or the machine
runs out of memory. Queries and documents embed into incompatible dimensions.
The worker fails at runtime because dependency versions are too old for Qwen3.

**Why it happens:**
Qwen3-Embedding-0.6B is small relative to larger embedding models but still a
real local model: approximately 596M parameters, BF16 weights, up to 1024 output
dimensions, and instruction-aware query behavior. The model card documents
`transformers>=4.51.0` and `sentence-transformers>=2.7.0`; older Transformers
can raise `KeyError: 'qwen3'`. It also recommends query prompts/instructions and
documents do not need the same query instruction.

**How to avoid:**
Phase 2 should isolate model startup and fail gracefully. Phase 4 should persist
embedding metadata in the index:

- model id
- embedding dimension
- tokenizer/max tokens used for chunks
- query prompt/instruction version
- document embedding mode
- normalization policy

Keep chunk lengths much lower than the advertised 32k context unless measured
locally. Batch conservatively and expose CPU/memory impact through worker
status. Treat TEI, quantized variants, or a smaller fallback as implementation
validation topics, not assumptions.

**Warning signs:**
Model dependency versions are not pinned. Search schema does not store vector
dimension or model id. The same raw `encode()` call is used for both query and
document embeddings without considering prompts. Chunks are whole transcripts or
huge tool outputs.

**Phase to address:**
Phase 2 - Backfill Worker and Rebuild Path, Phase 4 - Hybrid Retrieval and
Ranking, Phase 6 - Operational Hardening.

**Test/verification idea:**
Unit-test embedder contracts with a fake model: dimension mismatch must fail
fast and trigger rebuild guidance. Add an optional local smoke test that loads
the selected model, embeds a query with the query prompt and documents without
that prompt, and records batch latency/memory expectations.

**Confidence:** HIGH for model card requirements and features. MEDIUM for final
runtime resource budget until tested on the target Mac mini.

---

### Pitfall 11: Rebuilding by Scanning All Historical Transcripts on Startup

**What goes wrong:**
Startup is slow, the Mac mini does unnecessary disk work, or search indexes
closed/archived sessions even though V1 scope is open sessions. The feature
amplifies an existing performance concern: full Codex session-tree scans.

**Why it happens:**
Codi already has code that scans `~/.codex/sessions` to refresh resume/session
metadata. It is tempting to reuse this for search, but this project's V1 scope
is all currently open tmux sessions, not every historical transcript.

**How to avoid:**
Phase 2 should derive the backfill set from active `WindowState` records and
runtime-specific transcript paths. Full historical search should be a future
milestone with its own pagination, indexing budget, and UX. The rebuild command
should say exactly whether it rebuilds open sessions only or a broader corpus.

**Warning signs:**
Backfill starts from `config.codex_sessions_path.rglob("*.jsonl")` without
filtering to live windows. Claude coverage differs from Codex because only one
runtime's historical tree was scanned. The search DB grows with closed sessions
after restart.

**Phase to address:**
Phase 2 - Backfill Worker and Rebuild Path, Phase 6 - Operational Hardening.

**Test/verification idea:**
Create many fake historical transcripts plus two active windows. Run backfill
and assert only active sessions are indexed in V1. Add a separate explicit test
for future all-history mode only when that requirement exists.

**Confidence:** HIGH. V1 scope is open sessions only, and repo concerns already
identify full session-tree scans as a performance bottleneck.

---

### Pitfall 12: Search Results Outlive Window Lifecycle

**What goes wrong:**
A result points to a window that has been killed, rebound, or replaced. Clicking
it silently selects the wrong session, shows no messages, or raises a confusing
404.

**Why it happens:**
Search rows are derived and may lag behind session state. Codi can rebind a
window to a new runtime session id, and tmux window IDs are stable for routing
only while the window exists.

**How to avoid:**
Phase 5 should validate result navigation against current `SessionManager`
state. If the indexed session is no longer open, show "session no longer open"
instead of navigating incorrectly. Phase 3 should update search metadata on
session changes and mark rows inactive when a window closes or session id
changes.

**Warning signs:**
Clicking a result only calls `setActiveId(row.window_id)` without checking live
session state. Search results do not include both `window_id` and `session_id`.
There is no inactive/stale state in result payloads.

**Phase to address:**
Phase 3 - Live Queue and Convergence, Phase 5 - Web UI Search Experience.

**Test/verification idea:**
Index a result, kill or rebind the window in mocked `SessionManager`, then click
or API-resolve the result. Assert the response marks it stale and does not
select the wrong window.

**Confidence:** HIGH. Existing Codi session state can rebind sessions and
window routing is intentionally based on tmux window IDs.

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Put search endpoints and indexing code directly into `src/codexbot/web/api.py` | Fast first endpoint | Makes an already large web module own worker state, schema, ranking, and status logic | Only a thin route wrapper is acceptable; search service code should live in focused modules |
| Use an in-memory `asyncio.Queue` for search live events | Simple queue implementation | Lost work on restart, no dead-letter handling, no convergence proof | Acceptable only behind an interface for a throwaway spike, not roadmap implementation |
| Use raw JSONL parsing in the worker | Avoids touching `TranscriptParser` | Codex/Claude differences, tool pairing, ordering, and UI parity drift | Never for production search; extend the shared parser instead |
| Key rows by message text hash | Easy dedupe | Drops repeated commands/errors and breaks provenance | Never |
| Index terminal pane snapshots | Captures visible text quickly | Duplicates transcript content, misses hidden history, includes transient UI chrome | Never for searchable history; pane text remains for streaming only |
| Skip status API until UI polish | Fewer endpoints early | UI cannot tell "not indexed yet" from "no matches" | Not acceptable; status is part of correctness for async backfill |
| Use `fast_search` everywhere | Lower latency in demos | Can hide recently added unindexed vectors | Only for an explicitly labeled indexed-only mode |
| Load embedding model at Python import time | Fewer worker lifecycle states | Slows startup, breaks tests, and couples web-only use to model availability | Never |
| Index all historical sessions in V1 | Impressive corpus size | Slow startup, larger DB, vague scope, and confusing stale results | Defer to a separate historical-search milestone |

## Integration Gotchas

Common mistakes when connecting search to existing Codi components and selected
libraries.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| `SessionMonitor` | Treat monitor offsets as search offsets | Keep search-owned ingest state; subscribe to parsed events without mutating monitor state |
| `TranscriptParser` | Fork parser logic in worker or web code | Extend parser once and reuse it for history, monitor, and search ingestion |
| `SessionManager` | Use cwd/name as search navigation identity | Store transcript identity and resolve current `window_id` through session state |
| Web `EventBus` | Assume event delivery is replayable | Queue live index work durably; WebSocket events remain client notification, not search source of truth |
| LanceDB FTS | Create FTS once and never optimize | Create FTS on searchable text columns and schedule optimize/maintenance for appended rows |
| LanceDB hybrid query | Use vector-only search and call it hybrid | Query both vector and text halves, apply metadata filters, and rerank/merge intentionally |
| Qwen3 embedding | Encode queries/documents identically without prompts | Use query prompt/instruction for queries, document mode for indexed rows, and persist model metadata |
| React Web UI | Render empty search as final during backfill | Bind UI to search status and label partial/degraded states clearly |

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Synchronous per-message embedding | Send latency, WebSocket lag, monitor loop delays | Worker process plus durable queue and batch flush | Immediately under active sessions with long assistant/tool output |
| Full transcript-tree scan on every startup | Slow boot, high disk activity, stale closed-session rows | Backfill only open sessions for V1; make historical indexing explicit later | Users with months of Codex/Claude sessions |
| Whole-transcript chunks | High memory use, poor snippets, weak ranking | Entry-level or bounded chunks with provenance and overlap | Long sessions or large tool outputs |
| Never optimizing LanceDB indexes | Query latency grows as unindexed tail grows | Track maintenance state and schedule optimize after row/batch thresholds | Continuous ingest over many live turns |
| Aggressive reranking with local model | CPU/memory spikes and slow results | Start with RRF or lightweight reranking; add heavier reranker only after local measurement | Many candidate rows or multi-session searches |
| No queue depth limits | Memory growth and stale work | Durable bounded queue, backpressure status, dead-letter handling | Worker offline or model slow |
| Indexing images/binary tool payloads as text | Storage bloat and bad snippets | Store image presence/provenance only unless multimodal search is explicitly planned | Sessions with screenshots/uploads |

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Expanding search scope beyond existing auth/admin boundary | Search makes secrets in transcripts easier to discover | Keep current web auth requirements, local-first deployment assumptions, and V1 open-session scope |
| Logging raw indexed text, queries, or snippets from transcripts | Sensitive prompts, file paths, tokens, or command output land in long-lived logs | Log counts, ids, offsets, status, and error classes; avoid raw transcript text in normal logs |
| Sending transcript text to cloud embedding APIs | Violates local-first/out-of-scope requirement and may leak sensitive local work | Use local model/worker only; make remote embedding unsupported in V1 |
| Indexing environment dumps or secrets-heavy tool output without policy | Search surfaces sensitive values faster than chat scrolling | Preserve transcript source of truth, but add future redaction policy only if it is shared with display/export semantics; do not ad hoc redact only search |
| Serving search DB files from static web routes | Direct database download by authenticated or misrouted browser clients | Store under `CODEXBOT_DIR` and expose only authenticated API responses |

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Empty state ignores backfill | Users think search is broken or no match exists | Show "indexing active sessions" with queue/backfill status |
| Results lack snippet provenance | Users cannot decide which hit matters | Show session name, runtime, cwd, role/content type, timestamp/order, and highlighted snippet |
| Search result click assumes row is live | Wrong session opens or UI errors after kill/rebind | Revalidate current `window_id` and mark stale results |
| Hybrid ranking hides exact command hits | Users cannot find the task with a known error/path | Boost exact lexical matches and support quoted/exact query behavior |
| Semantic degradation is silent | Users do not know why meaning-based results are weak | Show worker degraded/lexical-only status when embedder is unavailable |
| Backfill banner blocks normal chat | Search feels like startup is broken | Use compact status in search UI/sidebar, not modal blocking |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Search schema:** Has stable row identity, model metadata, transcript
  provenance, and mutable current-window metadata.
- [ ] **Backfill:** Indexes all open sessions on missing DB without blocking
  Codi startup or normal WebSocket/Telegram delivery.
- [ ] **Backfill/live convergence:** Appending to a transcript during backfill
  produces exactly one indexed row per transcript position.
- [ ] **Live queue:** Persists across restart and implements 32-item or
  60-second flush behavior.
- [ ] **Worker isolation:** Backend can import and serve `/api/sessions` without
  loading the embedding model.
- [ ] **Hybrid retrieval:** Exact command/path/error queries and semantic
  paraphrase queries both have golden tests.
- [ ] **LanceDB maintenance:** FTS/vector index creation and optimize behavior
  are part of rebuild or operational maintenance.
- [ ] **Status API:** UI can distinguish missing DB, backfill running, queue lag,
  worker failed, lexical-only, and ready.
- [ ] **UI navigation:** Clicking a result revalidates live session/window state.
- [ ] **Testing lane:** Backend tests, type checks, and `pnpm --dir web-ui build`
  remain the validation path.

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Duplicate or stale rows from bad identity | MEDIUM | Stop worker, bump search schema version if needed, rebuild from transcripts using stable row keys, add duplicate fixture tests |
| Missing rows from backfill/live race | MEDIUM | Re-run open-session rebuild, compare transcript positions vs indexed positions, add backfill watermark and durable queue |
| Monitor delivery broken by search offsets | HIGH | Restore `monitor_state.json` from backup if available, separate search state, add regression proving search does not mutate monitor state |
| Main backend stalls under embeddings | MEDIUM | Move model load/encode to worker, disable semantic mode temporarily, keep lexical search/status available |
| Live queue lost on restart | MEDIUM | Rebuild affected open sessions from transcripts, then replace in-memory queue with durable queue ledger |
| LanceDB unindexed tail causes slow/stale search | LOW to MEDIUM | Run optimize/maintenance, expose unindexed/maintenance status, tune cadence |
| Bad semantic quality from prompt/model misuse | LOW to MEDIUM | Rebuild embeddings with persisted model/prompt metadata and golden query evaluation |
| UI confusion during backfill | LOW | Add status endpoint response fields and frontend states before broad rollout |
| Result points to closed/rebound window | LOW | Mark rows inactive or stale, re-resolve window state at click/API time, rebuild current open-session metadata |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Unstable transcript identity | Phase 1 | Ingest repeated identical messages twice and assert idempotent row count and correct navigation metadata |
| Backfill/live race | Phase 2 and Phase 3 | Append while backfill is paused; assert exactly-once searchable rows after drain |
| Search mutates monitor offsets | Phase 1 and Phase 2 | Snapshot `monitor_state.json` before/after search rebuild and assert unchanged |
| Embedding in main backend | Phase 2 | Fake slow embedder while API/WebSocket smoke checks remain responsive |
| Non-durable live queue | Phase 3 | Restart worker mid-drain and assert pending work resumes without duplicates |
| LanceDB maintenance ignored | Phase 4 and Phase 6 | Add rows after index creation, check freshness/latency/status before and after optimize |
| Hybrid search misses exact technical terms | Phase 4 | Golden exact-query and semantic-query ranking tests |
| Wrong text indexed | Phase 1 and Phase 4 | Parser fixture matrix for user/assistant/tool/local-command/completion records |
| UI partial-index confusion | Phase 1 and Phase 5 | API status tests plus frontend states for initializing/running/failed/ready |
| Model prompt/resource misuse | Phase 2, Phase 4, Phase 6 | Embedder contract tests for dimension/model id/prompt metadata and optional local model smoke |
| Full historical scan in V1 | Phase 2 and Phase 6 | Fake many old transcripts; assert V1 indexes only active windows |
| Result outlives window lifecycle | Phase 3 and Phase 5 | Kill/rebind mocked window, then assert result is stale rather than misrouted |

## Sources

- Codi project context: `.planning/PROJECT.md` (HIGH confidence). Defines
  local-first open-session search, async initial backfill, separate worker,
  hybrid retrieval, Qwen3-Embedding-0.6B candidate, 32-item/60-second batching,
  and backfill status requirements.
- Codi architecture: `.planning/codebase/ARCHITECTURE.md` (HIGH confidence).
  Defines tmux `window_id` routing, shared `TranscriptParser`, `SessionMonitor`,
  WebSocket `EventBus`, Telegram queue path, monitor offsets, and anti-patterns.
- Codi concerns: `.planning/codebase/CONCERNS.md` (HIGH confidence). Identifies
  large orchestration modules, global queue/event state, EventBus overflow,
  full transcript scans, and history-cache scaling risks.
- Codi testing patterns: `.planning/codebase/TESTING.md` (HIGH confidence).
  Defines pytest/async testing patterns, tmp-path persistence tests, FastAPI
  tests, and frontend validation with `pnpm --dir web-ui build`.
- LanceDB hybrid search docs (HIGH confidence):
  https://docs.lancedb.com/search/hybrid-search
- LanceDB full-text search docs, including FTS index and optimize behavior
  (HIGH confidence): https://docs.lancedb.com/search/full-text-search
- LanceDB vector search docs, including async indexing and `fast_search`
  behavior (HIGH confidence): https://docs.lancedb.com/search/vector-search
- LanceDB indexing docs for vector, FTS, and scalar index categories
  (HIGH confidence): https://docs.lancedb.com/indexing
- Qwen3-Embedding-0.6B Hugging Face model card (HIGH confidence):
  https://huggingface.co/Qwen/Qwen3-Embedding-0.6B
- Context7 documentation lookup for LanceDB and sentence-transformers
  (HIGH confidence). Used to verify current hybrid search and prompt-aware
  encode guidance before writing this file.

---
*Pitfalls research for: Codi Web UI local hybrid session search*
*Researched: 2026-05-21*
