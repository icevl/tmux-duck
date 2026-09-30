import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Brain,
  GitPullRequest,
  GripVertical,
  Loader2,
  Moon,
  MoreVertical,
  Pencil,
  Pin,
  PinOff,
  Plus,
  Trash2,
  TriangleAlert,
  X,
} from "lucide-react";
import {
  AgentUsageSnapshot,
  api,
  SearchStatusResponse,
  SessionSummary,
  WsEvent,
} from "../api";
import { formatModel } from "../models";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { DuckLogo } from "./DuckLogo";
import { UserMenu } from "./UserMenu";
import { SearchStatusFooter } from "./SearchStatusFooter";
import { SessionSearch, type SearchHitTarget } from "./SessionSearch";

const META_ICON = 12;

export function RuntimeIcon({
  runtime,
  size = META_ICON,
}: {
  runtime: string;
  size?: number;
}) {
  return (
    <Brain
      size={size}
      className={`runtime-icon runtime-icon-${runtime}`}
      aria-label={runtime}
    />
  );
}

interface Props {
  sessions: SessionSummary[];
  // false → first /api/sessions response not yet in. Renders a spinner
  // in the list instead of the "No sessions yet" empty state, otherwise
  // we flash an empty list every time the page reloads.
  sessionsLoaded: boolean;
  activeId: string | null;
  busyIds: Set<string>;
  doneIds: Set<string>;
  // Mission Control toggle + count of sessions waiting on the user.
  missionActive: boolean;
  attentionCount: number;
  onToggleMission: () => void;
  onSelect: (id: string) => void;
  onNew: () => void;
  // Connectors dialog stays wired, but its footer button is hidden for now.
  onOpenConnectors?: () => void;
  onOpenAccounts: () => void;
  // Account namespaces ("" = Main); the list shows only `namespace`'s sessions.
  namespaces: SidebarNamespace[];
  namespace: string;
  onNamespaceChange: (id: string) => void;
  // An account with open sessions is signed out.
  accountsNeedSignIn: boolean;
  onLogout: () => void;
  onClose: () => void;
  onRename: (session: SessionSummary) => void;
  onPin: (session: SessionSummary, pinned: boolean) => void;
  onDelete: (session: SessionSummary) => void;
  onReorder: (windowIds: string[]) => void | Promise<void>;
  onOpenSearchHit?: (target: SearchHitTarget) => void;
  subscribeWs: (listener: (e: WsEvent) => void) => () => void;
  notificationsSupported: boolean;
  notificationsEnabled: boolean;
  notificationPermission: NotificationPermission | "unsupported";
  onToggleNotifications: () => void;
}

function sessionSortValue(session: SessionSummary): number | null {
  const order = session.sort_order;
  return typeof order === "number" && Number.isInteger(order) && order >= 0
    ? order
    : null;
}

function compareSessions(a: SessionSummary, b: SessionSummary): number {
  if (a.pinned !== b.pinned) return a.pinned ? -1 : 1;
  const aOrder = sessionSortValue(a);
  const bOrder = sessionSortValue(b);
  if (aOrder !== null && bOrder !== null && aOrder !== bOrder) {
    return aOrder - bOrder;
  }
  if (aOrder !== null && bOrder === null) return -1;
  if (aOrder === null && bOrder !== null) return 1;
  const aTs = a.last_activity ?? 0;
  const bTs = b.last_activity ?? 0;
  if (aTs !== bTs) return bTs - aTs;
  return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
}

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 10_000) return `${Math.round(n / 1000)}k`;
  if (n >= 1_000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
}

