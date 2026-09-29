import { ModalShell } from "./ModalShell";
import { useCallback, useEffect, useState } from "react";
import { AccountInfo, api } from "../api";

interface Props {
  onClose: () => void;
  onChanged?: () => void;
}

const RUNTIME_LABELS: Record<string, string> = {
  claude: "Claude Code",
  codex: "Codex",
};
const POLL_MS = 1500;

function isActive(a: AccountInfo): boolean {
  const state = a.login?.state;
  return state === "starting" || state === "awaiting_code" || state === "awaiting_browser";
}

function statusText(a: AccountInfo): string {
  if (a.logged_in === true) {
    return [a.email, a.detail].filter(Boolean).join(" · ") || "Signed in";
  }
  if (a.logged_in === false) return "Not signed in";
  return a.detail || "Status unknown";
}

/**
 * Agent accounts: the system-wide login per runtime plus extra Claude
 * profiles, each with its own credentials. Sign-in runs the CLI's
 * browserless flow on the server and hands the link to this page, so it
 * works from a phone: open the link, sign in, paste the code back (Claude)
 * or enter the shown code on the page (Codex).
 */
export function AccountsDialog({ onClose, onChanged }: Props) {
  const [accounts, setAccounts] = useState<AccountInfo[]>([]);
  const [profileRuntimes, setProfileRuntimes] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [codes, setCodes] = useState<Record<string, string>>({});
  const [newLabel, setNewLabel] = useState("");

  const reload = useCallback(async () => {
    try {
      const r = await api.listAccounts();
      setAccounts(r.accounts);
      setProfileRuntimes(r.profile_runtimes);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const polling = accounts.some(isActive);
  useEffect(() => {
    if (!polling) return;
    const timer = window.setInterval(() => void reload(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [polling, reload]);

  async function run(a: AccountInfo | null, action: () => Promise<unknown>) {
    setBusyKey(a?.key ?? "new");
    setError(null);
    try {
      await action();
      await reload();
      onChanged?.();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyKey(null);
    }
  }

  async function addAccount(runtime: string) {
    const label = newLabel.trim();
    if (!label) return;
    await run(null, async () => {
      const created = await api.createAccount({ runtime, label });
      setNewLabel("");
      await api.startAccountLogin(created);
    });
  }

  const runtimes = Array.from(new Set(accounts.map((a) => a.runtime)));

  return (
    <ModalShell title="Accounts" onClose={onClose} className="sm:max-w-[560px]">
        {error && <div className="login-error">{error}</div>}

        {runtimes.map((runtime) => (
          <section key={runtime} className="accounts-group">
            <h3>{RUNTIME_LABELS[runtime] ?? runtime}</h3>
            {accounts
              .filter((a) => a.runtime === runtime)
              .map((a) => (
                <div key={a.key} className="account-row">
                  <div className="account-head">
                    <div className="account-text">
                      <div className="account-label">
                        {a.label}
                        {a.is_default && <span className="account-tag">system</span>}
                        {a.sessions > 0 && (
                          <span className="account-tag">
                            {a.sessions} session{a.sessions === 1 ? "" : "s"}
                          </span>
                        )}
                      </div>
                      <div
                        className={`account-status${
                          a.logged_in === false ? " signed-out" : ""
                        }`}
                      >
                        {statusText(a)}
                      </div>
                    </div>
                    <div className="account-actions">
                      {!isActive(a) && (
                        <button
                          className={a.logged_in === false ? "primary" : ""}
                          disabled={busyKey === a.key}
                          onClick={() => run(a, () => api.startAccountLogin(a))}
                        >
                          {a.logged_in ? "Re-login" : "Sign in"}
                        </button>
                      )}
                      <button
                        disabled={busyKey === a.key}
                        onClick={() => run(a, () => api.refreshAccount(a))}
                        title="Re-check sign-in status"
                      >
                        ↻
                      </button>
                      {!a.is_default && (
                        <button
                          className="danger"
                          disabled={busyKey === a.key || a.sessions > 0}
                          title={
                            a.sessions > 0
                              ? "Close this account's sessions first"
                              : "Delete account"
                          }
                          onClick={() => run(a, () => api.deleteAccount(a))}
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </div>

                  {a.login && a.login.state !== "cancelled" && (
                    <div className="account-login">
                      {a.login.state === "starting" && <div>Starting sign-in…</div>}

                      {a.login.state === "awaiting_code" && a.login.url && (
                        <>
                          <div>
                            1.{" "}
                            <a href={a.login.url} target="_blank" rel="noreferrer">
                              Open the sign-in page
                            </a>{" "}
                            and sign in to the account you want here.
                          </div>
                          <div>2. Paste the code it shows:</div>
                          <form
                            className="account-code-form"
                            onSubmit={(e) => {
                              e.preventDefault();
                              const code = (codes[a.key] ?? "").trim();
                              if (!code) return;
                              void run(a, async () => {
                                await api.submitAccountLoginCode(a, code);
                                setCodes((c) => ({ ...c, [a.key]: "" }));
                              });
                            }}
                          >
                            <input
                              value={codes[a.key] ?? ""}
                              onChange={(e) =>
                                setCodes((c) => ({ ...c, [a.key]: e.target.value }))
                              }
                              placeholder="Authentication code"
                              autoComplete="off"
                              spellCheck={false}
                            />
                            <button className="primary" type="submit">
                              Submit
                            </button>
                          </form>
                        </>
                      )}

                      {a.login.state === "awaiting_browser" && a.login.url && (
                        <>
                          <div>
                            1.{" "}
                            <a href={a.login.url} target="_blank" rel="noreferrer">
                              Open the sign-in page
                            </a>{" "}
                            and sign in.
                          </div>
                          <div>
                            2. Enter this code there:{" "}
                            <code className="account-user-code">{a.login.user_code}</code>
                          </div>
                          <div className="account-muted">Waiting for confirmation…</div>
                        </>
                      )}

                      {a.login.state === "succeeded" && (
                        <div className="account-ok">
                          Signed in{a.email ? ` as ${a.email}` : ""}.
                        </div>
                      )}
                      {a.login.state === "failed" && (
                        <div className="login-error">
                          Sign-in failed{a.login.message ? `: ${a.login.message}` : ""}
                        </div>
                      )}
                      {a.login.message && a.login.state === "awaiting_code" && (
                        <div className="login-error">{a.login.message}</div>
                      )}

                      {isActive(a) && (
                        <button
                          className="account-cancel"
                          onClick={() => run(a, () => api.cancelAccountLogin(a))}
                        >
                          Cancel sign-in
                        </button>
                      )}
                    </div>
                  )}
                </div>
              ))}

            {profileRuntimes.includes(runtime) && (
              <form
                className="account-add"
                onSubmit={(e) => {
                  e.preventDefault();
                  void addAccount(runtime);
                }}
              >
                <input
                  value={newLabel}
                  onChange={(e) => setNewLabel(e.target.value)}
                  placeholder={`Add ${RUNTIME_LABELS[runtime] ?? runtime} account — name`}
                  maxLength={60}
                />
                <button type="submit" disabled={!newLabel.trim() || busyKey === "new"}>
                  Add &amp; sign in
                </button>
              </form>
            )}
          </section>
        ))}

        <div className="modal-actions">
          <button onClick={onClose}>Close</button>
        </div>
      </ModalShell>
  );
}
