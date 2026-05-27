// Thin wrapper around fetch. All requests carry session cookies via
// `credentials: "include"`. The server returns JSON for /api/* endpoints
// and the proxy in vite.config.ts forwards them to the Python backend in
// dev mode.

export interface SessionSummary {
  window_id: string;
  name: string;
  tmux_name: string;
  cwd: string;
  runtime: "codex" | "claude" | string;
  session_id: string | null;
  pane_command: string | null;
  last_activity: number | null;
  pinned: boolean;
  sort_order: number | null;
  dormant?: boolean;
}

export interface ResumeDormantResponse {
  ok: boolean;
  window_id: string;
  name: string;
  runtime: string;
  cwd: string;
  session_id: string;
}

export interface SessionMessage {
  role: string;
  text: string;
  content_type: string;
  timestamp?: string;
  seq?: number;
  transcript_offset?: number | null;
  transcript_index?: number | null;
  tool_name?: string | null;
  tool_input?: Record<string, unknown> | null;
  tool_use_id?: string | null;
}

export interface SessionMessagesResponse {
  messages: SessionMessage[];
  session_id: string | null;
  has_more: boolean;
  oldest_timestamp?: string | null;
  newest_timestamp?: string | null;
  history_version?: string;
}

export interface RuntimeInfo {
  name: string;
  display_name: string;
  emoji: string;
}

export interface SlashCommandHint {
  command: string;
  description: string;
}

export interface SlashCommandsResponse {
  runtime: string;
  window_id: string | null;
  session_id: string | null;
  commands: SlashCommandHint[];
  source: string;
  updated_at: number | null;
}

export interface SkillHint {
  name: string;
  invocation: string;
  description: string;
}

export interface SkillHintsResponse {
  runtime: string;
  window_id: string | null;
  session_id: string | null;
  skills: SkillHint[];
  source: string;
  updated_at: number | null;
}

export interface DirectoryEntry {
  name: string;
  path: string;
}

export interface DirectoryListing {
  path: string;
  parent: string | null;
  entries: DirectoryEntry[];
}

export interface ResumeSession {
  session_id: string;
  summary: string;
  message_count: number;
}

export type SearchIndexState =
  | "missing"
  | "building"
  | "partial"
  | "ready"
  | "stale"
  | "degraded"
  | "unavailable";

export type SearchResponseOutcome = "ok" | "not_ready" | "unavailable";
export type SearchOutcome = "lexical" | "semantic" | "metadata" | "hybrid";

export interface SearchCounters {
  /** Total chunks discovered by the current backfill before embedding starts.
   * Used together with indexed_chunks for an "X/Y" progress display. */
  total_chunks?: number;
  open_sessions: number;
  indexed_sessions: number;
  indexed_chunks: number;
  queued_items: number;
  failed_items: number;
}

export interface SearchGenerationMetadata {
  schema_version: number;
  generation_id: string;
  created_at: string;
  active: boolean;
}

export interface SearchIndexMetadata {
  schema_version: number;
  generation_id: string;
  model_id: string;
  vector_dimension: number;
  table_name: string;
  created_at: string;
  completed: boolean;
  recent_error: string | null;
}

export interface SearchWorkerHealth {
  /** True while the worker is sleeping between batches because the
   * supervisor saw user activity (tmux pane busy / agent generating). */
  paused?: boolean;
  status: "idle" | "running" | "completed" | "failed" | null;
  current_task: string | null;
  heartbeat_at: string | null;
  heartbeat_age_seconds: number | null;
  stale: boolean;
  stale_after_seconds: number;
  recent_error: string | null;
}

export interface SearchQueueHealth {
  queued_items: number;
  leased_items: number;
  failed_items: number;
  stale_sources: number;
  oldest_queued_at: string | null;
  oldest_queued_age_seconds: number | null;
  lagging: boolean;
  recent_error: string | null;
}

export interface SearchBackfillProgress {
  total_chunks?: number;
  open_sessions: number;
  indexed_sessions: number;
  indexed_chunks: number;
  queued_items: number;
  failed_items: number;
  generation_id: string | null;
  model_id: string | null;
  vector_dimension: number | null;
  table_name: string | null;
}

export interface SearchRecoveryCommand {
  label: string;
  command: string;
  description: string | null;
}

