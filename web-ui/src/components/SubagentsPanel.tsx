import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowDown, ArrowUp, Bot, ChevronLeft, User, X } from "lucide-react";
import { api, SessionMessage, Subagent, WsEvent } from "../api";
import { Markdown } from "./Markdown";

interface Props {
  windowId: string;
  open: boolean;
  onClose: () => void;
  row?: "top" | "bottom";
  onToggleRow?: () => void;
  subscribeWs: (l: (e: WsEvent) => void) => () => void;
}

// Tools whose appearance in the main transcript means a subagent was just
// spawned or finished — a cue to refresh the inventory immediately.
const SPAWN_TOOLS = new Set(["Agent", "Workflow", "Task"]);

function StatusDot({ status }: { status: Subagent["status"] }) {
  return (
    <span
      className={`subagent-dot ${status}`}
      title={status === "running" ? "Running" : "Completed"}
      aria-label={status}
    />
  );
}

function SubagentBubble({ m }: { m: SessionMessage }) {
  const isUser = m.role === "user" && m.content_type !== "tool_result";
  return (
    <div className={`message-line ${isUser ? "user" : "assistant"}`}>
      <div className="message-avatar" aria-hidden="true">
        {isUser ? <User size={16} /> : <Bot size={16} />}
      </div>
      <div className={`bubble ${m.role} ${m.content_type}`.trim()}>
        <div className="meta">
          <span>
            {m.role}
            {m.content_type && m.content_type !== "text"
              ? ` · ${m.content_type}`
              : ""}
          </span>
        </div>
        <Markdown text={m.text} />
      </div>
    </div>
  );
}

export function SubagentsPanel({
  windowId,
  open,
  onClose,
  row,
  onToggleRow,
  subscribeWs,
}: Props) {
  const [subagents, setSubagents] = useState<Subagent[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [messages, setMessages] = useState<SessionMessage[]>([]);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingMsgs, setLoadingMsgs] = useState(false);
  const subagentsRef = useRef<Subagent[]>([]);
  subagentsRef.current = subagents;

  const refreshList = useCallback(async () => {
    if (!windowId) return;
    try {
      const r = await api.getSubagents(windowId);
      setSubagents(r.subagents);
    } catch {
      // Transient — keep the previous list.
    }
  }, [windowId]);

  // Reset selection + cache when the active window changes.
  useEffect(() => {
    setSelectedId(null);
    setMessages([]);
    setSubagents([]);
  }, [windowId]);

  // While open: fetch inventory, poll it slowly, and refresh on spawn/finish.
  useEffect(() => {
    if (!open || !windowId) return;
    setLoadingList(true);
    void refreshList().finally(() => setLoadingList(false));
    const timer = window.setInterval(() => void refreshList(), 5000);
    const unsub = subscribeWs((e) => {
      if (
        e.type === "message" &&
        e.window_id === windowId &&
        SPAWN_TOOLS.has(e.tool_name ?? "")
      ) {
        void refreshList();
      }
    });
    return () => {
      window.clearInterval(timer);
      unsub();
    };
  }, [open, windowId, refreshList, subscribeWs]);

  // Fetch + poll the selected subagent's transcript (poll only while running).
  useEffect(() => {
    if (!open || !selectedId || !windowId) return;
    let cancelled = false;
    const load = async () => {
      try {
        const r = await api.getSubagentMessages(windowId, selectedId);
        if (!cancelled) setMessages(r.messages);
      } catch {
        // Keep whatever we have.
      }
    };
    setLoadingMsgs(true);
    setMessages([]);
    void load().finally(() => {
      if (!cancelled) setLoadingMsgs(false);
    });
    const timer = window.setInterval(() => {
      const status = subagentsRef.current.find(
        (s) => s.agent_id === selectedId,
      )?.status;
      if (status === "completed") return; // transcript is final; stop refetching
      void load();
    }, 2000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [open, selectedId, windowId]);

  const selected = subagents.find((s) => s.agent_id === selectedId) ?? null;

  return (
    <aside
      className={`subagents-panel${open ? " open" : ""}`}
      aria-hidden={!open}
    >
      <header className="subagents-header">
        {selectedId ? (
          <button
            type="button"
            className="icon-button"
            onClick={() => setSelectedId(null)}
            aria-label="Back to subagent list"
            title="Back"
          >
            <ChevronLeft size={16} />
          </button>
        ) : (
          <Bot size={16} />
        )}
        <span className="subagents-title">
          {selected
            ? selected.description || selected.agent_type || selected.agent_id
            : "Subagents"}
          {!selectedId && subagents.length > 0 ? ` (${subagents.length})` : ""}
        </span>
        {onToggleRow && (
          <button
            type="button"
            className="icon-button"
            onClick={onToggleRow}
            title={row === "bottom" ? "Move to top row" : "Move to bottom row"}
            aria-label={
              row === "bottom" ? "Move to top row" : "Move to bottom row"
            }
          >
            {row === "bottom" ? <ArrowUp size={16} /> : <ArrowDown size={16} />}
          </button>
        )}
        <button
          type="button"
          className="icon-button"
          onClick={onClose}
          aria-label="Close subagents panel"
          title="Close"
        >
          <X size={16} />
        </button>
      </header>

      <div className="subagents-body">
        {selectedId ? (
          <div className="subagents-transcript">
            {selected && (
              <div className="subagent-detail-head">
                <StatusDot status={selected.status} />
                <span className="subagent-type">{selected.agent_type}</span>
                {selected.run_id && (
                  <span className="subagent-run">{selected.run_id}</span>
                )}
              </div>
            )}
            {loadingMsgs && messages.length === 0 ? (
              <div className="subagents-empty">Loading transcript…</div>
            ) : messages.length === 0 ? (
              <div className="subagents-empty">No transcript yet.</div>
            ) : (
              messages.map((m, i) => (
                <SubagentBubble key={`${m.transcript_offset ?? i}-${i}`} m={m} />
              ))
            )}
          </div>
        ) : loadingList && subagents.length === 0 ? (
          <div className="subagents-empty">Loading…</div>
        ) : subagents.length === 0 ? (
          <div className="subagents-empty">
            No subagents for this session yet. They appear here when the agent
            spawns an Agent or Workflow.
          </div>
        ) : (
          <ul className="subagents-list">
            {subagents.map((s) => (
              <li key={s.agent_id}>
                <button
                  type="button"
                  className="subagent-row"
                  onClick={() => setSelectedId(s.agent_id)}
                >
                  <StatusDot status={s.status} />
                  <span className="subagent-row-main">
                    <span className="subagent-type">
                      {s.agent_type || "agent"}
                      {s.spawn_kind === "workflow" ? " · workflow" : ""}
                    </span>
                    {s.description && (
                      <span className="subagent-desc">{s.description}</span>
                    )}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  );
}
