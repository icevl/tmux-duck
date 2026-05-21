# Feature Research

**Domain:** Local-first Web UI search for active Codex/Claude coding sessions
**Researched:** 2026-05-21
**Confidence:** HIGH for v1 feature shape; MEDIUM for v2 differentiators

## Feature Landscape

Codi search should be a session-navigation and recall feature, not a separate knowledge-base product. The v1 user is sitting in the Web UI with many live tmux-backed Codex and Claude sessions, trying to answer: "which session was working on this?" and "where in that transcript did the useful thing happen?"

The core result shape should be ranked sessions with nested matching hits/snippets. A session-level result answers whether this is the right window to open; hit-level snippets prove why it matched and give a direct jump target.

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Search entry in the existing session workflow | Search is primarily for switching among many active sessions, so it belongs in or near the sidebar/session switcher instead of a detached page. | MEDIUM | Add a compact search input or command-style overlay reachable from the sidebar and keyboard. Preserve current active chat, draft text, panels, pin/order behavior, and `/t/<window_id>` routing. |
| Open-session scope for v1 | Project scope says v1 is current open tmux sessions; users need the active work queue first. | LOW | Make scope explicit in UI copy/status. Do not silently search closed/archived Codex or Claude history in v1. |
| Cross-runtime parity | Codi manages Codex and Claude sessions side by side; search that misses one runtime breaks the core product promise. | MEDIUM | Index normalized transcript records from both runtime adapters. Result rows must show runtime, `window_id`, name, cwd, and session id when known. |
| Session metadata matching | Users often remember a repo, directory, branch-ish name, task title, runtime, tmux id, or session id before they remember transcript text. | LOW | Include session name, cwd, runtime, `window_id`, `session_id`, pane command, pinned state, and last activity in the searchable/rankable metadata. Routing remains keyed by `window_id`, not names. |
| Message/content matching across user, assistant, and useful tool/output text | The remembered clue may be in the user's ask, the model's answer, an error line, a command output, or a tool name. | HIGH | Use the existing transcript parser as the source of truth. Index richer local transcript text; do not inherit Telegram truncation. Avoid indexing transient terminal viewport text as canonical history. |
| Hybrid lexical + semantic retrieval | Exact identifiers/errors and meaning-based recollection both matter for coding sessions. | HIGH | Lexical search must reliably find exact paths, command names, errors, ticket IDs, and symbols. Semantic search should help with "that auth fix discussion" style queries. Use local retrieval only. |
| Ranked session groups with nested hits/snippets | External search UX patterns group results by container and show previews; Codi's natural container is a session. | HIGH | Return top sessions ordered by relevance, with each session showing top 2-3 hits, total hit count, score/rationale labels, role, timestamp, and transcript position. |
| Snippet highlighting and role/tool labels | Users need evidence before switching sessions. | MEDIUM | Snippets should be short, highlighted, and scannable: role (`user`, `assistant`, `tool`), optional `tool_name`, timestamp, and a 240-400 character window around the best match. Semantic-only hits can show the best chunk excerpt without fake exact highlights. |
| Click-through to session and hit | Search must reduce navigation time, not just list matches. | HIGH | Selecting a session result opens that `window_id`. Selecting a hit should load the relevant message window, scroll to it, and temporarily highlight it. Use transcript offset/index when available; fall back to timestamp/sequence. |
| Basic facets/filters | Message search tools commonly let users narrow by location, author/type, and time. Codi needs analogous filters for sessions. | MEDIUM | Include v1 filters for runtime (`codex`/`claude`), cwd/project, role/content type, active/busy/done status, and recent time range. Avoid a full query language initially. |
| Freshness and backfill status | Search will be wrong during initial indexing unless the UI explains freshness. | MEDIUM | Show index status: missing/building/ready/degraded, indexed session count, queue lag, and "new messages may take up to about 60s" style freshness. The Web UI should keep working while backfill runs. |
| Non-blocking failure states | The existing Web UI and delivery paths must not degrade because search is indexing or embedding. | MEDIUM | Search UI needs empty, loading, stale, degraded, and index-unavailable states. Search failures should not block session list, chat, WebSocket events, Telegram delivery, or terminal panels. |
| Local-only privacy boundary | Codi is a self-hosted host-control UI. Search must preserve that deployment model. | MEDIUM | Do not send transcript text to cloud embeddings/search. Do not build a browser-side full-text index containing all session content. Persist the derived index under the configured local state directory and make it rebuildable. |
| Result limits and pagination | Many active sessions can contain long histories; dumping everything is unusable. | LOW | Default to a small result set: e.g. top 10 sessions, top 3 hits each, with "more hits in this session" expansion. Cap snippet payloads to keep API responses small. |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required for the first usable v1, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Session-aware ranking boosts | Generic search ranks documents; Codi can rank by live-session usefulness. | MEDIUM | Relevance is primary, but boost exact metadata matches, active/busy sessions, recent activity, pinned sessions, and the currently selected project. Keep boosts explainable so stale active sessions do not bury better matches. |
| Match rationale labels | Users can trust results faster when they know why a session matched. | MEDIUM | Labels such as `exact path`, `tool output`, `semantic`, `session cwd`, `assistant answer`, or `recent active` make ranking less opaque. |
| Inline preview without switching | Users can inspect several candidate sessions before changing context. | MEDIUM | Expand a result to show more hits and a little surrounding context. Keep it lightweight; full transcript reading remains in ChatView. |
| Query chips from typed intent | Search can feel fast without exposing a formal grammar. | MEDIUM | Convert UI selections or simple typed tokens into chips: `runtime:claude`, `role:tool`, `cwd:rag-webapp`, `after:today`. Start as UI chips, not a GitHub-grade parser. |
| Current-session find mode | Once inside the right session, users may want local navigation within the transcript. | MEDIUM | Add "find in this session" as a scoped mode reusing the same result renderer and jump behavior. This should not replace browser `Ctrl+F`; it should use transcript positions and history pagination. |
| Search recent queries | Repeated debugging often uses the same errors or issue IDs. | LOW | Store recent query strings locally in the browser, without storing transcript results. |
| Index diagnostics and rebuild controls | Local derived indexes occasionally drift or get corrupted. | MEDIUM | Add a small admin/status surface: rebuild open-session index, show last backfill time, failed session paths, queued item count, and model/index version. |
| Closed/resumable session search | The long-term value grows when old Codex/Claude sessions are searchable. | HIGH | Defer until open-session v1 proves document modeling, ranking, and jump behavior. Requires runtime-aware resume history, archive scope controls, and stronger index lifecycle management. |
| Search commands, skills, and choices alongside transcript hits | Codi already has command/skill hints and GSD choices; search could become a unified "what can I do or where was it discussed?" surface. | MEDIUM | Keep separate result sections for sessions, messages, commands, and skills. Do not mix command execution into transcript result clicks. |
| Task/decision extraction on top of search | Semantic search can later surface "decisions", "blockers", and "next actions" across sessions. | HIGH | This is a v2 layer over reliable retrieval, not a v1 requirement. It likely needs summarization/index enrichment and stronger evaluation. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Search all historical/closed sessions in v1 | More corpus feels more powerful. | It expands scope, startup cost, privacy risk, ranking ambiguity, and runtime-specific resume/history bugs before active-session search is proven. | V1 searches open tmux sessions only. Add closed/resumable session search after index lifecycle and result jumping are stable. |
| Cloud embeddings or hosted search | Easier implementation and higher-quality models. | Violates local-first/self-hosted expectations and may expose raw coding transcripts/secrets. | Use local embeddings and a local derived index. Keep cloud search out of v1. |
| Synchronous indexing on message delivery | Makes every new message immediately searchable. | Embedding/index writes on the hot path can stall FastAPI, WebSocket events, Telegram delivery, and session monitoring. | Queue live items and batch indexing in the separate local worker/service. Surface freshness lag. |
| Browser-side full transcript index | Avoids backend work and feels simple. | Sends too much transcript text to the browser, consumes memory, duplicates ranking logic, and breaks with long histories. | Backend search endpoint returns bounded ranked sessions and snippets. |
| Full GitHub/Sourcegraph-style query language in v1 | Power users like boolean, regex, and qualifiers. | Parser and explainability work can dominate the milestone and create fragile edge cases. | Provide simple filters/chips and exact phrase support first; defer boolean/regex grammar. |
| Terminal scrollback search as source of truth | Users see terminal text and expect it searchable. | Pane text is transient, lossy, and separate from normalized transcript history. It can duplicate or contradict transcript records. | Index transcript-normalized messages and useful tool/output records. Consider terminal viewport find as a separate terminal-panel feature later. |
| Name-keyed routing or result identity | Names are human-readable. | Codi's core invariant is routing by tmux `window_id`; names can change and collide. | Result identity and jump actions use `window_id` plus transcript offsets/indexes. Names are display metadata only. |
| Search-triggered session mutation | "Open/restart/resume from search" feels convenient. | Search should not kill, resume, reorder, or create sessions by accident. | Result clicks only select/open and optionally jump. Mutating actions stay behind existing explicit controls. |
| Telegram search parity in v1 | There is already a Telegram channel. | Telegram result rendering, truncation, topics, and rate limits are different enough to distract from Web UI requirements. | Build Web UI search first. Later expose a topic-safe Telegram command if there is demand. |
| Per-user ACL semantics in v1 | Hosted tools often filter results per user. | Codi's Web UI is a local admin console with existing auth, not a multi-tenant product. Adding per-session ACLs would imply broader authorization work. | Keep search behind existing Web UI auth and local host-control assumptions. |

