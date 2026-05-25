import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Brain,
  ChevronDown,
  Clock3,
  Filter,
  Loader2,
  Pin,
  Search,
  X,
} from "lucide-react";
import {
  api,
  SearchHighlight,
  SearchHit,
  SearchResponse,
  SearchSessionResult,
  SearchStatusResponse,
  SessionSummary,
} from "../api";

const ICON = 16;
const MIN_QUERY_LENGTH = 2;
const DEFAULT_LIMIT = 10;
const DEFAULT_HITS_PER_SESSION = 3;

type RuntimeFilter = "all" | "codex" | "claude";
type RoleFilter = "all" | "user" | "agent" | "tool";
type RecentFilter = "any" | "1h" | "24h" | "7d";

export interface SearchHitTarget {
  target_id: string;
  window_id: string;
  session_id: string | null;
  transcript_offset: number | null;
  transcript_index: number | null;
  chunk_index: number | null;
  source_order: number;
  snippet: string;
}

interface Props {
  sessions: SessionSummary[];
  onOpenResult: (windowId: string) => void;
  onOpenHit?: (target: SearchHitTarget) => void;
  onHasActiveQueryChange: (active: boolean) => void;
}

const runtimeOptions: Array<{ value: RuntimeFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "codex", label: "Codex" },
  { value: "claude", label: "Claude" },
];

const roleOptions: Array<{ value: RoleFilter; label: string }> = [
  { value: "all", label: "All" },
  { value: "user", label: "User" },
  { value: "agent", label: "Agent" },
  { value: "tool", label: "Tool" },
];

const recentOptions: Array<{ value: RecentFilter; label: string }> = [
  { value: "any", label: "Any" },
  { value: "1h", label: "1h" },
  { value: "24h", label: "24h" },
  { value: "7d", label: "7d" },
];

function statusLabel(status: SearchStatusResponse | null): string {
  if (!status) return "Unavailable";
  switch (status.state) {
    case "ready":
      return "Ready";
    case "building":
    case "partial":
      return "Indexing";
    case "stale":
      return "Stale";
    case "degraded":
      return "Degraded";
    case "missing":
      return "Missing";
    case "unavailable":
      return "Unavailable";
  }
}

function statusTone(status: SearchStatusResponse | null): string {
  if (!status || !status.available || status.state === "unavailable") {
    return "danger";
  }
  if (
    status.state === "building" ||
    status.state === "partial" ||
    status.state === "stale" ||
    status.state === "degraded" ||
    status.state === "missing"
  ) {
    return "warn";
  }
  return "ok";
}

function cwdBase(cwd: string): string {
  const parts = cwd.split("/").filter(Boolean);
  return parts.at(-1) ?? cwd;
}

function formatRelative(ts: number | null): string {
  if (!ts) return "";
  const sec = Math.floor(Date.now() / 1000 - ts);
  if (sec < 5) return "just now";
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  if (sec < 86400) return `${Math.floor(sec / 3600)}h ago`;
  return `${Math.floor(sec / 86400)}d ago`;
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "unknown";
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  return `${Math.floor(seconds / 86400)}d`;
}

function recentSeconds(filter: RecentFilter): number | null {
  switch (filter) {
    case "1h":
      return 3600;
    case "24h":
      return 86400;
    case "7d":
      return 604800;
    case "any":
      return null;
  }
}

function rolePayload(filter: RoleFilter): {
  role: string | null;
  content_type: string | null;
} {
  switch (filter) {
    case "user":
      return { role: "user", content_type: null };
    case "agent":
      return { role: "assistant", content_type: null };
    case "tool":
      return { role: null, content_type: "tool_use" };
    case "all":
      return { role: null, content_type: null };
  }
}

function hitLabel(hit: SearchHit): string {
  if (hit.provenance.tool_name) return hit.provenance.tool_name;
  if (hit.provenance.content_type === "tool_use") return "Tool";
  if (hit.provenance.role === "assistant") return "Agent";
  if (hit.provenance.role === "user") return "User";
  return hit.provenance.role || "System";
}

