# Phase 3: Live Queue and Convergence - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-05-22
**Phase:** 3-Live Queue and Convergence
**Areas discussed:** Queue capture timing, Deduplication identity, Backfill/live overlap, Failure and stale-session behavior

---

## Queue Capture Timing

| Question | Option | Description | Selected |
|----------|--------|-------------|----------|
| What should the live queue treat as the atomic item to index? | Parsed entry | Queue each useful text-bearing transcript item with provenance; matches Phase 2 backfill/parser identity. | yes |
| What should the live queue treat as the atomic item to index? | Completed turn | Queue one consolidated item after a turn completes; simpler UI narrative but slower and easier to miss tool/output details. | |
| What should the live queue treat as the atomic item to index? | Hybrid | Queue entries as they arrive, then update/close a turn bundle when completion is observed. | |
| Where should live queue items be created from? | Monitor listener | Attach to SessionMonitor transcript events and persist queue rows off the hot send path. | yes |
| Where should live queue items be created from? | Worker tailer | Have the search worker tail transcript files itself; more isolated but duplicates monitor/parser logic. | |
| Where should live queue items be created from? | Periodic scan | Poll open sessions periodically; lowest coupling but weaker freshness and harder offset accounting. | |
| If live queue persistence is temporarily slow or failing, what should happen to normal message delivery? | Deliver and lag | Keep Web UI/Telegram delivery moving; expose search queue lag/error and recover from transcript watermarks. | yes |
| If live queue persistence is temporarily slow or failing, what should happen to normal message delivery? | Block delivery | Wait for queue durability before advancing; strongest indexing guarantee but can make chat feel stuck. | |
| If live queue persistence is temporarily slow or failing, what should happen to normal message delivery? | Best effort | Do not surface lag; failed queue writes are recovered only by later rebuild/backfill. | |
| Which live transcript items should be queued for search indexing? | Useful text | Queue user text, assistant text, and meaningful tool/output text; matches Phase 2 broad text-bearing backfill. | yes |
| Which live transcript items should be queued for search indexing? | Chat only | Queue only user and assistant conversation text; cleaner search but misses tool results and evidence. | |
| Which live transcript items should be queued for search indexing? | Everything textual | Queue every text-bearing transcript event, including noisy status/progress events. | |

**User's choice:** Parsed entry; Monitor listener; Deliver and lag; Useful text.
**Notes:** The user chose to move to the next area after this set.

---

## Deduplication Identity

| Question | Option | Description | Selected |
|----------|--------|-------------|----------|
| Should queue item identity and search document identity be separate concepts? | Separate IDs | Use a queue item id for leases/retries and transcript-based row identity for idempotent index writes. | yes |
| Should queue item identity and search document identity be separate concepts? | Row ID only | Use the search row identity as the queue id too; simpler but harder to represent retries and failed attempts cleanly. | |
| Should queue item identity and search document identity be separate concepts? | Queue ID only | Treat each queue row as unique; easiest for leasing but risks duplicate search documents. | |
| What should define the idempotent search row identity for live items? | Transcript provenance | Use runtime/session transcript provenance plus entry offset/index and chunk index; aligns with Phase 2 backfill. | yes |
| What should define the idempotent search row identity for live items? | Content hash | Hash normalized text and metadata; catches duplicates but can merge distinct repeated messages incorrectly. | |
| What should define the idempotent search row identity for live items? | Window metadata | Use tmux window/session metadata; easy to route but unstable when windows are renamed or recreated. | |
| How should long live entries be chunked for idempotent writes? | Same chunker | Use the same deterministic chunking policy as backfill so live and rebuild generate identical chunk ids. | yes |
| How should long live entries be chunked for idempotent writes? | One doc per entry | Simpler identity but large tool outputs may be oversized or poorly searchable. | |
| How should long live entries be chunked for idempotent writes? | Worker decides | Let the worker split opportunistically; flexible but weakens live/backfill convergence guarantees. | |
| When a duplicate live/backfill row is produced, how should the index write behave? | Idempotent upsert | Write by stable row identity so retries and backfill/live overlap replace the same document, not append duplicates. | yes |
| When a duplicate live/backfill row is produced, how should the index write behave? | Drop before worker | Prevent duplicate queue rows as early as possible; useful but not enough for crash/retry overlap by itself. | |
| When a duplicate live/backfill row is produced, how should the index write behave? | Append versions | Keep every occurrence; preserves event history but violates the no-duplicate search-doc criterion. | |

**User's choice:** Separate IDs; Transcript provenance; Same chunker; Idempotent upsert.
**Notes:** The user chose to move to the next area after this set.

---