export interface SearchBenchmarkSummary {
  schema_version: number;
  created_at: string;
  ok: boolean;
  provider: "fake" | "local";
  model_id: string;
  vector_dimension: number;
  batch_size: number;
  chunk_max_chars: number;
  chunk_overlap_chars: number;
  document_count: number;
  query_count: number;
  index_elapsed_ms: number;
  query_p50_ms: number;
  query_p95_ms: number;
  peak_memory_mb: number;
  embedding_docs_per_second: number;
  exact_top3: number;
  semantic_top5: number;
  fallback_ok: boolean;
  package_versions: Record<string, string>;
  exact_top3_recall: number;
  semantic_top5_recall: number;
  passed: boolean;
  failures: string[];
  thresholds: Record<string, number>;
}

export interface SearchOperationalStatus {
  worker: SearchWorkerHealth;
  queue: SearchQueueHealth;
  progress: SearchBackfillProgress;
  recent_errors: string[];
  recovery_commands: SearchRecoveryCommand[];
  benchmark: SearchBenchmarkSummary | null;
}

export interface SearchStatusResponse {
  state: SearchIndexState;
  available: boolean;
  scope: "open_sessions";
  reason: string | null;
  counters: SearchCounters | null;
  generation: SearchGenerationMetadata | null;
  index: SearchIndexMetadata | null;
  operations: SearchOperationalStatus | null;
  // True when the backend feature flag (CODEXBOT_SEARCH_ENABLED) is on.
  // When false the rest of the fields are absent and the UI hides the
  // search filter affordance and the index footer entirely.
  enabled?: boolean;
  // True when the supervisor has paused indexing because tmux work is
  // active. UI uses this to show a "deferred" footer instead of
  // misleading degraded/missing/unavailable.
  deferred?: boolean;
}

export interface SearchStatusDisabled {
  enabled: false;
}

export type SearchStatusPayload = SearchStatusResponse | SearchStatusDisabled;

export interface SearchRoutingMetadata {
  window_id: string;
  name: string | null;
  cwd: string;
  runtime: string;
  session_id: string | null;
  status: string | null;
  pinned: boolean;
  sort_order: number | null;
}

export interface SearchRowIdentity {
  runtime: string;
  transcript_source: string;
  transcript_offset: number | null;
  transcript_index: number | null;
  role: string;
  content_type: string;
  tool_use_id: string | null;
  chunk_index: number;
}

export interface TranscriptProvenance {
  runtime: string;
  session_id: string | null;
  transcript_source: string;
  transcript_offset: number | null;
  transcript_index: number | null;
  role: string;
  content_type: string;
  tool_name: string | null;
  tool_use_id: string | null;
  source_event_kind: string;
  timestamp: string | null;
}

export interface SearchHighlight {
  start: number;
  end: number;
  label: string;
}

export interface SearchHit {
  identity: SearchRowIdentity;
  provenance: TranscriptProvenance;
  snippet: string;
  score: number;
  outcomes: SearchOutcome[];
  source_order: number;
  timestamp: string | null;
  highlights: SearchHighlight[];
  match_labels: string[];
}

export interface SearchSessionResult {
  routing: SearchRoutingMetadata;
  hits: SearchHit[];
  hit_count: number;
  score: number | null;
}

export interface SearchRequest {
  query: string;
  limit?: number;
  hits_per_session?: number;
  runtime?: string | null;
  cwd?: string | null;
  role?: string | null;
  content_type?: string | null;
  status?: string | null;
  window_id?: string | null;
  session_id?: string | null;
  pinned?: boolean | null;
  recent_after?: string | null;
  recent_seconds?: number | null;
}

export interface SearchResponse {
  status: SearchStatusResponse;
  query: string;
  results: SearchSessionResult[];
  total_results: number;
  total_sessions: number;
  limit: number;
  hits_per_session: number;
  outcome: SearchResponseOutcome;
}