function renderSnippet(snippet: string, highlights: SearchHighlight[]) {
  const sorted = [...highlights]
    .filter((h) => h.start >= 0 && h.end > h.start && h.end <= snippet.length)
    .sort((a, b) => a.start - b.start);
  const parts: JSX.Element[] = [];
  let cursor = 0;
  sorted.forEach((highlight, idx) => {
    if (highlight.start < cursor) return;
    if (highlight.start > cursor) {
      parts.push(
        <span key={`text-${idx}`}>{snippet.slice(cursor, highlight.start)}</span>,
      );
    }
    parts.push(
      <mark key={`mark-${idx}`} title={highlight.label}>
        {snippet.slice(highlight.start, highlight.end)}
      </mark>,
    );
    cursor = highlight.end;
  });
  if (cursor < snippet.length) {
    parts.push(<span key="text-tail">{snippet.slice(cursor)}</span>);
  }
  return parts.length > 0 ? parts : snippet;
}

function statusPanel(
  active: boolean,
  loading: boolean,
  error: string | null,
  response: SearchResponse | null,
  status: SearchStatusResponse | null,
) {
  if (!active) return null;
  if (loading) {
    return {
      title: "Searching...",
      body: null,
      tone: "loading",
    };
  }
  if (error) {
    return {
      title: "Search unavailable",
      body: error,
      tone: "danger",
    };
  }
  const effective = response?.status ?? status;
  if (response?.outcome === "unavailable" || effective?.state === "unavailable") {
    return {
      title: "Search unavailable",
      body: "Keep working and try again after indexing recovers.",
      tone: "danger",
    };
  }
  if (response?.outcome === "not_ready" || effective?.state === "building") {
    return {
      title: "Indexing",
      body: "Results may be incomplete.",
      tone: "warn",
    };
  }
  if (effective?.state === "stale") {
    return {
      title: "Stale",
      body: "Search is behind the latest session activity.",
      tone: "warn",
    };
  }
  if (response && response.results.length === 0) {
    return {
      title: "No matches",
      body: "Try different terms or filters.",
      tone: "muted",
    };
  }
  return null;
}

