// Full-width dashboard across every session: what's running, what's blocked
// waiting on you, what finished while you were away. Reads the server-side
// status the backend ships on /api/sessions and live `session_status` events.
// Blocked cards answer the pending prompt inline; click any card to open it.
import { useEffect, useMemo, useState } from "react";
import { X } from "lucide-react";
import { api, SessionStatus, SessionSummary } from "../api";
import { RuntimeIcon } from "./Sidebar";

type CardStatus = SessionStatus | "dormant";

interface PromptInfo {
  ui_name: string;
  options: { label: string }[];
  current_index: number;
}

type PromptMap = Record<string, PromptInfo>;

function statusOf(s: SessionSummary): SessionStatus {
  return s.status ?? "idle";
}

function cardStatus(s: SessionSummary): CardStatus {
  return s.dormant ? "dormant" : statusOf(s);
}

// Coarse "N minutes ago" label. Re-rendered on the component's 30s ticker so a
// "running · 4m" chip keeps creeping up without a per-card timer.
function relTime(since: number | null | undefined): string {
  if (!since) return "";
  const secs = Math.max(0, Date.now() / 1000 - since);
  const mins = Math.floor(secs / 60);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h`;
  return `${Math.floor(hrs / 24)}d`;
}

interface Group {
  key: CardStatus;
  label: string;
  sessions: SessionSummary[];
}

// Groups in attention-priority order: blocked first (waiting on you), then
// running, finished-unread, idle, and dormant last.
function buildGroups(sessions: SessionSummary[]): Group[] {
  const buckets: Record<CardStatus, SessionSummary[]> = {
    blocked: [],
    running: [],
    done: [],
    idle: [],
    dormant: [],
  };
  for (const s of sessions) buckets[cardStatus(s)].push(s);

  const bySinceAsc = (a: SessionSummary, b: SessionSummary) =>
    (a.status_since ?? 0) - (b.status_since ?? 0);
  const bySinceDesc = (a: SessionSummary, b: SessionSummary) =>
    (b.status_since ?? 0) - (a.status_since ?? 0);
  const byActivityDesc = (a: SessionSummary, b: SessionSummary) =>
    (b.last_activity ?? 0) - (a.last_activity ?? 0);

  // Longest-waiting / longest-running float to the top of their group.
  buckets.blocked.sort(bySinceAsc);
  buckets.running.sort(bySinceAsc);
  buckets.done.sort(bySinceDesc);
  buckets.idle.sort(byActivityDesc);
  buckets.dormant.sort(byActivityDesc);

  const labels: Record<CardStatus, string> = {
    blocked: "Needs you",
    running: "Running",
    done: "Finished",
    idle: "Idle",
    dormant: "Dormant",
  };
  const order: CardStatus[] = ["blocked", "running", "done", "idle", "dormant"];
  return order
    .map((key) => ({ key, label: labels[key], sessions: buckets[key] }))
    .filter((g) => g.sessions.length > 0);
}

function basename(path: string): string {
  const parts = path.split("/").filter(Boolean);
  return parts.length ? parts[parts.length - 1] : path;
}

function SessionCard({
  session,
  active,
  prompt,
  onOpen,
  onToast,
}: {
  session: SessionSummary;
  active: boolean;
  prompt: PromptInfo | undefined;
  onOpen: (windowId: string) => void;
  onToast: (text: string, kind?: "info" | "error") => void;
}) {
  const status = cardStatus(session);
  const rel = relTime(session.status_since);
  const wid = session.window_id;
  // Disable a card's actions briefly after a click so a double-tap can't fire
  // two choices / acks against the same prompt.
  const [pending, setPending] = useState(false);

  const run = async (fn: () => Promise<unknown>, errorMsg: string) => {
    if (pending) return;
    setPending(true);
    try {
      await fn();
    } catch {
      onToast(errorMsg, "error");
    } finally {
      setPending(false);
    }
  };

  const stop = (e: React.MouseEvent) => e.stopPropagation();

  return (
    <div
      className={`mc-card mc-card-${status}${active ? " active" : ""}`}
      role="button"
      tabIndex={0}
      onClick={() => onOpen(wid)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen(wid);
        }
      }}
    >
      <div className="mc-card-head">
        <RuntimeIcon runtime={session.runtime} size={14} />
        <span className="mc-card-name">
          {session.name || session.tmux_name || "session"}
        </span>
        <span className={`mc-chip mc-chip-${status}`}>
          {status}
          {rel ? ` · ${rel}` : ""}
        </span>
      </div>
      {session.cwd ? (
        <div className="mc-card-cwd" title={session.cwd}>
          {basename(session.cwd)}
        </div>
      ) : null}
      {status === "blocked" && session.prompt_summary ? (
        <div className="mc-card-prompt">{session.prompt_summary}</div>
      ) : null}

      {status === "blocked" && prompt && prompt.options.length > 0 ? (
        <div className="mc-card-actions" onClick={stop}>
          {prompt.options.map((opt, idx) => (
            <button
              key={idx}
              type="button"
              className="mc-action"
              disabled={pending}
              onClick={() =>
                run(
                  () => api.chooseOption(wid, idx, prompt.options.length),
                  "Failed to send choice",
                )
              }
            >
              {opt.label}
            </button>
          ))}
        </div>
      ) : null}

      {status === "running" ? (
        <div className="mc-card-actions" onClick={stop}>
          <button
            type="button"
            className="mc-action"
            disabled={pending}
            onClick={() =>
              run(() => api.sendKey(wid, "Escape"), "Failed to interrupt")
            }
          >
            Interrupt
          </button>
        </div>
      ) : null}

      {status === "done" ? (
        <div className="mc-card-actions" onClick={stop}>
          <button
            type="button"
            className="mc-action"
            disabled={pending}
            onClick={() =>
              run(() => api.ackSession(wid), "Failed to mark read")
            }
          >
            Mark read
          </button>
        </div>
      ) : null}
    </div>
  );
}

export function MissionControl({
  sessions,
  activeId,
  prompts,
  onOpen,
  onClose,
  onToast,
}: {
  sessions: SessionSummary[];
  activeId: string | null;
  prompts: PromptMap;
  onOpen: (windowId: string) => void;
  onClose: () => void;
  onToast: (text: string, kind?: "info" | "error") => void;
}) {
  // Tick every 30s so relative-time chips stay roughly current even when no
  // events arrive (an idle dashboard shouldn't freeze its clocks).
  const [, setTick] = useState(0);
  useEffect(() => {
    const id = window.setInterval(() => setTick((t) => t + 1), 30000);
    return () => window.clearInterval(id);
  }, []);

  const groups = useMemo(() => buildGroups(sessions), [sessions]);
  const attention = useMemo(
    () => sessions.filter((s) => cardStatus(s) === "blocked").length,
    [sessions],
  );

  return (
    <main className="chat-area mission-control">
      <div className="chat-header">
        <div className="chat-title">
          <div className="name">Mission Control</div>
          <div className="mc-summary">
            {sessions.length} session{sessions.length === 1 ? "" : "s"}
            {attention > 0 ? ` · ${attention} need you` : ""}
          </div>
        </div>
        <button
          type="button"
          className="icon-button"
          onClick={onClose}
          title="Back to chat"
          aria-label="Back to chat"
        >
          <X size={16} />
        </button>
      </div>
      <div className="mc-body">
        {groups.length === 0 ? (
          <div className="empty-state">
            <h2>No sessions</h2>
            <p>Create one to see it here.</p>
          </div>
        ) : (
          groups.map((group) => (
            <section className="mc-group" key={group.key}>
              <h3 className="mc-group-title">
                {group.label}
                <span className="mc-group-count">{group.sessions.length}</span>
              </h3>
              <div className="mc-grid">
                {group.sessions.map((s) => (
                  <SessionCard
                    key={s.window_id}
                    session={s}
                    active={s.window_id === activeId}
                    prompt={prompts[s.window_id]}
                    onOpen={onOpen}
                    onToast={onToast}
                  />
                ))}
              </div>
            </section>
          ))
        )}
      </div>
    </main>
  );
}
