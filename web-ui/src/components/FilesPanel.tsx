import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowUp,
  ChevronDown,
  ChevronRight,
  ChevronsDownUp,
  File as FileIcon,
  Folder,
  FolderOpen,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import { api } from "../api";
import { CodeViewer } from "./CodeViewer";
import { Markdown } from "./Markdown";

const ICON = 16;

const MARKDOWN_EXTENSIONS = new Set([
  "md",
  "markdown",
  "mdown",
  "mdwn",
  "mkd",
  "mdx",
]);

function isMarkdownPath(path: string): boolean {
  const dot = path.lastIndexOf(".");
  if (dot === -1) return false;
  return MARKDOWN_EXTENSIONS.has(path.slice(dot + 1).toLowerCase());
}

interface Props {
  windowId: string;
  open: boolean;
  onClose: () => void;
  row?: "top" | "bottom";
  onToggleRow?: () => void;
}

interface DirEntry {
  name: string;
  type: "file" | "dir";
  path: string;
}

interface FileView {
  path: string;
  size: number;
  truncated: boolean;
  binary: boolean;
  content: string;
}

// Per-windowId cache of "directory path → entries". Survives across panel
// open/close inside a session so re-opening doesn't re-fetch the tree.
type Tree = Map<string, DirEntry[]>;

interface NodeProps {
  entry: DirEntry;
  depth: number;
  tree: Tree;
  expanded: Set<string>;
  loading: Set<string>;
  selectedPath: string | null;
  onToggleDir: (path: string) => void;
  onSelectFile: (entry: DirEntry) => void;
}