async function request<T>(
  path: string,
  init: RequestInit & { json?: unknown } = {},
): Promise<T> {
  const { json, headers, ...rest } = init;
  const opts: RequestInit = {
    credentials: "include",
    headers: {
      "Content-Type": json !== undefined ? "application/json" : "application/json",
      Accept: "application/json",
      ...(headers ?? {}),
    },
    ...rest,
  };
  if (json !== undefined) {
    opts.body = JSON.stringify(json);
  }
  const res = await fetch(path, opts);
  if (res.status === 401) {
    const err = new Error("unauthorized");
    (err as Error & { code?: number }).code = 401;
    throw err;
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      if (typeof body?.detail === "string") detail = body.detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (res.status === 204) {
    return undefined as unknown as T;
  }
  const ct = res.headers.get("content-type") ?? "";
  if (ct.includes("application/json")) {
    return (await res.json()) as T;
  }
  return (await res.text()) as unknown as T;
}

export const api = {
  me: () =>
    request<{
      authenticated: boolean;
      enabled: boolean;
      totp_required: boolean;
    }>("/api/me"),
  login: (password: string, totpCode?: string) =>
    request<{ ok: boolean }>("/api/login", {
      method: "POST",
      json: { password, totp_code: totpCode || null },
    }),
  logout: () => request<{ ok: boolean }>("/api/logout", { method: "POST" }),

  listSessions: () =>
    request<{ sessions: SessionSummary[] }>("/api/sessions"),
  getSearchStatus: () => request<SearchStatusResponse>("/api/search/status"),
  searchSessions: (searchRequest: SearchRequest) =>
    request<SearchResponse>("/api/search", {
      method: "POST",
      json: searchRequest,
    }),
  wipeSearchIndex: () =>
    request<{ ok: boolean; killed_pids: number[]; removed: string[] }>(
      "/api/search/wipe",
      { method: "POST" },
    ),
  resumeDormantSession: (windowId: string) =>
    request<ResumeDormantResponse>(
      `/api/sessions/${encodeURIComponent(windowId)}/resume`,
      { method: "POST" },
    ),
  createSession: (body: {
    cwd: string;
    runtime: string;
    resume_session_id?: string | null;
    name?: string | null;
  }) => request<SessionSummary>("/api/sessions", { method: "POST", json: body }),
  killSession: (windowId: string) =>
    request<{ ok: boolean }>(`/api/sessions/${encodeURIComponent(windowId)}`, {
      method: "DELETE",
    }),
  renameSession: (windowId: string, name: string) =>
    request<{ ok: boolean; name: string }>(
      `/api/sessions/${encodeURIComponent(windowId)}`,
      { method: "PATCH", json: { name } },
    ),
  setSessionPinned: (windowId: string, pinned: boolean) =>
    request<{ ok: boolean; pinned: boolean }>(
      `/api/sessions/${encodeURIComponent(windowId)}`,
      { method: "PATCH", json: { pinned } },
    ),
  reorderSessions: (windowIds: string[]) =>
    request<{ ok: boolean }>("/api/sessions/order", {
      method: "PATCH",
      json: { window_ids: windowIds },
    }),
  getMessages: (
    windowId: string,
    opts?: {
      before?: string;
      after?: string;
      before_offset?: number;
      before_index?: number;
      after_offset?: number;
      after_index?: number;
      around_offset?: number;
      around_index?: number;
      limit?: number;
    },
  ) => {
    const params = new URLSearchParams();
    params.set("limit", String(opts?.limit ?? 500));
    if (opts?.before) params.set("before", opts.before);
    if (opts?.after) params.set("after", opts.after);
    if (opts?.before_offset !== undefined) {
      params.set("before_offset", String(opts.before_offset));
    }
    if (opts?.before_index !== undefined) {
      params.set("before_index", String(opts.before_index));
    }
    if (opts?.after_offset !== undefined) {
      params.set("after_offset", String(opts.after_offset));
    }
    if (opts?.after_index !== undefined) {
      params.set("after_index", String(opts.after_index));
    }
    if (opts?.around_offset !== undefined) {
      params.set("around_offset", String(opts.around_offset));
    }
    if (opts?.around_index !== undefined) {
      params.set("around_index", String(opts.around_index));
    }
    return request<SessionMessagesResponse>(
      `/api/sessions/${encodeURIComponent(windowId)}/messages?${params.toString()}`,
    );
  },
  sendText: (windowId: string, text: string, enter = true) =>
    request<{ ok: boolean }>(
      `/api/sessions/${encodeURIComponent(windowId)}/text`,
      { method: "POST", json: { text, enter } },
    ),
  sendKey: (windowId: string, key: string) =>
    request<{ ok: boolean }>(
      `/api/sessions/${encodeURIComponent(windowId)}/keys`,
      { method: "POST", json: { key } },
    ),
  sendCommand: (windowId: string, command: string) =>
    request<{ ok: boolean }>(
      `/api/sessions/${encodeURIComponent(windowId)}/command`,
      { method: "POST", json: { command } },
    ),
  screenshotUrl: (windowId: string) =>
    `/api/sessions/${encodeURIComponent(windowId)}/screenshot.png?t=${Date.now()}`,
  uploadImage: async (
    windowId: string,
    file: File,
  ): Promise<{ ok: boolean; path: string }> => {
    const res = await fetch(
      `/api/sessions/${encodeURIComponent(
        windowId,
      )}/upload?filename=${encodeURIComponent(file.name || "image")}`,
      {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": file.type || "application/octet-stream",
        },
        body: file,
      },
    );
    if (res.status === 401) {
      const err = new Error("unauthorized");
      (err as Error & { code?: number }).code = 401;
      throw err;
    }
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        if (typeof body?.detail === "string") detail = body.detail;
      } catch {
        /* ignore */
      }
      throw new Error(detail);
    }
    return (await res.json()) as { ok: boolean; path: string };
  },

  listRuntimes: () =>
    request<{ runtimes: RuntimeInfo[] }>("/api/runtimes"),
  listSlashCommands: (runtime: string, windowId?: string | null) => {
    const params = new URLSearchParams();
    params.set("runtime", runtime);
    if (windowId) params.set("window_id", windowId);
    return request<SlashCommandsResponse>(
      `/api/slash-commands?${params.toString()}`,
    );
  },
  listSkillHints: (runtime: string, windowId?: string | null) => {
    const params = new URLSearchParams();
    params.set("runtime", runtime);
    if (windowId) params.set("window_id", windowId);
    return request<SkillHintsResponse>(`/api/skill-hints?${params.toString()}`);
  },
  listSkills: (runtime: string) =>
    request<{ skills: string[]; runtime: string }>(
      `/api/skills?runtime=${encodeURIComponent(runtime)}`,
    ),
  listDirectories: (path: string) =>
    request<DirectoryListing>(
      `/api/directories?path=${encodeURIComponent(path)}`,
    ),
  listResumeSessions: (cwd: string) =>
    request<{ sessions: ResumeSession[] }>(
      `/api/resume-sessions?cwd=${encodeURIComponent(cwd)}`,
    ),
  getGitInfo: (windowId: string) =>
    request<{ is_repo: boolean; branch: string | null }>(
      `/api/sessions/${encodeURIComponent(windowId)}/git`,
    ),
  listBranches: (windowId: string) =>
    request<{
      is_repo: boolean;
      current: string | null;
      branches: string[];
    }>(`/api/sessions/${encodeURIComponent(windowId)}/branches`),
  switchBranch: (windowId: string, branch: string) =>
    request<{ ok: boolean; branch: string; stdout: string }>(
      `/api/sessions/${encodeURIComponent(windowId)}/switch-branch`,
      { method: "POST", json: { branch } },
    ),
  getOfficeState: () =>
    request<{
      catalog: Record<string, unknown>;
      layout: { cols: number; rows: number; placements: unknown[] } | null;
    }>("/api/office/state"),
  putOfficeState: (body: {
    catalog: Record<string, unknown>;
    layout: { cols: number; rows: number; placements: unknown[] } | null;
  }) =>
    request<{ ok: boolean; path: string }>("/api/office/state", {
      method: "PUT",
      json: body,
    }),

  getDiff: async (
    windowId: string,
    etag?: string | null,
  ): Promise<
    | {
        status: 304;
        etag: string | null;
        data: null;
      }
    | {
        status: 200;
        etag: string | null;
        data: {
          is_repo: boolean;
          diff: string;
          additions: number;
          deletions: number;
          file_count: number;
          untracked: string[];
        };
      }
  > => {
    const headers: Record<string, string> = { Accept: "application/json" };
    if (etag) headers["If-None-Match"] = etag;
    const res = await fetch(
      `/api/sessions/${encodeURIComponent(windowId)}/diff`,
      { credentials: "include", headers },
    );
    if (res.status === 401) {
      const err = new Error("unauthorized");
      (err as Error & { code?: number }).code = 401;
      throw err;
    }
    const newEtag = res.headers.get("ETag");
    if (res.status === 304) {
      return { status: 304, etag: newEtag, data: null };
    }
    if (!res.ok) throw new Error(res.statusText);
    const data = await res.json();
    return { status: 200, etag: newEtag, data };
  },

  getUpdateStatus: () =>
    request<{
      enabled: boolean;
      current_sha: string | null;
      latest_sha: string | null;
      has_update: boolean;
      dirty: boolean;
      subject: string | null;
    }>("/api/update/status"),

  runUpdate: () =>
    request<{ started: boolean }>("/api/update/run", { method: "POST" }),

  chooseOption: (windowId: string, optionIndex: number, total: number) =>
    request<{ ok: boolean }>(
      `/api/sessions/${encodeURIComponent(windowId)}/choose`,
      { method: "POST", json: { option_index: optionIndex, total } },
    ),

  listSessionFiles: (windowId: string, path = "") =>
    request<{
      path: string;
      entries: { name: string; type: "file" | "dir"; path: string }[];
    }>(
      `/api/sessions/${encodeURIComponent(windowId)}/files?path=${encodeURIComponent(
        path,
      )}`,
    ),

  getSessionFileContent: (windowId: string, path: string) =>
    request<{
      path: string;
      size: number;
      truncated: boolean;
      binary: boolean;
      content: string;
    }>(
      `/api/sessions/${encodeURIComponent(
        windowId,
      )}/files/content?path=${encodeURIComponent(path)}`,
    ),

  saveSessionFileContent: (windowId: string, path: string, content: string) =>
    request<{ path: string; size: number }>(
      `/api/sessions/${encodeURIComponent(windowId)}/files/content`,
      { method: "PUT", json: { path, content } },
    ),

  searchSessionFiles: (windowId: string, q: string) =>
    request<{
      matches: { name: string; type: "file" | "dir"; path: string }[];
      truncated: boolean;
    }>(
      `/api/sessions/${encodeURIComponent(windowId)}/files/search?q=${encodeURIComponent(
        q,
      )}`,
    ),
};