export function SessionSearch({
  sessions,
  onOpenResult,
  onOpenHit,
  onHasActiveQueryChange,
}: Props) {
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [runtime, setRuntime] = useState<RuntimeFilter>("all");
  const [role, setRole] = useState<RoleFilter>("all");
  const [pinned, setPinned] = useState(false);
  const [recent, setRecent] = useState<RecentFilter>("any");
  const [status, setStatus] = useState<SearchStatusResponse | null>(null);
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [detailsOpen, setDetailsOpen] = useState(false);
  const requestSeq = useRef(0);

  const trimmedQuery = query.trim();
  const active = trimmedQuery.length >= MIN_QUERY_LENGTH;

  useEffect(() => {
    onHasActiveQueryChange(active);
  }, [active, onHasActiveQueryChange]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setDebouncedQuery(trimmedQuery);
    }, 260);
    return () => window.clearTimeout(timer);
  }, [trimmedQuery]);

  useEffect(() => {
    let cancelled = false;
    const load = () => {
      api.getSearchStatus()
        .then((next) => {
          if (!cancelled) setStatus(next);
        })
        .catch((err: Error) => {
          if (!cancelled) setError(err.message);
        });
    };
    load();
    const interval = window.setInterval(load, 10000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    if (debouncedQuery.length < MIN_QUERY_LENGTH) {
      setResponse(null);
      setLoading(false);
      return;
    }

    const seq = ++requestSeq.current;
    const roleFields = rolePayload(role);
    setLoading(true);
    setError(null);
    api
      .searchSessions({
        query: debouncedQuery,
        limit: DEFAULT_LIMIT,
        hits_per_session: DEFAULT_HITS_PER_SESSION,
        runtime: runtime === "all" ? null : runtime,
        role: roleFields.role,
        content_type: roleFields.content_type,
        pinned: pinned ? true : null,
        recent_seconds: recentSeconds(recent),
      })
      .then((next) => {
        if (seq !== requestSeq.current) return;
        setResponse(next);
        setStatus(next.status);
      })
      .catch((err: Error) => {
        if (seq !== requestSeq.current) return;
        setResponse(null);
        setError(err.message);
      })
      .finally(() => {
        if (seq === requestSeq.current) setLoading(false);
      });
  }, [debouncedQuery, pinned, recent, role, runtime]);

  const sessionById = useMemo(
    () => new Map(sessions.map((session) => [session.window_id, session])),
    [sessions],
  );

  const panel = statusPanel(active, loading, error, response, status);
  const effectiveStatus = response?.status ?? status;
  const operations = effectiveStatus?.operations ?? null;
  const searchDetailsId = "session-search-status-details";
  const showLexicalNotice =
    response?.status.state === "degraded" && response.results.length > 0;

  const openHit = (result: SearchSessionResult, hit: SearchHit) => {
    const target: SearchHitTarget = {
      target_id: `${result.routing.window_id}:${hit.source_order}:${Date.now()}`,
      window_id: result.routing.window_id,
      session_id: hit.provenance.session_id,
      transcript_offset: hit.provenance.transcript_offset,
      transcript_index: hit.provenance.transcript_index,
      chunk_index: hit.identity.chunk_index,
      source_order: hit.source_order,
      snippet: hit.snippet,
    };
    if (onOpenHit) onOpenHit(target);
    else onOpenResult(result.routing.window_id);
  };

  return (
    <div className={`session-search${active ? " active" : ""}`}>
      <label className="session-search-input-wrap">
        <Search size={ICON} aria-hidden="true" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search open sessions"
          aria-label="Search open sessions"
        />
        {query && (
          <button
            type="button"
            className="session-search-clear"
            onClick={() => setQuery("")}
            aria-label="Clear search"
            title="Clear search"
          >
            <X size={14} />
          </button>
        )}
      </label>

      <div className="session-search-meta">
        <span className={`search-status ${statusTone(effectiveStatus)}`}>
          {loading ? <Loader2 size={12} className="activity-spinner" /> : null}
          {statusLabel(effectiveStatus)}
        </span>
        <span className="search-scope">Open sessions only</span>
        {effectiveStatus?.counters && (
          <span className="search-counts">
            {effectiveStatus.counters.indexed_sessions}/
            {effectiveStatus.counters.open_sessions} indexed
          </span>
        )}
        <button
          type="button"
          className="search-details-toggle"
          aria-expanded={detailsOpen}
          aria-controls={searchDetailsId}
          onClick={() => setDetailsOpen((current) => !current)}
        >
          <ChevronDown
            size={12}
            className={detailsOpen ? "expanded" : ""}
            aria-hidden="true"
          />
          {detailsOpen ? "Hide details" : "Show details"}
        </button>
      </div>

      {detailsOpen && (
        <div
          id={searchDetailsId}
          className="search-status-details"
          aria-label="Search status details"
        >
          {operations ? (
            <>
              <div className="search-detail-row">
                <span>Worker heartbeat</span>
                <strong>
                  {operations.worker.status ?? "inactive"}
                  {operations.worker.stale ? " stale" : ""}
                </strong>
                <small>
                  {operations.worker.heartbeat_at
                    ? `${formatDuration(
                        operations.worker.heartbeat_age_seconds,
                      )} ago`
                    : "no heartbeat"}
                </small>
              </div>
              <div className="search-detail-row">
                <span>Queue lag</span>
                <strong>
                  {operations.queue.queued_items + operations.queue.leased_items}
                  {" queued"}
                </strong>
                <small>
                  {operations.queue.failed_items} failed
                  {operations.queue.oldest_queued_age_seconds != null
                    ? `, oldest ${formatDuration(
                        operations.queue.oldest_queued_age_seconds,
                      )}`
                    : ""}
                </small>
              </div>
              <div className="search-detail-row">
                <span>Backfill</span>
                <strong>
                  {operations.progress.indexed_sessions}/
                  {operations.progress.open_sessions} sessions
                </strong>
                <small>{operations.progress.indexed_chunks} chunks</small>
              </div>
              {(operations.progress.model_id || operations.progress.table_name) && (
                <div className="search-detail-row">
                  <span>Model/index</span>
                  <strong>{operations.progress.model_id ?? "lexical"}</strong>
                  <small>
                    {operations.progress.vector_dimension
                      ? `${operations.progress.vector_dimension} dims`
                      : "no vector index"}
                    {operations.progress.table_name
                      ? `, ${operations.progress.table_name}`
                      : ""}
                  </small>
                </div>
              )}
              {operations.benchmark && (
                <div className="search-detail-row">
                  <span>Benchmark</span>
                  <strong>{operations.benchmark.passed ? "passed" : "failed"}</strong>
                  <small>
                    p95 {Math.round(operations.benchmark.query_p95_ms)}ms,
                    {" "}
                    {Math.round(operations.benchmark.peak_memory_mb)}MB
                  </small>
                </div>
              )}
              {operations.recent_errors.length > 0 && (
                <div className="search-detail-row vertical">
                  <span>Recent errors</span>
                  {operations.recent_errors.map((message) => (
                    <small key={message}>{message}</small>
                  ))}
                </div>
              )}
              <div className="search-detail-row vertical">
                <span>Local recovery</span>
                <small>
                  Run the suggested command in the Codi project shell. Web UI
                  recovery controls are intentionally read-only in this phase.
                </small>
                {operations.recovery_commands.map((item) => (
                  <code key={item.command}>{item.command}</code>
                ))}
              </div>
            </>
          ) : (
            <div className="search-detail-row vertical">
              <span>Search status</span>
              <small>
                Start a search to see session matches. Indexing status is shown
                here while Codi catches up.
              </small>
            </div>
          )}
        </div>
      )}

      <div className="session-search-filters" aria-label="Search filters">
        <div className="search-filter-row">
          <Filter size={12} aria-hidden="true" />
          {runtimeOptions.map((option) => (
            <button
              type="button"
              key={option.value}
              className={`search-filter${
                runtime === option.value ? " active" : ""
              }`}
              onClick={() => setRuntime(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className="search-filter-row">
          {roleOptions.map((option) => (
            <button
              type="button"
              key={option.value}
              className={`search-filter${role === option.value ? " active" : ""}`}
              onClick={() => setRole(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
        <div className="search-filter-row">
          <button
            type="button"
            className={`search-filter${pinned ? " active" : ""}`}
            onClick={() => setPinned((current) => !current)}
          >
            <Pin size={12} />
            Pinned
          </button>
          {recentOptions.map((option) => (
            <button
              type="button"
              key={option.value}
              className={`search-filter${
                recent === option.value ? " active" : ""
              }`}
              onClick={() => setRecent(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {active && (
        <div className="search-results" aria-live="polite">
          {panel ? (
            <div className={`search-state-panel ${panel.tone}`}>
              {panel.tone === "danger" && <AlertTriangle size={ICON} />}
              {panel.tone === "loading" && (
                <Loader2 size={ICON} className="activity-spinner" />
              )}
              <div>
                <div className="search-state-title">{panel.title}</div>
                {panel.body && <div className="search-state-body">{panel.body}</div>}
              </div>
            </div>
          ) : (
            <>
              {showLexicalNotice && (
                <div className="search-state-panel warn compact">
                  <AlertTriangle size={ICON} />
                  <div>
                    <div className="search-state-title">Degraded</div>
                    <div className="search-state-body">
                      Semantic search is not ready. Showing lexical results.
                    </div>
                  </div>
                </div>
              )}
              {response?.results.map((result) => {
                const session = sessionById.get(result.routing.window_id);
                const title =
                  result.routing.name ||
                  session?.name ||
                  result.routing.window_id;
                return (
                  <div
                    className="search-result-group"
                    key={result.routing.window_id}
                  >
                    <button
                      type="button"
                      className="search-result-session"
                      onClick={() => onOpenResult(result.routing.window_id)}
                    >
                      <div className="search-result-title">
                        {result.routing.pinned && <Pin size={12} />}
                        <span>{title}</span>
                      </div>
                      <div className="search-result-meta">
                        <Brain
                          size={12}
                          className={`runtime-icon runtime-icon-${result.routing.runtime}`}
                        />
                        <span>{result.routing.runtime}</span>
                        <span>{cwdBase(result.routing.cwd)}</span>
                        <span>{result.hit_count} hits</span>
                        {session?.last_activity && (
                          <span>
                            <Clock3 size={11} />
                            {formatRelative(session.last_activity)}
                          </span>
                        )}
                      </div>
                    </button>
                    <div className="search-result-hits">
                      {result.hits.map((hit) => {
                        const labels =
                          showLexicalNotice &&
                          !hit.match_labels.some((label) =>
                            label.toLowerCase().startsWith("lexical"),
                          )
                            ? ["Lexical", ...hit.match_labels]
                            : hit.match_labels;
                        return (
                          <button
                            type="button"
                            key={`${hit.source_order}:${hit.identity.chunk_index}`}
                            className="search-result-hit"
                            onClick={() => openHit(result, hit)}
                          >
                            <div className="search-hit-meta">
                              <span>{hitLabel(hit)}</span>
                              {hit.timestamp && <span>{hit.timestamp}</span>}
                            </div>
                            <div className="search-hit-snippet">
                              {renderSnippet(hit.snippet, hit.highlights)}
                            </div>
                            {labels.length > 0 && (
                              <div className="search-hit-labels">
                                {labels.map((label) => (
                                  <span key={label}>{label}</span>
                                ))}
                              </div>
                            )}
                          </button>
                        );
                      })}
                    </div>
                  </div>
                );
              })}
            </>
          )}
        </div>
      )}
    </div>
  );
}