function TreeNode({
  entry,
  depth,
  tree,
  expanded,
  loading,
  selectedPath,
  onToggleDir,
  onSelectFile,
}: NodeProps) {
  const isOpen = expanded.has(entry.path);
  const isLoading = loading.has(entry.path);
  const children = isOpen ? tree.get(entry.path) ?? null : null;

  const isDir = entry.type === "dir";
  const isSelected = selectedPath === entry.path;
  const handleClick = () => {
    if (isDir) onToggleDir(entry.path);
    else onSelectFile(entry);
  };

  return (
    <>
      <button
        type="button"
        className={`files-row${isSelected ? " selected" : ""}`}
        style={{ paddingLeft: 8 + depth * 14 }}
        onClick={handleClick}
        title={entry.path}
      >
        <span className="files-row-chevron" aria-hidden="true">
          {isDir ? (
            isOpen ? (
              <ChevronDown size={12} />
            ) : (
              <ChevronRight size={12} />
            )
          ) : (
            <span className="files-row-chevron-spacer" />
          )}
        </span>
        <span className="files-row-icon" aria-hidden="true">
          {isDir ? (
            isOpen ? (
              <FolderOpen size={ICON} />
            ) : (
              <Folder size={ICON} />
            )
          ) : (
            <FileIcon size={ICON} />
          )}
        </span>
        <span className="files-row-name">{entry.name}</span>
        {isLoading && <span className="files-row-spinner">…</span>}
      </button>
      {isDir && isOpen && children && (
        <>
          {children.map((child) => (
            <TreeNode
              key={child.path}
              entry={child}
              depth={depth + 1}
              tree={tree}
              expanded={expanded}
              loading={loading}
              selectedPath={selectedPath}
              onToggleDir={onToggleDir}
              onSelectFile={onSelectFile}
            />
          ))}
        </>
      )}
    </>
  );
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

// Highlight occurrences of `needle` in `haystack` (case-insensitive).
function highlight(haystack: string, needle: string) {
  if (!needle) return haystack;
  const lower = haystack.toLowerCase();
  const target = needle.toLowerCase();
  const out: (string | JSX.Element)[] = [];
  let i = 0;
  let key = 0;
  while (i < haystack.length) {
    const found = lower.indexOf(target, i);
    if (found === -1) {
      out.push(haystack.slice(i));
      break;
    }
    if (found > i) out.push(haystack.slice(i, found));
    out.push(
      <mark key={key++} className="files-match-hit">
        {haystack.slice(found, found + target.length)}
      </mark>,
    );
    i = found + target.length;
  }
  return out;
}

export function FilesPanel({
  windowId,
  open,
  onClose,
  row,
  onToggleRow,
}: Props) {
  // Per-window tree cache so switching back to a session reuses fetched dirs.
  const treeRef = useRef<Map<string, Tree>>(new Map());
  const getTree = useCallback((): Tree => {
    let t = treeRef.current.get(windowId);
    if (!t) {
      t = new Map();
      treeRef.current.set(windowId, t);
    }
    return t;
  }, [windowId]);

  // tick is bumped after every tree mutation to force a re-render — using
  // a counter instead of cloning the Map every time keeps deep trees cheap.
  const [, setTick] = useState(0);
  const bump = useCallback(() => setTick((n) => n + 1), []);

  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());
  const [loading, setLoading] = useState<Set<string>>(() => new Set());
  const [filter, setFilter] = useState("");
  // The actual query in flight on the server, separate from the input so
  // the debounce can hold the request without resetting on every keypress.
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<DirEntry[] | null>(null);
  const [searchTruncated, setSearchTruncated] = useState(false);
  const [searching, setSearching] = useState(false);

  const [selected, setSelected] = useState<FileView | null>(null);
  const [selectedLoading, setSelectedLoading] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [editValue, setEditValue] = useState("");
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // For markdown files we default to rendered preview; toggle flips to raw.
  // Reset per file so opening a new file shows its native default.
  const [markdownPreview, setMarkdownPreview] = useState(true);

  // Reset everything when the panel changes window.
  useEffect(() => {
    setExpanded(new Set());
    setLoading(new Set());
    setFilter("");
    setSearchQuery("");
    setSearchResults(null);
    setSearchTruncated(false);
    setSelected(null);
    setError(null);
  }, [windowId]);

  // Debounce filter → searchQuery. 200ms is short enough to feel live but
  // long enough to skip a fetch per keystroke on a 100k-file repo.
  useEffect(() => {
    const trimmed = filter.trim();
    if (!trimmed) {
      setSearchQuery("");
      setSearchResults(null);
      setSearchTruncated(false);
      return;
    }
    const t = window.setTimeout(() => setSearchQuery(trimmed), 200);
    return () => window.clearTimeout(t);
  }, [filter]);

  // Run the search whenever the debounced query changes. The latest-request
  // guard avoids racing an older fetch over a newer one when typing fast.
  useEffect(() => {
    if (!searchQuery) return;
    let cancelled = false;
    setSearching(true);
    setError(null);
    (async () => {
      try {
        const res = await api.searchSessionFiles(windowId, searchQuery);
        if (cancelled) return;
        // Show files first; users care about file results in this view, and
        // walking already visits dirs. Keep dirs visible too — they help
        // when someone is hunting for a folder name.
        setSearchResults(res.matches);
        setSearchTruncated(res.truncated);
      } catch (err) {
        if (cancelled) return;
        setError((err as Error).message);
        setSearchResults([]);
      } finally {
        if (!cancelled) setSearching(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [searchQuery, windowId]);

  const fetchDir = useCallback(
    async (path: string) => {
      setLoading((prev) => {
        const next = new Set(prev);
        next.add(path);
        return next;
      });
      try {
        const res = await api.listSessionFiles(windowId, path);
        getTree().set(path, res.entries);
        bump();
      } catch (err) {
        setError((err as Error).message);
      } finally {
        setLoading((prev) => {
          if (!prev.has(path)) return prev;
          const next = new Set(prev);
          next.delete(path);
          return next;
        });
      }
    },
    [bump, getTree, windowId],
  );

  // Load the root once when the panel opens for this window.
  useEffect(() => {
    if (!open) return;
    if (getTree().has("")) return;
    void fetchDir("");
  }, [fetchDir, getTree, open]);

  const toggleDir = useCallback(
    (path: string) => {
      setExpanded((prev) => {
        const next = new Set(prev);
        if (next.has(path)) {
          next.delete(path);
        } else {
          next.add(path);
          if (!getTree().has(path)) void fetchDir(path);
        }
        return next;
      });
    },
    [fetchDir, getTree],
  );

  const selectFile = useCallback(
    async (entry: DirEntry) => {
      setSelectedLoading(true);
      setError(null);
      setMarkdownPreview(true);
      setEditMode(false);
      setSaveError(null);
      try {
        const res = await api.getSessionFileContent(windowId, entry.path);
        setSelected(res);
        setEditValue(res.content);
      } catch (err) {
        setError((err as Error).message);
        setSelected(null);
      } finally {
        setSelectedLoading(false);
      }
    },
    [windowId],
  );

  const startEdit = useCallback(() => {
    if (!selected || selected.binary || selected.truncated) return;
    setEditValue(selected.content);
    setEditMode(true);
    setSaveError(null);
  }, [selected]);

  const cancelEdit = useCallback(() => {
    if (selected) setEditValue(selected.content);
    setEditMode(false);
    setSaveError(null);
  }, [selected]);

  const saveEdit = useCallback(async () => {
    if (!selected) return;
    setSaving(true);
    setSaveError(null);
    try {
      const res = await api.saveSessionFileContent(
        windowId,
        selected.path,
        editValue,
      );
      setSelected({
        ...selected,
        content: editValue,
        size: res.size,
      });
      setEditMode(false);
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }, [editValue, selected, windowId]);

  const isDirty =
    selected !== null && editMode && editValue !== selected.content;

  // Clicking a directory in search results: clear the search, expand the
  // dir and all its ancestors so the user lands on it in tree view, and
  // prefetch the dir's contents.
  const revealDir = useCallback(
    (path: string) => {
      const ancestors: string[] = [];
      const parts = path.split("/");
      for (let i = 1; i <= parts.length; i += 1) {
        ancestors.push(parts.slice(0, i).join("/"));
      }
      setExpanded((prev) => {
        const next = new Set(prev);
        for (const a of ancestors) next.add(a);
        return next;
      });
      for (const a of ancestors) {
        if (!getTree().has(a)) void fetchDir(a);
      }
      setFilter("");
    },
    [fetchDir, getTree],
  );

  // Drop the cached tree and refetch the root + every dir the user has
  // expanded so the panel reflects whatever the agent (or anything else)
  // wrote to disk since the last load.
  const refreshTree = useCallback(() => {
    const tree = getTree();
    const pathsToReload = ["", ...Array.from(expanded)];
    tree.clear();
    bump();
    for (const path of pathsToReload) {
      void fetchDir(path);
    }
  }, [bump, expanded, fetchDir, getTree]);

  const collapseAll = useCallback(() => {
    setExpanded(new Set());
  }, []);

  const root = getTree().get("");
  const tree = getTree();
  const inSearchMode = searchQuery.length > 0;

  return (
    <aside
      className={`files-panel${open ? " open" : ""}${
        selected ? " viewing" : ""
      }`}
      aria-hidden={!open}
    >
      <header className="files-panel-header">
        <div className="files-panel-title">
          <span>Files</span>
        </div>
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
            {row === "bottom" ? (
              <ArrowUp size={ICON} />
            ) : (
              <ArrowDown size={ICON} />
            )}
          </button>
        )}
        <button
          type="button"
          className="icon-button"
          onClick={onClose}
          aria-label="Close files panel"
          title="Close"
        >
          <X size={ICON} />
        </button>
      </header>

      {selected ? (
        <div className="files-viewer">
          <div className="files-viewer-toolbar">
            <button
              type="button"
              className="files-viewer-back"
              onClick={() => setSelected(null)}
              title="Back to tree"
            >
              ← Back
            </button>
            <span className="files-viewer-path" title={selected.path}>
              {selected.path}
            </span>
            {isMarkdownPath(selected.path) &&
              !selected.binary &&
              !selected.truncated &&
              !editMode && (
                <div
                  className="files-viewer-mode"
                  role="group"
                  aria-label="Markdown view mode"
                >
                  <button
                    type="button"
                    className={markdownPreview ? "active" : ""}
                    onClick={() => setMarkdownPreview(true)}
                  >
                    Preview
                  </button>
                  <button
                    type="button"
                    className={!markdownPreview ? "active" : ""}
                    onClick={() => setMarkdownPreview(false)}
                  >
                    Raw
                  </button>
                </div>
              )}
            <span className="files-viewer-size">{formatSize(selected.size)}</span>
            {!selected.binary && !selected.truncated && !editMode && (
              <button
                type="button"
                className="files-viewer-edit"
                onClick={startEdit}
                title="Edit file"
                aria-label="Edit file"
              >
                Edit
              </button>
            )}
            {editMode && (
              <>
                <button
                  type="button"
                  className="files-viewer-edit"
                  onClick={cancelEdit}
                  disabled={saving}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  className="files-viewer-save"
                  onClick={saveEdit}
                  disabled={!isDirty || saving}
                  title={
                    saving
                      ? "Saving…"
                      : isDirty
                      ? "Save changes (Ctrl/Cmd+S)"
                      : "No changes"
                  }
                >
                  {saving ? "Saving…" : "Save"}
                </button>
              </>
            )}
          </div>
          {saveError && (
            <div className="files-viewer-save-error">{saveError}</div>
          )}
          <div className="files-viewer-body">
            {selectedLoading ? (
              <div className="files-viewer-empty">Loading…</div>
            ) : selected.binary ? (
              <div className="files-viewer-empty">Binary file — not shown.</div>
            ) : selected.truncated ? (
              <div className="files-viewer-empty">
                File is larger than 1 MB — preview disabled.
              </div>
            ) : isMarkdownPath(selected.path) &&
              markdownPreview &&
              !editMode ? (
              <div className="files-viewer-markdown">
                <Markdown text={selected.content} />
              </div>
            ) : editMode ? (
              <CodeViewer
                text={editValue}
                path={selected.path}
                editable
                onChange={setEditValue}
              />
            ) : (
              <CodeViewer text={selected.content} path={selected.path} />
            )}
          </div>
        </div>
      ) : (
        <>
          <div className="files-filter-row">
            <div className="files-filter">
              <Search size={14} aria-hidden="true" />
              <input
                type="text"
                placeholder="Search by name across all files…"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                spellCheck={false}
                autoCorrect="off"
                autoCapitalize="off"
              />
              {filter && (
                <button
                  type="button"
                  className="files-filter-clear"
                  onClick={() => setFilter("")}
                  title="Clear search"
                  aria-label="Clear search"
                >
                  <X size={14} />
                </button>
              )}
            </div>
            <button
              type="button"
              className="files-tool-button"
              onClick={refreshTree}
              title="Refresh from disk"
              aria-label="Refresh file tree"
            >
              <RefreshCw size={14} />
            </button>
            <button
              type="button"
              className="files-tool-button"
              onClick={collapseAll}
              disabled={expanded.size === 0}
              title="Collapse all folders"
              aria-label="Collapse all folders"
            >
              <ChevronsDownUp size={14} />
            </button>
          </div>
          <div className="files-tree">
            {error && <div className="files-error">{error}</div>}

            {inSearchMode ? (
              searching && searchResults === null ? (
                <div className="files-viewer-empty">Searching…</div>
              ) : searchResults && searchResults.length === 0 ? (
                <div className="files-viewer-empty">
                  No matches for “{searchQuery}”.
                </div>
              ) : searchResults ? (
                <>
                  {searchTruncated && (
                    <div className="files-search-note">
                      Showing first {searchResults.length} matches — narrow your
                      query to see more.
                    </div>
                  )}
                  {searchResults.map((m) => (
                    <button
                      type="button"
                      key={m.path}
                      className="files-row files-search-row"
                      onClick={() =>
                        m.type === "dir" ? revealDir(m.path) : selectFile(m)
                      }
                      title={m.path}
                    >
                      <span className="files-row-icon" aria-hidden="true">
                        {m.type === "dir" ? (
                          <Folder size={ICON} />
                        ) : (
                          <FileIcon size={ICON} />
                        )}
                      </span>
                      <span className="files-search-text">
                        <span className="files-search-name">
                          {highlight(m.name, searchQuery)}
                        </span>
                        <span className="files-search-path">
                          {highlight(m.path, searchQuery)}
                        </span>
                      </span>
                    </button>
                  ))}
                </>
              ) : null
            ) : (
              <>
                {!root && !error && (
                  <div className="files-viewer-empty">Loading…</div>
                )}
                {root && root.length === 0 && (
                  <div className="files-viewer-empty">Empty directory.</div>
                )}
                {root &&
                  root.map((entry) => (
                    <TreeNode
                      key={entry.path}
                      entry={entry}
                      depth={0}
                      tree={tree}
                      expanded={expanded}
                      loading={loading}
                      selectedPath={null}
                      onToggleDir={toggleDir}
                      onSelectFile={selectFile}
                    />
                  ))}
              </>
            )}
          </div>
        </>
      )}
    </aside>
  );
}