export type WsEvent =
  | { type: "hello"; ts: number }
  | {
      type: "message";
      window_id: string;
      session_id: string;
      role: string;
      text: string;
      content_type: string;
      is_complete: boolean;
      tool_name: string | null;
      tool_input: Record<string, unknown> | null;
      tool_use_id: string | null;
      turn_id: number | null;
      timestamp?: string | null;
      transcript_offset?: number | null;
      transcript_index?: number | null;
      ts: number;
      seq?: number;
    }
  | {
      type: "completion";
      window_id: string;
      session_id: string;
      turn_id: number | null;
      transcript_offset?: number | null;
      transcript_index?: number | null;
      ts: number;
      seq?: number;
    }
  | {
      type: "stream";
      window_id: string;
      session_id: string | null;
      text: string;
      status: string;
      ts: number;
      seq?: number;
    }
  | {
      type: "stream_end";
      window_id: string;
      session_id: string | null;
      ts: number;
      seq?: number;
    }
  | { type: "sessions_changed"; ts: number; seq?: number }
  | {
      type: "slash_commands_changed";
      runtime: string;
      window_id: string;
      session_id: string;
      source: string;
      ts: number;
      seq?: number;
    }
  | {
      type: "skill_hints_changed";
      runtime: string;
      window_id: string;
      session_id: string;
      source: string;
      ts: number;
      seq?: number;
    }
  | {
      type: "update_available";
      current_sha: string;
      latest_sha: string;
      subject: string;
      ts: number;
      seq?: number;
    }
  | {
      type: "interactive_prompt";
      window_id: string;
      runtime: string;
      ui_name: string;
      options: Array<{ label: string }>;
      current_index: number;
      content: string;
      ts: number;
      seq?: number;
    }
  | {
      type: "interactive_prompt_cleared";
      window_id: string;
      ts: number;
      seq?: number;
    }
  | (SearchStatusResponse & { type: "search_status"; ts: number; seq?: number });