## UX Result Shape

Recommended v1 response shape:

```typescript
interface SearchResponse {
  query: string;
  index_status: "missing" | "building" | "ready" | "stale" | "degraded";
  freshness_lag_seconds: number | null;
  sessions_indexed: number;
  sessions_total: number;
  results: SearchSessionResult[];
}

interface SearchSessionResult {
  window_id: string;
  session_id: string | null;
  runtime: string;
  name: string;
  cwd: string;
  last_activity: number | null;
  status: "active" | "busy" | "done" | "unknown";
  pinned: boolean;
  score: number;
  match_summary: string;
  hit_count: number;
  hits: SearchHit[];
}

interface SearchHit {
  role: string;
  content_type: string;
  tool_name?: string | null;
  timestamp?: string | null;
  transcript_offset?: number | null;
  transcript_index?: number | null;
  score: number;
  match_type: "lexical" | "semantic" | "metadata" | "hybrid";
  snippet: string;
  highlights: Array<{ start: number; end: number }>;
}
```

Recommended rendering:

- Show one search box, result count, and index status.
- Results are grouped by session. The row header shows runtime icon, session name, cwd basename/path, status, last activity, and a concise match summary.
- Each session group shows up to 3 hits by default. Each hit shows role/tool, time, short snippet, and highlight spans.
- Selecting the session header switches to the session. Selecting a hit switches and scrolls/highlights the message.
- Relevance sort is primary. Session recency, busy/done state, pinned state, and active project are boosts/tie-breakers, not replacements for relevance.
- Empty states should distinguish "no matches" from "index still building" and "search unavailable".

