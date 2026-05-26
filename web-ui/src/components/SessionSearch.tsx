import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  Brain,
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
  status: SearchStatusResponse | null;
  // False when the backend feature flag is off; we keep the input visible
  // (still useful for triggering result panels) but hide filter affordances.
  searchEnabled: boolean;
  onStatusUpdate: (status: SearchStatusResponse) => void;
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
  status,
  searchEnabled,
  onStatusUpdate,
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
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const filtersRef = useRef<HTMLDivElement | null>(null);
  const requestSeq = useRef(0);

  const filtersActive =
    runtime !== "all" || role !== "all" || recent !== "any" || pinned;

  useEffect(() => {
    if (!filtersOpen) return;
    const onDocClick = (e: MouseEvent) => {
      const el = filtersRef.current;
      if (el && !el.contains(e.target as Node)) setFiltersOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFiltersOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [filtersOpen]);

  const resetFilters = () => {
    setRuntime("all");
    setRole("all");
    setPinned(false);
    setRecent("any");
  };

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
        onStatusUpdate(next.status);
      })
      .catch((err: Error) => {
        if (seq !== requestSeq.current) return;
        setResponse(null);
        setError(err.message);
      })
      .finally(() => {
        if (seq === requestSeq.current) setLoading(false);
      });
  }, [debouncedQuery, pinned, recent, role, runtime, onStatusUpdate]);

  const sessionById = useMemo(
    () => new Map(sessions.map((session) => [session.window_id, session])),
    [sessions],
  );

  const panel = statusPanel(active, loading, error, response, status);
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
      <div className="session-search-bar">
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
        {searchEnabled && (
        <div
          className={`search-filters-anchor${filtersOpen ? " open" : ""}`}
          ref={filtersRef}
        >
          <button
            type="button"
            className={`search-filters-trigger${filtersActive ? " active" : ""}${
              filtersOpen ? " open" : ""
            }`}
            aria-expanded={filtersOpen}
            aria-haspopup="true"
            aria-label={
              filtersActive ? "Filters (active)" : "Filters"
            }
            title={filtersActive ? "Filters active" : "Filters"}
            onClick={() => setFiltersOpen((current) => !current)}
          >
            <Filter size={14} />
            {filtersActive && (
              <span className="search-filters-badge" aria-hidden="true" />
            )}
          </button>
          {filtersOpen && (
            <div
              className="search-filters-popover"
              role="dialog"
              aria-label="Search filters"
            >
              <div className="search-filters-popover-header">
                <span>Filters</span>
                {filtersActive && (
                  <button
                    type="button"
                    className="search-filters-reset"
                    onClick={resetFilters}
                  >
                    Reset
                  </button>
                )}
              </div>
              <div className="search-filter-group">
                <div className="search-filter-group-label">Runtime</div>
                <div className="search-filter-row">
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
              </div>
              <div className="search-filter-group">
                <div className="search-filter-group-label">Role</div>
                <div className="search-filter-row">
                  {roleOptions.map((option) => (
                    <button
                      type="button"
                      key={option.value}
                      className={`search-filter${
                        role === option.value ? " active" : ""
                      }`}
                      onClick={() => setRole(option.value)}
                    >
                      {option.label}
                    </button>
                  ))}
                </div>
              </div>
              <div className="search-filter-group">
                <div className="search-filter-group-label">Recent</div>
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
            </div>
          )}
        </div>
        )}
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
