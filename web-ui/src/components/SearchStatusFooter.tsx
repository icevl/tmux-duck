import { useState } from "react";
import { ChevronUp, Copy, Loader2, Trash2 } from "lucide-react";
import { api, SearchStatusResponse } from "../api";
import { ConfirmDialog } from "./ConfirmDialog";

interface Props {
  status: SearchStatusResponse | null;
}

const BIG_TASKS = new Set(["initial_backfill", "rebuild"]);

// Whatever's running outside of those big tasks is small live-queue drain.
// Per the design call, we don't dirty the footer for that — small queue
// activity stays invisible and the footer keeps saying "ready · X/Y".
function indexingTaskLabel(status: SearchStatusResponse | null): string | null {
  const worker = status?.operations?.worker;
  if (!worker || worker.status !== "running") return null;
  const task = worker.current_task;
  if (!task) return null;
  if (!BIG_TASKS.has(task)) return null;
  if (task === "initial_backfill") return "initial backfill";
  if (task === "rebuild") return "rebuild";
  return task.replaceAll("_", " ");
}

function statusLine(status: SearchStatusResponse | null): {
  tone: "ok" | "warn" | "danger" | "muted";
  state: string;
  detail: string | null;
  showSpinner: boolean;
} {
  const task = indexingTaskLabel(status);
  const counters = status?.counters;
  const indexed = counters ? counters.indexed_sessions : null;
  const open = counters ? counters.open_sessions : null;
  const indexedChunks = counters?.indexed_chunks ?? null;
  const totalChunks = counters?.total_chunks ?? null;
  const sessionsSuffix =
    indexed != null && open != null ? `${indexed}/${open} indexed` : null;
  // Chunk progress is what actually moves while embedding runs. The worker
  // writes total_chunks before starting and ticks indexed_chunks after each
  // 32-doc batch, so the footer is something the user can watch tick.
  const chunkProgress =
    totalChunks && totalChunks > 0
      ? `${indexedChunks ?? 0}/${totalChunks} chunks`
      : indexedChunks
      ? `${indexedChunks} chunks`
      : null;

  // Big task in flight → footer says "indexing" no matter what state the
  // backend computed (the worker is alive even if heartbeat looks stale).
  if (task) {
    const isPaused = status?.operations?.worker?.paused === true;
    if (isPaused) {
      return {
        tone: "muted",
        state: "paused",
        detail: chunkProgress
          ? `${task} · ${chunkProgress} · waiting for idle`
          : `${task} · waiting for idle`,
        showSpinner: false,
      };
    }
    return {
      tone: "warn",
      state: "indexing",
      detail: chunkProgress ? `${task} · ${chunkProgress}` : task,
      showSpinner: true,
    };
  }

  // No active worker, but supervisor is deliberately holding back —
  // override degraded/missing/etc. with a clearer "deferred" signal so
  // the user sees this is by design, not a failure.
  if (status?.deferred) {
    return {
      tone: "muted",
      state: "deferred",
      detail: "waiting for tmux to be idle",
      showSpinner: false,
    };
  }

  if (!status) {
    return { tone: "muted", state: "search idle", detail: null, showSpinner: false };
  }
  switch (status.state) {
    case "ready":
      return {
        tone: "ok",
        state: "ready",
        detail: sessionsSuffix,
        showSpinner: false,
      };
    case "building":
    case "partial":
      return {
        tone: "warn",
        state: "indexing",
        detail: sessionsSuffix,
        showSpinner: true,
      };
    case "stale":
      return {
        tone: "warn",
        state: "stale",
        detail: sessionsSuffix,
        showSpinner: false,
      };
    case "degraded":
      return {
        tone: "warn",
        state: "degraded",
        detail: sessionsSuffix,
        showSpinner: false,
      };
    case "missing":
      return {
        tone: "muted",
        state: "missing",
        detail: sessionsSuffix,
        showSpinner: false,
      };
    case "unavailable":
      return {
        tone: "danger",
        state: "unavailable",
        detail: sessionsSuffix,
        showSpinner: false,
      };
  }
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "unknown";
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
  return `${Math.floor(seconds / 86400)}d`;
}

function shouldShowRecovery(status: SearchStatusResponse | null): boolean {
  // Maintenance commands are noise during healthy operation. Surface them
  // only when the user actually has something to fix.
  if (!status) return false;
  // Supervisor is deliberately holding back. Nothing to recover — wait
  // for the workload to settle.
  if (status.deferred) return false;
  if (status.state === "unavailable") return true;
  if (status.state === "missing") return true;
  if (status.state === "degraded") return true;
  if (status.state === "stale") return true;
  const ops = status.operations;
  if (ops) {
    if (ops.worker.status === "failed") return true;
    if (ops.worker.stale) return true;
    if (ops.recent_errors.length > 0) return true;
    if (ops.queue.failed_items > 0) return true;
  }
  return false;
}