## Feature Dependencies

```text
Transcript normalization
    └──requires──> Search document model
                       └──requires──> Backfill ingestion
                       └──requires──> Live indexing queue
                                      └──requires──> Index freshness status

Session metadata snapshot
    └──enhances──> Ranking, filters, and result headers

Hybrid retrieval
    └──requires──> Lexical index
    └──requires──> Local embedding/vector index
    └──requires──> Result merge/rerank
                       └──enhances──> Ranked session groups

Search API
    └──requires──> Bounded result DTOs
    └──requires──> Authenticated Web UI route
                       └──requires──> Sidebar/search UI rendering
                                      └──requires──> Hit jump behavior

Closed-session search
    └──requires──> Stable open-session search
    └──requires──> Runtime-aware resume history
    └──requires──> Archive/index lifecycle policy
```

### Dependency Notes

- **Search document model requires transcript normalization:** The index should be derived from the same Codex/Claude transcript parsing that powers history, so search does not create a second source of truth.
- **Live indexing queue requires backfill coordination:** New messages must be queued while initial backfill is running, then drained without duplicating documents.
- **Hit jump behavior requires transcript positions:** v1 should store enough position metadata to fetch and scroll around a hit without loading an entire long transcript into the browser.
- **Filters require session metadata snapshot:** Runtime/cwd/status filters should come from Codi session state, not ad hoc parsing of display names.
- **Closed-session search requires runtime-aware history:** Current concerns already call out Codex-centered resume indexing; v2 historical search should not proceed until Claude history parity is solved.

