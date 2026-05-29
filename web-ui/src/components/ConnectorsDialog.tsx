import { useEffect, useState } from "react";
import {
  AclEntry,
  api,
  ConnectorField,
  ConnectorInfo,
  ConnectorTypeInfo,
  ConnectorWriteBody,
  RuntimeInfo,
} from "../api";
import { DirectoryPicker } from "./DirectoryPicker";

interface Props {
  onClose: () => void;
}

type View = "list" | "pick-type" | "form";

function asString(v: unknown): string {
  return typeof v === "string" ? v : v == null ? "" : String(v);
}

function asList(v: unknown): string {
  return Array.isArray(v) ? v.join(", ") : "";
}

function parseList(value: string): string[] {
  return value
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

/**
 * Manage external connectors. The form is rendered generically from the
 * selected type's declarative field schema (`/api/connector-types`), so a
 * new connector type needs no UI changes here. Secret fields are write-only:
 * blank on edit means "keep the existing value".
 */
export function ConnectorsDialog({ onClose }: Props) {
  const [connectors, setConnectors] = useState<ConnectorInfo[]>([]);
  const [types, setTypes] = useState<ConnectorTypeInfo[]>([]);
  const [runtimes, setRuntimes] = useState<RuntimeInfo[]>([]);
  const [view, setView] = useState<View>("list");
  const [selectedType, setSelectedType] = useState<ConnectorTypeInfo | null>(null);
  const [editing, setEditing] = useState<ConnectorInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [name, setName] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [values, setValues] = useState<Record<string, string>>({});
  // Structured value for "acl" fields, keyed by field key.
  const [aclValues, setAclValues] = useState<Record<string, AclEntry[]>>({});

  function reload() {
    api
      .listConnectors()
      .then((r) => setConnectors(r.connectors))
      .catch((e: Error) => setError(e.message));
  }

  useEffect(() => {
    reload();
    api.listConnectorTypes().then((r) => setTypes(r.types)).catch(() => undefined);
    api.listRuntimes().then((r) => setRuntimes(r.runtimes)).catch(() => undefined);
  }, []);

  function setValue(key: string, val: string) {
    setValues((prev) => ({ ...prev, [key]: val }));
  }

  function startForm(type: ConnectorTypeInfo, c: ConnectorInfo | null) {
    const init: Record<string, string> = {};
    const initAcl: Record<string, AclEntry[]> = {};
    for (const f of type.fields) {
      if (f.type === "acl") {
        const raw = c ? c.config[f.key] : null;
        initAcl[f.key] = Array.isArray(raw)
          ? raw.map((e) => ({
              user: asString((e as AclEntry).user),
              write: Boolean((e as AclEntry).write),
            }))
          : [];
      } else if (f.type === "runtime")
        init[f.key] = c ? asString(c.config[f.key]) || "codex" : "codex";
      else if (f.type === "bool")
        init[f.key] = c && c.config[f.key] ? "true" : "false";
      else if (f.type === "secret") init[f.key] = "";
      else if (f.type === "list") init[f.key] = c ? asList(c.config[f.key]) : "";
      else init[f.key] = c ? asString(c.config[f.key]) : "";
    }
    setSelectedType(type);
    setEditing(c);
    setName(c ? c.name : "");
    setEnabled(c ? c.enabled : false);
    setValues(init);
    setAclValues(initAcl);
    setError(null);
    setView("form");
  }

  function openCreate() {
    setError(null);
    if (types.length === 0) {
      setError("No connector types available");
      return;
    }
    if (types.length === 1) {
      startForm(types[0], null);
    } else {
      setView("pick-type");
    }
  }

  function openEdit(c: ConnectorInfo) {
    const type = types.find((t) => t.type === c.type);
    if (!type) {
      setError(`Unknown connector type: ${c.type}`);
      return;
    }
    startForm(type, c);
  }

  async function save() {
    if (!selectedType) return;
    if (!name.trim()) {
      setError("Name is required");
      return;
    }
    for (const f of selectedType.fields) {
      if (!f.required) continue;
      if (f.type === "acl") {
        if (!(aclValues[f.key] || []).some((r) => r.user.trim())) {
          setError(`${f.label} is required`);
          return;
        }
        continue;
      }
      const v = (values[f.key] || "").trim();
      if (f.type === "secret") {
        // On edit, an already-set secret may be left blank to keep it.
        if (!v && !editing?.secrets[f.key]) {
          setError(`${f.label} is required`);
          return;
        }
      } else if (f.type !== "bool" && !v) {
        setError(`${f.label} is required`);
        return;
      }
    }

    const config: Record<string, unknown> = {};
    for (const f of selectedType.fields) {
      if (f.type === "acl") {
        config[f.key] = (aclValues[f.key] || [])
          .filter((r) => r.user.trim())
          .map((r) => ({ user: r.user.trim(), write: !!r.write }));
        continue;
      }
      const v = values[f.key] ?? "";
      if (f.type === "list") config[f.key] = parseList(v);
      else if (f.type === "bool") config[f.key] = v === "true";
      else if (f.type === "secret") {
        if (v.trim()) config[f.key] = v.trim();
      } else config[f.key] = v.trim ? v.trim() : v;
    }

    const body: ConnectorWriteBody = { name: name.trim(), enabled, config };
    setBusy(true);
    setError(null);
    try {
      if (editing) await api.updateConnector(editing.id, body);
      else await api.createConnector({ ...body, type: selectedType.type });
      reload();
      setView("list");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function toggleEnabled(c: ConnectorInfo) {
    try {
      await api.updateConnector(c.id, { enabled: !c.enabled });
      reload();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function remove(c: ConnectorInfo) {
    if (!window.confirm(`Delete connector "${c.name}"?`)) return;
    try {
      await api.deleteConnector(c.id);
      reload();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function killSessions(c: ConnectorInfo) {
    if (
      !window.confirm(
        `Kill ALL active agent sessions for "${c.name}"? Running tmux windows ` +
          `will be terminated and their Slack threads detached.`,
      )
    )
      return;
    try {
      const r = await api.killConnectorSessions(c.id);
      setError(null);
      reload();
      window.alert(`Killed ${r.killed} session(s).`);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function updateAcl(key: string, rows: AclEntry[]) {
    setAclValues((prev) => ({ ...prev, [key]: rows }));
  }

  function renderField(f: ConnectorField) {
    const v = values[f.key] ?? "";
    if (f.type === "acl") {
      const rows = aclValues[f.key] || [];
      return (
        <div className="acl-list">
          {rows.map((row, i) => (
            <div className="acl-row" key={i}>
              <input
                value={row.user}
                placeholder="U0123 (Slack user id)"
                onChange={(e) => {
                  const next = rows.slice();
                  next[i] = { ...row, user: e.target.value };
                  updateAcl(f.key, next);
                }}
              />
              <label className="acl-write">
                <input
                  type="checkbox"
                  checked={row.write}
                  onChange={(e) => {
                    const next = rows.slice();
                    next[i] = { ...row, write: e.target.checked };
                    updateAcl(f.key, next);
                  }}
                />
                Write
              </label>
              <button
                type="button"
                className="danger"
                onClick={() => updateAcl(f.key, rows.filter((_, j) => j !== i))}
              >
                ✕
              </button>
            </div>
          ))}
          <button
            type="button"
            className="ghost"
            onClick={() => updateAcl(f.key, [...rows, { user: "", write: false }])}
          >
            + Add user
          </button>
        </div>
      );
    }
    if (f.type === "runtime") {
      return (
        <div className="runtime-buttons">
          {runtimes.map((r) => (
            <button
              key={r.name}
              className={v === r.name ? "selected" : ""}
              onClick={() => setValue(f.key, r.name)}
            >
              {r.emoji} {r.display_name}
            </button>
          ))}
        </div>
      );
    }
    if (f.type === "directory") {
      return (
        <DirectoryPicker
          value={v || null}
          onChange={(p) => setValue(f.key, p)}
          maxHeight={180}
        />
      );
    }
    if (f.type === "textarea") {
      return (
        <textarea
          rows={4}
          value={v}
          onChange={(e) => setValue(f.key, e.target.value)}
          placeholder={f.placeholder}
        />
      );
    }
    if (f.type === "bool") {
      return (
        <label>
          <input
            type="checkbox"
            checked={v === "true"}
            onChange={(e) => setValue(f.key, e.target.checked ? "true" : "false")}
            style={{ marginRight: 8 }}
          />
          {f.help || f.label}
        </label>
      );
    }
    const isSecret = f.type === "secret";
    return (
      <input
        type={isSecret ? "password" : "text"}
        value={v}
        onChange={(e) => setValue(f.key, e.target.value)}
        placeholder={
          isSecret && editing?.secrets[f.key]
            ? "•••••• set — leave blank to keep"
            : f.placeholder
        }
      />
    );
  }

  return (
    <div className="modal-backdrop" onMouseDown={onClose}>
      <div className="modal" onMouseDown={(e) => e.stopPropagation()}>
        <h2>Connectors</h2>
        {error && (
          <div className="login-error" style={{ marginBottom: 10 }}>
            {error}
          </div>
        )}

        {view === "list" && (
          <>
            <div style={{ maxHeight: 340, overflowY: "auto" }}>
              {connectors.length === 0 && (
                <div style={{ color: "var(--text-2)", padding: 8 }}>
                  No connectors yet. Add one to drive sessions from an external
                  chat.
                </div>
              )}
              {connectors.map((c) => (
                <div key={c.id} className="connector-row">
                  <div className="connector-main">
                    <div className="connector-name">
                      🔌 {c.name}
                      {c.running && (
                        <span className="connector-badge live"> live</span>
                      )}
                    </div>
                    <div className="path">
                      {c.type}
                      {c.config.default_runtime
                        ? ` · ${asString(c.config.default_runtime)}`
                        : ""}
                      {c.config.cwd ? ` · ${asString(c.config.cwd)}` : ""}
                    </div>
                  </div>
                  <div className="connector-actions">
                    <button onClick={() => toggleEnabled(c)}>
                      {c.enabled ? "Disable" : "Enable"}
                    </button>
                    <button onClick={() => openEdit(c)}>Edit</button>
                    <button onClick={() => killSessions(c)} title="Kill all active agent sessions">
                      Kill sessions
                    </button>
                    <button className="danger" onClick={() => remove(c)}>
                      Delete
                    </button>
                  </div>
                </div>
              ))}
            </div>
            <div className="modal-actions">
              <button onClick={onClose}>Close</button>
              <button className="primary" onClick={openCreate}>
                + Add connector
              </button>
            </div>
          </>
        )}

        {view === "pick-type" && (
          <>
            <div className="modal-row">
              <label>Choose a connector type</label>
            </div>
            <div style={{ maxHeight: 320, overflowY: "auto" }}>
              {types.map((t) => (
                <div
                  key={t.type}
                  className="dir-row"
                  onClick={() => startForm(t, null)}
                >
                  <span>🔌 {t.label}</span>
                  <span className="path">{t.type}</span>
                </div>
              ))}
            </div>
            <div className="modal-actions">
              <button onClick={() => setView("list")}>← Back</button>
            </div>
          </>
        )}

        {view === "form" && selectedType && (
          <>
            <div className="modal-row">
              <label>Name</label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={`My ${selectedType.label} connector`}
              />
            </div>

            {selectedType.fields.map((f) => (
              <div className="modal-row" key={f.key}>
                <label>
                  {f.label}
                  {f.type === "directory" && values[f.key]
                    ? `: ${values[f.key]}`
                    : ""}
                </label>
                {renderField(f)}
                {f.help && f.type !== "bool" && (
                  <div className="path" style={{ marginTop: 2 }}>
                    {f.help}
                  </div>
                )}
              </div>
            ))}

            <div className="modal-row">
              <label>
                <input
                  type="checkbox"
                  checked={enabled}
                  onChange={(e) => setEnabled(e.target.checked)}
                  style={{ marginRight: 8 }}
                />
                Enabled (connect now)
              </label>
            </div>

            <div className="modal-actions">
              <button onClick={() => setView("list")}>← Back</button>
              <button className="primary" disabled={busy} onClick={save}>
                {busy ? "Saving…" : editing ? "Save" : "Create"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