## Backfill/live Overlap

| Question | Option | Description | Selected |
|----------|--------|-------------|----------|
| How should Phase 3 define the boundary between backfill-owned and live-owned transcript items? | Watermark plus upsert | Record per-session backfill watermarks and still rely on idempotent upserts for any boundary overlap. | yes |
| How should Phase 3 define the boundary between backfill-owned and live-owned transcript items? | Upsert only | Queue everything live and let row-identity upserts absorb all duplicates; simpler but more redundant work. | |
| How should Phase 3 define the boundary between backfill-owned and live-owned transcript items? | Pause live | Do not queue live items until backfill finishes; simpler but violates working-while-backfill behavior. | |
| What granularity should backfill/live watermarks use? | Transcript file | Track runtime/session transcript path plus byte offset or entry index; stable across tmux window changes. | yes |
| What granularity should backfill/live watermarks use? | Tmux window | Track by active window id; easy for open sessions but unstable once windows close or move. | |
| What granularity should backfill/live watermarks use? | Global only | Track one generation-wide checkpoint; simpler status but weak per-session recovery and resume behavior. | |
| Where should live batches converge while the initial backfill generation is still building? | Same generation | Apply live upserts into the current writable search generation using the same row identities as backfill. | yes |
| Where should live batches converge while the initial backfill generation is still building? | Queue until done | Keep live items durable but do not write them until backfill finishes; simpler but visibly slower to converge. | |
| Where should live batches converge while the initial backfill generation is still building? | Live overlay | Maintain a separate live overlay and merge later; faster reads later but adds a second index path. | |
| If a transcript watermark is stale or uncertain after restart, what should recovery do? | Replay safely | Resume from the last safe transcript offset/index and tolerate duplicates through idempotent upserts. | yes |
| If a transcript watermark is stale or uncertain after restart, what should recovery do? | Skip ahead | Move to the latest transcript position to avoid extra work; fastest but can miss messages. | |
| If a transcript watermark is stale or uncertain after restart, what should recovery do? | Force rebuild | Discard live progress and require a full rebuild; safest but heavy for normal restarts. | |

**User's choice:** Watermark plus upsert; Transcript file; Same generation; Replay safely.
**Notes:** The user chose to move to the next area after this set.

---

## Failure and Stale-Session Behavior

| Question | Option | Description | Selected |
|----------|--------|-------------|----------|
| How should failed live indexing queue items be retried? | Bounded retries | Persist attempts, lease expiry, last error, then move exhausted items to failed/dead-letter state for status and rebuild recovery. | yes |
| How should failed live indexing queue items be retried? | Retry forever | Keep failed items pending indefinitely; simple but can block batches and hide permanent parser/index bugs. | |
| How should failed live indexing queue items be retried? | Drop on failure | Do not retry failed items; fastest but breaks convergence unless a full rebuild later recovers them. | |
| How should queue lag and failed items affect user-visible search status? | Degraded status | Keep sessions usable, but show queue lag, failed count, and last error through search status. | yes |
| How should queue lag and failed items affect user-visible search status? | Logs only | Do not surface queue failures in Web UI/API status; simpler but hard to diagnose stale search results. | |
| How should queue lag and failed items affect user-visible search status? | Disable search | Mark search unavailable whenever live indexing has failures; strict but noisy during transient issues. | |
| When a tmux-backed session is no longer open, how should its search documents behave in V1? | Hide stale | Mark documents stale and exclude them from normal results so clicks never route to a dead tmux window. | yes |
| When a tmux-backed session is no longer open, how should its search documents behave in V1? | Show marked | Keep them searchable with a stale label; useful history but requires dead-link handling in the UI. | |
| When a tmux-backed session is no longer open, how should its search documents behave in V1? | Delete docs | Remove closed-session documents from the derived index; clean results but loses recent history until rebuild. | |
| How should failed/dead-letter queue items be recovered after a fix or restart? | Requeue on rebuild | Keep failed records inspectable and let rebuild/retry controls requeue them through the normal idempotent path. | yes |
| How should failed/dead-letter queue items be recovered after a fix or restart? | Auto on restart | Automatically requeue all failed items on every process start; simple but can repeat permanent failures noisily. | |
| How should failed/dead-letter queue items be recovered after a fix or restart? | Manual only | Require direct state-file cleanup or a future admin tool; minimal scope but poor operational recovery. | |

**User's choice:** Bounded retries; Degraded status; Hide stale; Requeue on rebuild.
**Notes:** The user selected finish after this set and confirmed the context was ready to write.

---

## the agent's Discretion

No business-level decisions were delegated to the agent.

## Deferred Ideas

None.
