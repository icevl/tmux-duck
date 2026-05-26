import { useEffect, useMemo, useRef, useState } from "react";
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  Filter,
  Folder,
  FolderOpen,
  Loader2,
  Pin,
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
const DEFAULT_HITS_PER_SESSION = 50;

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
  const [collapsedSessions, setCollapsedSessions] = useState<Set<string>>(
    () => new Set(),
  );
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

  // Keep the filter-related identifiers referenced so the build doesn't strip
  // them while the filter button itself is commented out. Re-enabling is a
  // one-block uncomment in JSX below.
  void [
    Filter,
    Pin,
    runtimeOptions,
    roleOptions,
    recentOptions,
    searchEnabled,
    filtersActive,
    resetFilters,
  ];

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
  // The backend marks state="degraded" both for "no vector index" (real
  // lexical-only fallback) and for "vector index exists but the live queue
  // is behind". The second case is misleading to call "Semantic not ready" —
  // semantic IS ready, the queue just hasn't merged the freshest events yet.
  // Only fire the warning when the vector index truly isn't there.
  const showLexicalNotice =
    response?.status.state === "degraded" &&
    response.status.index == null &&
    response.results.length > 0;

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
        {/* Filter button hidden for now — keep the popover logic wired so we
            can flip it back on without re-implementing.
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
        */}
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
                const wid = result.routing.window_id;
                const expanded = !collapsedSessions.has(wid);
                return (
                  <div className="search-tree-group" key={wid}>
                    <button
                      type="button"
                      className="search-tree-row session"
                      onClick={() =>
                        setCollapsedSessions((prev) => {
                          const next = new Set(prev);
                          if (next.has(wid)) next.delete(wid);
                          else next.add(wid);
                          return next;
                        })
                      }
                    >
                      <span className="tree-chevron" aria-hidden="true">
                        {expanded ? (
                          <ChevronDown size={12} />
                        ) : (
                          <ChevronRight size={12} />
                        )}
                      </span>
                      <span className="tree-icon" aria-hidden="true">
                        {expanded ? (
                          <FolderOpen size={14} />
                        ) : (
                          <Folder size={14} />
                        )}
                      </span>
                      <span className="tree-label">{title}</span>
                      <span className="tree-count">{result.hit_count}</span>
                    </button>
                    {expanded &&
                      result.hits.map((hit) => (
                        <button
                          type="button"
                          key={`${hit.source_order}:${hit.identity.chunk_index}`}
                          className="search-tree-row hit"
                          onClick={() => openHit(result, hit)}
                        >
                          <span className="tree-snippet">
                            {renderSnippet(hit.snippet, hit.highlights)}
                          </span>
                        </button>
                      ))}
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