function fmtReset(ts: number | null): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString([], {
    weekday: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export interface SidebarNamespace {
  id: string;
  label: string;
  signedOut: boolean;
  needsAttention: boolean;
}

const PERMISSION_MODE_LABELS: Record<string, string> = {
  plan: "plan",
  acceptEdits: "auto-edit",
  bypassPermissions: "bypass",
  auto: "auto",
};

// The auto title is generated once from the first message and goes stale, so
// prefer Claude's recap of the session, then the latest request.
function sessionSubtitle(s: SessionSummary): string | null {
  const text = s.recap || s.last_prompt || (s.title !== s.name ? s.title : null);
  return text ? text.replace(/\s+/g, " ").trim() : null;
}

function permissionModeLabel(mode: string | null | undefined): string | null {
  return mode ? (PERMISSION_MODE_LABELS[mode] ?? null) : null;
}

// The badge next to the session name: the active model, falling back to the
// permission mode until the transcript names a model. The rest goes into the
// tooltip.
function sessionBadge(
  s: SessionSummary,
): { label: string; title: string } | null {
  const model = formatModel(s.model);
  const mode = permissionModeLabel(s.permission_mode);
  const details = [
    s.model ? `Model: ${s.model}` : null,
    s.effort ? `Effort: ${s.effort}` : null,
    s.permission_mode ? `Permission mode: ${s.permission_mode}` : null,
  ].filter(Boolean);
  const label = model ?? mode;
  return label ? { label, title: details.join(" · ") } : null;
}

function UsageRow({
  agent,
  percent,
  text,
  title,
}: {
  agent: string;
  percent: number | null;
  text: string;
  title: string;
}) {
  return (
    <div className="flex items-center gap-3" title={title}>
      <span className="w-12 shrink-0 font-medium text-foreground/80">{agent}</span>
      {percent !== null && (
        <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
          <div
            className={cn(
              "h-full rounded-full transition-[width]",
              percent >= 80 ? "bg-destructive" : "bg-primary",
            )}
            style={{ width: `${Math.min(100, percent)}%` }}
          />
        </div>
      )}
      <span
        className={cn(
          "shrink-0 text-muted-foreground tabular-nums",
          percent === null && "flex-1 text-left",
        )}
      >
        {text}
      </span>
    </div>
  );
}

export function Sidebar({
  sessions,
  sessionsLoaded,
  activeId,
  busyIds,
  doneIds,
  missionActive,
  attentionCount,
  onToggleMission,
  onSelect,
  onNew,
  onOpenAccounts,
  namespaces,
  namespace,
  onNamespaceChange,
  accountsNeedSignIn,
  onLogout,
  onClose,
  onRename,
  onPin,
  onDelete,
  onReorder,
  onOpenSearchHit,
  subscribeWs,
  notificationsSupported,
  notificationsEnabled,
  notificationPermission,
  onToggleNotifications,
}: Props) {
  // Pinned first; manual order wins within each group, with activity/name as
  // fallback for sessions that predate persisted ordering.
  const ordered = useMemo(
    () => [...sessions].sort(compareSessions),
    [sessions],
  );
  const orderedById = useMemo(
    () => new Map(ordered.map((session) => [session.window_id, session])),
    [ordered],
  );

  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dragOverId, setDragOverId] = useState<string | null>(null);
  const [searchActive, setSearchActive] = useState(false);
  const [searchStatus, setSearchStatus] = useState<SearchStatusResponse | null>(
    null,
  );
  // null = not yet known (initial fetch in flight); true/false = backend
  // CODEXBOT_SEARCH_ENABLED.
  const [searchEnabled, setSearchEnabled] = useState<boolean | null>(null);
  // Per-agent usage counters (Codex rate limits, Claude token totals). Initial
  // snapshot via REST; live updates via `agent_usage` events (server polls
  // local files every ~2.5 min — no provider API calls involved).
  const [usage, setUsage] = useState<AgentUsageSnapshot | null>(null);
  // Touch screens have no hover: keep the row actions visible there.
  const isTouch = useMemo(
    () => window.matchMedia("(hover: none)").matches,
    [],
  );

  useEffect(() => {
    let cancelled = false;
    api
      .getUsage()
      .then((u) => {
        if (!cancelled) setUsage(u);
      })
      .catch(() => {
        // Older backend without /api/usage — the block simply doesn't render.
      });
    const unsub = subscribeWs((event) => {
      if (event.type === "agent_usage") {
        setUsage({ codex: event.codex, claude: event.claude });
      }
    });
    return () => {
      cancelled = true;
      unsub();
    };
  }, [subscribeWs]);

  const handleSearchActiveChange = useCallback((active: boolean) => {
    setSearchActive(active);
  }, []);

  const handleSearchStatusUpdate = useCallback((next: SearchStatusResponse) => {
    setSearchStatus(next);
  }, []);

  useEffect(() => {
    let cancelled = false;
    api
      .getSearchStatus()
      .then((next) => {
        if (cancelled) return;
        if (next.enabled === false) {
          setSearchEnabled(false);
          setSearchStatus(null);
        } else {
          setSearchEnabled(true);
          setSearchStatus(next);
        }
      })
      .catch(() => {
        // Footer falls back to "search idle" when nothing has landed yet.
      });
    const unsub = subscribeWs((event) => {
      if (event.type === "search_status") {
        const { type: _type, ts: _ts, seq: _seq, ...rest } = event;
        setSearchEnabled(true);
        setSearchStatus(rest as SearchStatusResponse);
      }
    });
    return () => {
      cancelled = true;
      unsub();
    };
  }, [subscribeWs]);

  const notificationTitle = !notificationsSupported
    ? "Browser notifications are unavailable"
    : notificationsEnabled
    ? "Disable browser notifications"
    : notificationPermission === "denied"
    ? "Notifications are blocked in this browser"
    : "Enable browser notifications";

  const moveSession = (
    sourceId: string,
    targetId: string,
    placement: "before" | "after",
  ) => {
    if (sourceId === targetId) return;
    const source = orderedById.get(sourceId);
    const target = orderedById.get(targetId);
    if (!source || !target || source.pinned !== target.pinned) return;

    const next = [...ordered];
    const from = next.findIndex((session) => session.window_id === sourceId);
    if (from < 0) return;
    const [moved] = next.splice(from, 1);
    let to = next.findIndex((session) => session.window_id === targetId);
    if (to < 0) return;
    if (placement === "after") to += 1;
    next.splice(to, 0, moved);
    void onReorder(next.map((session) => session.window_id));
  };

  return (
    <aside className="sidebar flex flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground">
      <div className="flex h-15 shrink-0 items-center justify-between gap-2 px-4">
        <div className="flex items-center gap-2 text-[15px] font-semibold tracking-tight">
          <DuckLogo width={28} height={28} className="text-warning" />
          <span data-slot="brand">TmuxDuck</span>
        </div>
        <div className="flex items-center gap-2">
          <UserMenu
            missionActive={missionActive}
            attentionCount={attentionCount}
            onToggleMission={onToggleMission}
            onOpenAccounts={onOpenAccounts}
            accountsNeedSignIn={accountsNeedSignIn}
            onLogout={onLogout}
            notificationsSupported={notificationsSupported}
            notificationsEnabled={notificationsEnabled}
            notificationTitle={notificationTitle}
            onToggleNotifications={onToggleNotifications}
          />
          <Button
            variant="ghost"
            size="icon"
            className="sidebar-close hidden max-[760px]:inline-flex"
            onClick={onClose}
            title="Close menu"
            aria-label="Close menu"
          >
            <X />
          </Button>
        </div>
      </div>
      {namespaces.length > 1 && (
        <div
          className="mx-3 mb-2 flex gap-1 rounded-lg bg-secondary p-1"
          role="tablist"
          aria-label="Account"
        >
          {namespaces.map((n) => {
            const active = n.id === namespace;
            return (
              <button
                key={n.id || "main"}
                type="button"
                role="tab"
                data-slot="tab"
                aria-selected={active}
                onClick={() => onNamespaceChange(n.id)}
                title={n.signedOut ? `${n.label} — signed out` : n.label}
                className={cn(
                  "relative flex-1 truncate rounded-md px-2 py-1 text-xs font-medium text-muted-foreground transition",
                  "hover:text-foreground",
                  active && "bg-background text-foreground shadow-sm",
                  n.signedOut && "text-destructive",
                )}
              >
                {n.label}
                {!active && n.needsAttention && (
                  <span
                    className="absolute top-1 right-1 size-1.5 rounded-full bg-warning"
                    aria-label="Needs attention"
                  />
                )}
              </button>
            );
          })}
        </div>
      )}
      <div className="px-3 pb-2">
        <Button
          variant="outline"
          className="w-full justify-center gap-2 bg-background/60 dark:bg-input/20"
          onClick={onNew}
        >
          <Plus />
          New session
        </Button>
      </div>
      {searchEnabled !== false && (
        <SessionSearch
          sessions={sessions}
          status={searchStatus}
          searchEnabled={searchEnabled === true}
          onStatusUpdate={handleSearchStatusUpdate}
          onOpenResult={onSelect}
          onOpenHit={onOpenSearchHit}
          onHasActiveQueryChange={handleSearchActiveChange}
        />
      )}
      <div
        className="session-list flex min-h-0 flex-1 flex-col gap-0.5 overflow-y-auto px-2 py-1"
        style={searchActive ? { display: "none" } : undefined}
      >
        {ordered.length === 0 ? (
          sessionsLoaded ? (
            <div className="px-3 py-8 text-center text-sm text-muted-foreground">
              No sessions yet.
            </div>
          ) : (
            <div className="flex flex-col gap-1 p-1" role="status" aria-label="Loading sessions">
              {Array.from({ length: 4 }).map((_, i) => (
                <div key={i} className="flex flex-col gap-2 rounded-lg px-3 py-2.5">
                  <div className="h-3 w-2/3 animate-pulse rounded bg-muted" />
                  <div className="h-2.5 w-5/6 animate-pulse rounded bg-muted/70" />
                </div>
              ))}
            </div>
          )
        ) : (
          ordered.map((s) => {
            const active = s.window_id === activeId;
            const isBusy = busyIds.has(s.window_id);
            const isDone = doneIds.has(s.window_id);
            const badge = sessionBadge(s);
            const subtitle = sessionSubtitle(s);
            return (
              <div
                key={s.window_id}
                role="button"
                tabIndex={0}
                aria-current={active ? "true" : undefined}
                className={cn(
                  "group relative flex cursor-pointer items-start gap-1 rounded-lg py-2 pr-1.5 pl-1 transition-colors max-[760px]:pl-3",
                  "hover:bg-sidebar-accent/70 focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
                  active && "bg-sidebar-accent hover:bg-sidebar-accent",
                  s.dormant && "opacity-60 hover:opacity-100",
                  draggingId === s.window_id && "opacity-40",
                  dragOverId === s.window_id && "ring-1 ring-brand/60",
                )}
                draggable={!s.dormant}
                onDragStart={(e) => {
                  e.dataTransfer.effectAllowed = "move";
                  e.dataTransfer.setData("text/plain", s.window_id);
                  setDraggingId(s.window_id);
                  setDragOverId(null);
                }}
                onDragOver={(e) => {
                  const dragging = draggingId ? orderedById.get(draggingId) : null;
                  if (!dragging || dragging.pinned !== s.pinned) return;
                  e.preventDefault();
                  e.dataTransfer.dropEffect = "move";
                  setDragOverId(s.window_id);
                }}
                onDragLeave={() => {
                  setDragOverId((current) => (current === s.window_id ? null : current));
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  const sourceId = draggingId || e.dataTransfer.getData("text/plain");
                  const rect = e.currentTarget.getBoundingClientRect();
                  const placement =
                    e.clientY > rect.top + rect.height / 2 ? "after" : "before";
                  setDraggingId(null);
                  setDragOverId(null);
                  if (sourceId) moveSession(sourceId, s.window_id, placement);
                }}
                onDragEnd={() => {
                  setDraggingId(null);
                  setDragOverId(null);
                }}
                onKeyDown={(e) => {
                  if (e.target !== e.currentTarget) return;
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    e.currentTarget.click();
                  }
                }}
                onClick={async () => {
                  if (s.dormant) {
                    try {
                      const res = await api.resumeDormantSession(s.window_id);
                      onSelect(res.window_id);
                    } catch (err) {
                      console.error("resume dormant session failed:", err);
                    }
                    return;
                  }
                  onSelect(s.window_id);
                }}
              >
                {active && (
                  <span className="absolute top-2 bottom-2 left-0 w-0.5 rounded-full bg-brand" />
                )}
                <span
                  className={cn(
                    "mt-0.5 flex w-4 shrink-0 justify-center text-muted-foreground/60",
                    !s.dormant &&
                      "cursor-grab opacity-0 group-hover:opacity-100 active:cursor-grabbing max-[760px]:hidden",
                  )}
                  title={s.dormant ? "Dormant — click to resume" : "Drag to reorder"}
                  aria-hidden="true"
                >
                  {s.dormant ? <Moon size={13} /> : <GripVertical size={13} />}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex min-w-0 items-center gap-1.5">
                    {s.pinned && (
                      <Pin size={12} className="shrink-0 text-muted-foreground" aria-label="Pinned" />
                    )}
                    {isBusy ? (
                      <Loader2
                        size={12}
                        className="shrink-0 animate-spin text-brand"
                        aria-label="Agent is working"
                      />
                    ) : isDone ? (
                      <span
                        className="size-2 shrink-0 rounded-full bg-success"
                        title="Agent finished — click to open"
                        aria-label="Finished"
                      />
                    ) : null}
                    <span
                      className={cn(
                        "truncate text-sm font-medium",
                        active ? "text-foreground" : "text-foreground/90",
                      )}
                    >
                      {s.name}
                    </span>
                    {s.profile_logged_in === false && (
                      <span
                        className="shrink-0 text-destructive"
                        title="Account signed out — open Accounts to sign in"
                      >
                        <TriangleAlert size={12} aria-label="Account signed out" />
                      </span>
                    )}
                    {badge && (
                      <Badge
                        variant="outline"
                        title={badge.title}
                        className={cn(
                          "h-[18px] shrink-0 rounded-md px-1.5 text-[10.5px] font-medium text-muted-foreground",
                          s.permission_mode === "plan" && "border-brand/50 text-brand",
                        )}
                      >
                        {badge.label}
                      </Badge>
                    )}
                    {s.pr_url && (
                      <a
                        data-slot="link"
                        className="shrink-0 text-muted-foreground hover:text-foreground"
                        href={s.pr_url}
                        target="_blank"
                        rel="noreferrer"
                        title={s.pr_number ? `PR #${s.pr_number}` : "Pull request"}
                        onClick={(e) => e.stopPropagation()}
                      >
                        <GitPullRequest size={12} />
                      </a>
                    )}
                  </div>
                  {subtitle && (
                    <div
                      className="mt-0.5 truncate text-xs text-muted-foreground"
                      title={subtitle}
                    >
                      {subtitle}
                    </div>
                  )}
                </div>
                <DropdownMenu modal={false}>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      className={cn(
                        "size-7 shrink-0 text-muted-foreground opacity-0 group-hover:opacity-100 focus-visible:opacity-100 data-[state=open]:opacity-100",
                        (active || isTouch) && "opacity-100",
                      )}
                      title="More actions"
                      aria-label="Session actions"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <MoreVertical />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent
                    align="end"
                    className="w-40"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <DropdownMenuItem onSelect={() => onRename(s)}>
                      <Pencil /> Rename
                    </DropdownMenuItem>
                    <DropdownMenuItem onSelect={() => onPin(s, !s.pinned)}>
                      {s.pinned ? (
                        <>
                          <PinOff /> Unpin
                        </>
                      ) : (
                        <>
                          <Pin /> Pin
                        </>
                      )}
                    </DropdownMenuItem>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem variant="destructive" onSelect={() => onDelete(s)}>
                      <Trash2 /> Delete
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            );
          })
        )}
      </div>
      {searchEnabled !== false && <SearchStatusFooter status={searchStatus} />}
      {(usage?.codex?.primary || usage?.claude) && (
        <div className="flex shrink-0 flex-col gap-1.5 border-t border-sidebar-border px-4 py-3 text-xs">
          {usage?.codex?.primary && (
            <UsageRow
              agent="Codex"
              percent={usage.codex.primary.used_percent}
              text={`${Math.round(usage.codex.primary.used_percent)}% 5h${
                usage.codex.secondary
                  ? ` · ${Math.round(usage.codex.secondary.used_percent)}% wk`
                  : ""
              }`}
              title={`5h window resets ${fmtReset(usage.codex.primary.resets_at)}${
                usage.codex.secondary
                  ? ` · weekly resets ${fmtReset(usage.codex.secondary.resets_at)}`
                  : ""
              }`}
            />
          )}
          {usage?.claude?.limits?.five_hour ? (
            // Official account-wide percentages (matches the console).
            <UsageRow
              agent="Claude"
              percent={usage.claude.limits.five_hour.used_percent}
              text={`${Math.round(usage.claude.limits.five_hour.used_percent)}% 5h${
                usage.claude.limits.seven_day
                  ? ` · ${Math.round(usage.claude.limits.seven_day.used_percent)}% wk`
                  : ""
              }`}
              title={`5h window resets ${fmtReset(usage.claude.limits.five_hour.resets_at)}${
                usage.claude.limits.seven_day
                  ? ` · weekly resets ${fmtReset(usage.claude.limits.seven_day.resets_at)}`
                  : ""
              } · this Mac today: ${fmtTokens(usage.claude.today.input)} in / ${fmtTokens(
                usage.claude.today.output,
              )} out`}
            />
          ) : usage?.claude ? (
            // Fallback: local token counters (this machine only).
            <UsageRow
              agent="Claude"
              percent={null}
              text={`today ${fmtTokens(usage.claude.today.input)} in · ${fmtTokens(
                usage.claude.today.output,
              )} out`}
              title={`This Mac only. Last 5h: ${fmtTokens(
                usage.claude.last_5h.input,
              )} in / ${fmtTokens(usage.claude.last_5h.output)} out`}
            />
          ) : null}
        </div>
      )}
    </aside>
  );
}
