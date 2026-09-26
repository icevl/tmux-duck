import { useEffect, useState } from "react";
import { AccountInfo, api, ResumeSession, RuntimeInfo } from "../api";
import { DirectoryPicker } from "./DirectoryPicker";

interface Props {
  accounts: AccountInfo[];
  onClose: () => void;
  onOpenAccounts: () => void;
  onCreate: (body: {
    cwd: string;
    runtime: string;
    resume_session_id?: string | null;
    name?: string | null;
    profile?: string;
  }) => Promise<void>;
}

type Stage = "directory" | "runtime" | "resume";

// API account id → the session's profile field ("" = system default login).
function profileOf(account: AccountInfo): string {
  return account.is_default ? "" : account.id;
}

export function NewSessionDialog({ accounts, onClose, onOpenAccounts, onCreate }: Props) {
  const [stage, setStage] = useState<Stage>("directory");
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [runtimes, setRuntimes] = useState<RuntimeInfo[]>([]);
  const [runtime, setRuntime] = useState<string>("codex");
  const [profile, setProfile] = useState<string>("");
  const [resumeOptions, setResumeOptions] = useState<ResumeSession[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.listRuntimes().then((r) => setRuntimes(r.runtimes)).catch(() => undefined);
  }, []);

  async function selectDirectory(path: string) {
    setSelectedPath(path);
    setBusy(true);
    try {
      const r = await api.listResumeSessions(path);
      setResumeOptions(r.sessions);
      if (r.sessions.length > 0) {
        setStage("resume");
      } else {
        setStage("runtime");
      }
    } catch {
      setResumeOptions([]);
      setStage("runtime");
    } finally {
      setBusy(false);
    }
  }

  const runtimeAccounts = accounts.filter((a) => a.runtime === runtime);
  const selectedAccount = runtimeAccounts.find((a) => profileOf(a) === profile);
  const needsSignIn = selectedAccount?.logged_in === false;

  async function submit(body: {
    cwd: string;
    runtime: string;
    resume_session_id?: string | null;
    profile?: string;
  }) {
    setBusy(true);
    setError(null);
    try {
      await onCreate(body);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div className="modal" onMouseDown={(e) => e.stopPropagation()}>
        <h2>New session</h2>
        {error && <div className="login-error" style={{ marginBottom: 10 }}>{error}</div>}

        {stage === "directory" && (
          <>
            <div className="modal-row">
              <label>Working directory</label>
              <DirectoryPicker value={selectedPath} onChange={setSelectedPath} />
            </div>
            <div className="modal-actions">
              <button onClick={onClose}>Cancel</button>
              <button
                className="primary"
                disabled={!selectedPath || busy}
                onClick={() => selectDirectory(selectedPath ?? "")}
              >
                {busy ? "…" : "Use this directory →"}
              </button>
            </div>
          </>
        )}

        {stage === "resume" && (
          <>
            <div className="modal-row">
              <label>Existing sessions in {selectedPath}</label>
            </div>
            <div style={{ maxHeight: 320, overflowY: "auto" }}>
              {resumeOptions.map((s) => (
                <div
                  key={s.session_id}
                  className="resume-row"
                  onClick={() =>
                    submit({
                      cwd: selectedPath ?? "",
                      runtime: s.runtime || runtime,
                      resume_session_id: s.session_id,
                      profile: s.profile ?? "",
                    })
                  }
                >
                  <div className="summary">{s.summary || "Untitled"}</div>
                  <div className="count">
                    {s.message_count} msgs · {s.session_id.slice(0, 8)}…
                  </div>
                </div>
              ))}
            </div>
            <div className="modal-actions">
              <button onClick={() => setStage("directory")}>← Back</button>
              <button onClick={() => setStage("runtime")}>Skip — new session</button>
            </div>
          </>
        )}

        {stage === "runtime" && (
          <>
            <div className="modal-row">
              <label>Working directory</label>
              <div className="path" style={{ color: "var(--text-1)" }}>
                {selectedPath}
              </div>
            </div>
            <div className="modal-row">
              <label>Agent runtime</label>
              <div className="runtime-buttons">
                {runtimes.map((r) => (
                  <button
                    key={r.name}
                    className={runtime === r.name ? "selected" : ""}
                    onClick={() => {
                      setRuntime(r.name);
                      setProfile("");
                    }}
                  >
                    {r.emoji} {r.display_name}
                  </button>
                ))}
              </div>
            </div>
            {runtimeAccounts.length > 1 && (
              <div className="modal-row">
                <label>Account</label>
                <div className="runtime-buttons">
                  {runtimeAccounts.map((a) => (
                    <button
                      key={a.key}
                      className={profile === profileOf(a) ? "selected" : ""}
                      onClick={() => setProfile(profileOf(a))}
                      title={a.email ?? undefined}
                    >
                      {a.label}
                      {a.logged_in === false ? " · signed out" : ""}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {needsSignIn && (
              <div className="login-error">
                This account is signed out.{" "}
                <button className="link-button" onClick={onOpenAccounts}>
                  Sign in
                </button>
              </div>
            )}
            <div className="modal-actions">
              <button onClick={() => setStage("directory")}>← Back</button>
              <button
                className="primary"
                disabled={busy || !selectedPath || needsSignIn}
                onClick={() =>
                  submit({
                    cwd: selectedPath ?? "",
                    runtime,
                    resume_session_id: null,
                    profile,
                  })
                }
              >
                {busy ? "Creating…" : "Create"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
