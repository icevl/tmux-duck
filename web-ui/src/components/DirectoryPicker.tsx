import { useEffect, useState } from "react";
import { api, DirectoryListing } from "../api";

interface Props {
  /** Currently selected absolute path (controlled). */
  value: string | null;
  /** Fired when the user picks a directory (single click) or navigates. */
  onChange: (path: string) => void;
  /** Initial path to list; defaults to "~". */
  initialPath?: string;
  /** Max height of the scrollable directory list. */
  maxHeight?: number;
}

/**
 * Reusable directory browser: a path input + "Up" button and a list of
 * subdirectories. Single click selects a row; double click descends into it.
 * Extracted from NewSessionDialog so the New-session flow and the connector
 * settings form share one picker.
 */
export function DirectoryPicker({
  value,
  onChange,
  initialPath = "~",
  maxHeight = 260,
}: Props) {
  const [listing, setListing] = useState<DirectoryListing | null>(null);
  const [pathInput, setPathInput] = useState(value || initialPath);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setError(null);
    api
      .listDirectories(pathInput)
      .then((r) => {
        setListing(r);
        if (r.path !== pathInput) setPathInput(r.path);
      })
      .catch((err: Error) => setError(err.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathInput]);

  function goUp() {
    if (listing?.parent) setPathInput(listing.parent);
  }

  return (
    <div className="directory-picker">
      {error && (
        <div className="login-error" style={{ marginBottom: 8 }}>
          {error}
        </div>
      )}
      <div style={{ display: "flex", gap: 6, marginBottom: 6 }}>
        <input
          style={{ flex: 1 }}
          value={pathInput}
          onChange={(e) => setPathInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") setPathInput((p) => p.trim() || "~");
          }}
        />
        <button type="button" onClick={goUp} disabled={!listing?.parent}>
          ↑ Up
        </button>
      </div>
      <div style={{ maxHeight, overflowY: "auto" }}>
        {listing?.entries.length === 0 && (
          <div style={{ color: "var(--text-2)", padding: 8 }}>
            No subdirectories.
          </div>
        )}
        {listing?.entries.map((d) => (
          <div
            key={d.path}
            className={`dir-row${value === d.path ? " selected" : ""}`}
            onClick={() => onChange(d.path)}
            onDoubleClick={() => setPathInput(d.path)}
          >
            <span>📁 {d.name}</span>
            <span className="path">{d.path}</span>
          </div>
        ))}
      </div>
      {listing?.path && (
        <button
          type="button"
          className="ghost"
          style={{ marginTop: 6 }}
          onClick={() => onChange(listing.path)}
        >
          Use current folder: <span className="path">{listing.path}</span>
        </button>
      )}
    </div>
  );
}