## MVP Definition

### Launch With (v1)

Minimum viable product needed to validate session search.

- [ ] Sidebar/command-style search entry across currently open sessions only.
- [ ] Backend search endpoint returning ranked session groups with nested hit snippets.
- [ ] Index document model covering session metadata plus user, assistant, and useful tool/output transcript text from Codex and Claude.
- [ ] Background initial backfill for open sessions with non-blocking UI/API behavior.
- [ ] Live indexing queue for new transcript items with bounded freshness lag.
- [ ] Hybrid lexical + semantic retrieval using local-only storage/embeddings.
- [ ] Basic filters for runtime, cwd/project, role/content type, status, and recent time range.
- [ ] Click-through from result to session, and from hit to highlighted transcript message.
- [ ] Index status and degraded/empty/loading states in the Web UI.

### Add After Validation (v1.x)

Features to add once users prove the core result shape is useful.

- [ ] Expand more hits within a session result.
- [ ] Manual reindex and index diagnostics in a small admin/status surface.
- [ ] Recent query history stored locally in the browser.
- [ ] Query chips and exact phrase support beyond basic filters.
- [ ] Current-session scoped transcript find mode.
- [ ] Ranking/reranker tuning based on real queries and missed results.

### Future Consideration (v2+)

Features to defer until open-session search is stable.

- [ ] Closed/resumable historical session search.
- [ ] Advanced boolean/regex query language.
- [ ] Search across commands, skills, GSD choices, and settings as separate result sections.
- [ ] Decision/blocker/task extraction over search results.
- [ ] Telegram search command.
- [ ] Configurable embedding/index backend selection from the Web UI.
- [ ] Multi-user or shared-host authorization semantics.

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Search open sessions from sidebar/search overlay | HIGH | MEDIUM | P1 |
| Ranked sessions with top snippets | HIGH | HIGH | P1 |
| Cross-runtime transcript indexing | HIGH | MEDIUM | P1 |
| Hybrid lexical + semantic retrieval | HIGH | HIGH | P1 |
| Click-through and hit highlighting | HIGH | HIGH | P1 |
| Backfill/live index freshness status | HIGH | MEDIUM | P1 |
| Runtime/cwd/role/status/time filters | MEDIUM | MEDIUM | P1 |
| Inline result expansion | MEDIUM | MEDIUM | P2 |
| Query chips/recent queries | MEDIUM | LOW | P2 |
| Index diagnostics/rebuild | MEDIUM | MEDIUM | P2 |
| Current-session find mode | MEDIUM | MEDIUM | P2 |
| Closed-session search | HIGH | HIGH | P3 |
| Full boolean/regex query language | MEDIUM | HIGH | P3 |
| Task/decision extraction | MEDIUM | HIGH | P3 |
| Telegram search parity | LOW | MEDIUM | P3 |

**Priority key:**
- P1: Must have for v1 launch
- P2: Should have after validation
- P3: Future consideration

## Competitor Feature Analysis