function RecoveryCommandItem({
  item,
}: {
  item: { label: string; command: string; description: string | null };
}) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard.writeText(item.command).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <div className="recovery-command">
      <div className="recovery-command-head">
        <strong>{item.label}</strong>
        <button
          type="button"
          className="recovery-command-copy"
          onClick={copy}
          title="Copy command"
          aria-label="Copy command"
        >
          <Copy size={11} />
          {copied ? "copied" : "copy"}
        </button>
      </div>
      {item.description && <small>{item.description}</small>}
      <code>{item.command}</code>
    </div>
  );
}

export function SearchStatusFooter({ status }: Props) {
  const [open, setOpen] = useState(false);
  const [confirmWipe, setConfirmWipe] = useState(false);
  const [wiping, setWiping] = useState(false);
  const [wipeError, setWipeError] = useState<string | null>(null);
  const line = statusLine(status);
  const operations = status?.operations ?? null;
  const showRecovery = shouldShowRecovery(status);
  const detailsId = "search-status-footer-details";

  const runWipe = async () => {
    setWiping(true);
    setWipeError(null);
    try {
      await api.wipeSearchIndex();
      setConfirmWipe(false);
    } catch (err) {
      setWipeError(err instanceof Error ? err.message : "wipe failed");
    } finally {
      setWiping(false);
    }
  };

  return (
    <div className={`search-status-footer${open ? " open" : ""}`}>
      {open && (
        <div
          id={detailsId}
          className="search-status-details footer-details"
          aria-label="Search status details"
        >
          {operations ? (
            <>
              <div className="search-detail-row">
                <span>Worker heartbeat</span>
                <strong>
                  {operations.worker.status ?? "inactive"}
                  {operations.worker.paused ? " · paused" : ""}
                  {operations.worker.stale ? " · stale" : ""}
                </strong>
                <small>
                  {operations.worker.heartbeat_at
                    ? `${formatDuration(operations.worker.heartbeat_age_seconds)} ago`
                    : "no heartbeat"}
                </small>
              </div>
              <div className="search-detail-row">
                <span>Queue</span>
                <strong>
                  {operations.queue.queued_items + operations.queue.leased_items}{" "}
                  queued
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
                <small>
                  {operations.progress.indexed_chunks}
                  {operations.progress.total_chunks
                    ? `/${operations.progress.total_chunks}`
                    : ""}{" "}
                  chunks
                </small>
              </div>
              {(operations.progress.model_id || operations.progress.table_name) && (
                <div className="search-detail-row">
                  <span>Model</span>
                  <strong>{operations.progress.model_id ?? "lexical"}</strong>
                  <small>
                    {operations.progress.vector_dimension
                      ? `${operations.progress.vector_dimension} dims`
                      : "no vector index"}
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
              {showRecovery && operations.recovery_commands.length > 0 && (
                <div className="search-detail-row vertical recovery-block">
                  <span>Manual operations</span>
                  <small>
                    Run these in the Codi project shell when search looks
                    stuck or out of date.
                  </small>
                  {operations.recovery_commands.map((item) => (
                    <RecoveryCommandItem key={item.command} item={item} />
                  ))}
                </div>
              )}
              <div className="search-detail-row vertical recovery-block">
                <span>Reset</span>
                <small>
                  Stops the worker, drops the local queue and embeddings,
                  and triggers a fresh backfill from currently open sessions.
                </small>
                <button
                  type="button"
                  className="search-wipe-button"
                  onClick={() => {
                    setWipeError(null);
                    setConfirmWipe(true);
                  }}
                  disabled={wiping}
                >
                  <Trash2 size={12} />
                  {wiping ? "Wiping…" : "Wipe index"}
                </button>
                {wipeError && (
                  <small className="search-wipe-error">{wipeError}</small>
                )}
              </div>
            </>
          ) : (
            <div className="search-detail-row vertical">
              <span>Status</span>
              <small>Waiting for the first search index status update.</small>
            </div>
          )}
        </div>
      )}
      <button
        type="button"
        className={`search-status-footer-bar tone-${line.tone}`}
        onClick={() => setOpen((prev) => !prev)}
        aria-expanded={open}
        aria-controls={detailsId}
        title={status?.reason ?? "Search index status"}
      >
        {line.showSpinner ? (
          <Loader2 size={11} className="activity-spinner" />
        ) : (
          <span className={`status-dot tone-${line.tone}`} aria-hidden="true" />
        )}
        <span className="state">{line.state}</span>
        {line.detail && (
          <>
            <span className="sep" aria-hidden="true">
              ·
            </span>
            <span className="detail">{line.detail}</span>
          </>
        )}
        <ChevronUp
          size={11}
          className={`footer-chevron${open ? " open" : ""}`}
          aria-hidden="true"
        />
      </button>
      {confirmWipe && (
        <ConfirmDialog
          title="Wipe search index?"
          body="This terminates the indexing worker, removes the local queue and embeddings, and starts a fresh backfill from the currently open sessions. Existing transcripts on disk are not touched."
          confirmLabel={wiping ? "Wiping…" : "Wipe index"}
          danger
          onConfirm={runWipe}
          onCancel={() => {
            if (!wiping) setConfirmWipe(false);
          }}
        />
      )}
    </div>
  );
}
