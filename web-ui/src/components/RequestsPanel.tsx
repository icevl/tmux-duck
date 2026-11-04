import { useCallback, useEffect, useState } from "react";
import { ArrowDown, ArrowUp, History, X } from "lucide-react";
import { api, UserRequest, WsEvent } from "../api";

interface Props {
  windowId: string;
  open: boolean;
  onClose: () => void;
  onJump: (request: UserRequest) => void;
  row?: "top" | "bottom";
  onToggleRow?: () => void;
  subscribeWs: (l: (e: WsEvent) => void) => () => void;
}

function formatWhen(timestamp: string | null | undefined): string {
  if (!timestamp) return "";
  const date = new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  const time = date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  if (date.toDateString() === new Date().toDateString()) return time;
  return `${date.toLocaleDateString([], { day: "numeric", month: "short" })} ${time}`;
}

// Everything the user asked for in this session, newest first. A click jumps
// the chat to that message.
export function RequestsPanel({
  windowId,
  open,
  onClose,
  onJump,
  row,
  onToggleRow,
  subscribeWs,
}: Props) {
  const [requests, setRequests] = useState<UserRequest[]>([]);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const r = await api.getRequests(windowId);
      setRequests(r.requests);
    } catch {
      // Transient — keep the previous list.
    }
  }, [windowId]);

  useEffect(() => setRequests([]), [windowId]);

  useEffect(() => {
    if (!open || !windowId) return;
    setLoading(true);
    void refresh().finally(() => setLoading(false));
    return subscribeWs((e) => {
      if (
        e.type === "message" &&
        e.window_id === windowId &&
        e.role === "user" &&
        e.content_type === "text"
      ) {
        void refresh();
      }
    });
  }, [open, windowId, refresh, subscribeWs]);

  const newestFirst = [...requests].reverse();

  return (
    <aside className={`requests-panel${open ? " open" : ""}`} aria-hidden={!open}>
      <header className="subagents-header">
        <History size={16} />
        <span className="subagents-title">
          Requests{requests.length > 0 ? ` (${requests.length})` : ""}
        </span>
        {onToggleRow && (
          <button
            type="button"
            className="icon-button"
            onClick={onToggleRow}
            title={row === "bottom" ? "Move to top row" : "Move to bottom row"}
            aria-label={row === "bottom" ? "Move to top row" : "Move to bottom row"}
          >
            {row === "bottom" ? <ArrowUp size={16} /> : <ArrowDown size={16} />}
          </button>
        )}
        <button
          type="button"
          className="icon-button"
          onClick={onClose}
          aria-label="Close requests panel"
          title="Close"
        >
          <X size={16} />
        </button>
      </header>
      <div className="subagents-body">
        {loading && requests.length === 0 ? (
          <div className="subagents-empty">Loading…</div>
        ) : requests.length === 0 ? (
          <div className="subagents-empty">Nothing asked in this session yet.</div>
        ) : (
          <ol className="flex flex-col gap-1 p-2">
            {newestFirst.map((r, i) => (
              <li key={`${r.transcript_offset ?? i}-${r.transcript_index ?? 0}`}>
                <button
                  type="button"
                  data-slot="request-row"
                  onClick={() => onJump(r)}
                  title="Show in chat"
                  className="flex w-full cursor-pointer flex-col gap-1 rounded-lg px-3 py-2 text-left transition hover:bg-accent"
                >
                  <span className="flex items-center gap-2 text-[length:calc(11px*var(--ts,1))] text-muted-foreground">
                    <span className="tabular-nums">#{requests.length - i}</span>
                    <span>{formatWhen(r.timestamp)}</span>
                  </span>
                  <span className="line-clamp-4 text-sm break-words whitespace-pre-wrap text-foreground">
                    {r.text}
                  </span>
                </button>
              </li>
            ))}
          </ol>
        )}
      </div>
    </aside>
  );
}