| Feature | VS Code / IDE Search | Slack / Message Search | GitHub / Code Search | Our Approach |
|---------|----------------------|------------------------|----------------------|--------------|
| Result grouping | VS Code groups search results by file and shows hit previews. JetBrains Search Everywhere groups navigable item types from one entry point. | Slack separates result types such as messages/files/people/channels and supports filtering. | GitHub returns code/file matches with qualifiers. | Group by session first, then show matching transcript hits/snippets. Session is Codi's equivalent of file/channel. |
| Filters/scope | VS Code supports include/exclude patterns and search details. JetBrains offers tabs/filters. | Slack supports modifiers like `in:`, `from:`, date filters, and result type filters. | GitHub supports qualifiers such as repo/path/language/content plus boolean operators. | Offer simple v1 filters for runtime, cwd, role, status, and time. Avoid full query grammar until usage proves need. |
| Exact vs fuzzy/semantic | VS Code/GitHub emphasize exact text, regex, and code-aware qualifiers. | Slack supports phrase search and exclusion. | GitHub supports exact strings, boolean operations, and regex. | Use hybrid retrieval: exact lexical matching for technical artifacts plus semantic matching for remembered intent. |
| Navigation | Search tools jump directly to file, result, or conversation context. | Slack opens the conversation around the message. | GitHub opens files/lines. | Result header opens the session; hit opens the session and scrolls/highlights the transcript message. |
| Search scope | IDEs search a project/workspace; Slack searches conversations; Sourcegraph uses search contexts. | Scopes map to channels/users/date. | Scopes map to repos/orgs/paths. | Scope maps to open tmux sessions for v1, with cwd/runtime/status filters. Closed-session search is a later scope expansion. |

## Sources

- Local project context: `.planning/PROJECT.md` (Codi session search scope, local-first constraints, open-session v1, hybrid retrieval, non-blocking indexing).
- Local codebase map: `.planning/codebase/STRUCTURE.md` (FastAPI/WebSocket backend, React sidebar/chat, transcript monitor/parser, runtime adapters).
- Local conventions: `.planning/codebase/CONVENTIONS.md` (Web API/frontend wiring and test expectations).
- Local risks: `.planning/codebase/CONCERNS.md` (large Web/API modules, runtime-aware resume gaps, performance and event-bus concerns).
- VS Code documentation, "Search across files" and "Advanced search options" (grouped file results, hit previews, include/exclude, regex): https://code.visualstudio.com/docs/editing/codebasics
- Slack Help, "Search in Slack" (message modifiers, result filters, sorting): https://slack.com/help/articles/202528808-How-to-search-in-Slack
- GitHub Docs, "Understanding GitHub Code Search syntax" (exact strings, boolean operators, qualifiers, regex): https://github.com/github/docs/blob/main/content/search-github/github-code-search/understanding-github-code-search-syntax.md
- JetBrains IntelliJ IDEA Help, "Search Everywhere" (single entry point, tabs, filters, text search, result navigation): https://www.jetbrains.com/help/idea/searching-everywhere.html
- LanceDB documentation, "Hybrid Search" (vector + full-text search with reranking, filters, row IDs): https://docs.lancedb.com/search/hybrid-search
- Context7 LanceDB documentation lookup, 2026-05-21 (confirmed hybrid search support and Python query patterns).

## Confidence Notes

- **HIGH confidence:** v1 should use ranked session groups with nested snippets, open-session scope, Web UI integration, non-blocking indexing, and local-only retrieval. These are directly supported by project context and Codi's architecture.
- **MEDIUM confidence:** advanced query chips, current-session find, and diagnostic/rebuild surfaces. They follow common product patterns but should be validated after real search usage.
- **LOW confidence / deliberately deferred:** task extraction, closed-session historical search, Telegram parity, and multi-user authorization. These require separate requirements and risk pulling v1 away from the active-session workflow.

---
*Feature research for: Codi Web UI session search*
*Researched: 2026-05-21*
