import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, type ModelCatalog } from "../api";
import { formatModel, isCurrentModel, modelMatch } from "../models";

type ModelChange = { model?: string; effort?: string };

interface PickerProps {
  windowId: string;
  model: string | null;
  effort: string | null;
  onSwitch: (change: ModelChange) => Promise<void>;
}

// Popover state shared by the model and effort pickers: open/close on
// outside click or Escape (like the branch popover), and the catalog fetched
// on open (Codex's list comes from its own models cache and can change
// between releases).
function usePicker(windowId: string, onSwitch: PickerProps["onSwitch"]) {
  const [open, setOpen] = useState(false);
  const [catalog, setCatalog] = useState<ModelCatalog | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [switching, setSwitching] = useState<string | null>(null);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setCatalog(null);
    setLoadError(null);
    api
      .listModels(windowId)
      .then((c) => {
        if (!cancelled) setCatalog(c);
      })
      .catch((err: Error) => {
        if (!cancelled) setLoadError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [open, windowId]);

  useEffect(() => {
    if (!open) return;
    const onDocClick = (e: MouseEvent) => {
      const el = ref.current;
      if (el && !el.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: globalThis.KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  const switchTo = async (key: string, change: ModelChange) => {
    setSwitching(key);
    try {
      await onSwitch(change);
      setOpen(false);
    } catch {
      // Parent already surfaced the error; keep the menu open for retry.
    } finally {
      setSwitching(null);
    }
  };

  return { open, setOpen, catalog, loadError, switching, switchTo, ref };
}

function PickerShell({
  picker,
  className,
  title,
  label,
  children,
}: {
  picker: ReturnType<typeof usePicker>;
  className: string;
  title: string;
  label: string;
  children: ReactNode;
}) {
  const { open, setOpen, catalog, loadError, ref } = picker;
  return (
    <div className={`branch-menu ${className}${open ? " open" : ""}`} ref={ref}>
      <button
        type="button"
        className="branch-button"
        aria-haspopup="listbox"
        aria-expanded={open}
        title={title}
        onClick={() => setOpen((v) => !v)}
      >
        {label}
      </button>
      {open && (
        <div className="branch-menu-popover" role="listbox">
          {catalog === null ? (
            <div className="branch-menu-empty">{loadError ?? "Loading…"}</div>
          ) : (
            <>
              {children}
              <div className="model-menu-note">
                {catalog.restarts
                  ? "Codex restarts the session to switch (history is kept)."
                  : "Claude also saves it as the default for new sessions."}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function PickerItem({
  label,
  isCurrent,
  isSwitching,
  disabled,
  onPick,
}: {
  label: string;
  isCurrent: boolean;
  isSwitching: boolean;
  disabled: boolean;
  onPick: () => void;
}) {
  return (
    <button
      type="button"
      role="option"
      aria-selected={isCurrent}
      className={`branch-menu-item${isCurrent ? " current" : ""}`}
      disabled={disabled}
      onClick={onPick}
    >
      <span className="branch-menu-mark">
        {isCurrent ? "•" : isSwitching ? "…" : ""}
      </span>
      <span className="branch-menu-name">{label}</span>
    </button>
  );
}

// Composer popover next to the branch switcher: the agent's model.
export function ModelMenu({ windowId, model, onSwitch }: PickerProps) {
  const picker = usePicker(windowId, onSwitch);
  return (
    <PickerShell
      picker={picker}
      className="model-menu"
      title="Switch model"
      label={`model: ${formatModel(model) ?? "default"}`}
    >
      {picker.catalog?.models.map((m) => {
        const match = modelMatch(m.id, model);
        return (
          <PickerItem
            key={m.id}
            label={m.label}
            isCurrent={match !== null}
            isSwitching={picker.switching === m.id}
            // Only a sure match is disabled: a 1M-or-not unknown keeps both
            // context-window variants pickable.
            disabled={match === "exact" || picker.switching !== null}
            onPick={() => void picker.switchTo(m.id, { model: m.id })}
          />
        );
      })}
    </PickerShell>
  );
}

// Reasoning effort, offered per the current model's supported levels.
export function EffortMenu({ windowId, model, effort, onSwitch }: PickerProps) {
  const picker = usePicker(windowId, onSwitch);
  const models = picker.catalog?.models ?? [];
  const efforts =
    (models.find((m) => isCurrentModel(m.id, model)) ?? models[0])?.efforts ?? [];
  return (
    <PickerShell
      picker={picker}
      className="effort-menu"
      title="Switch reasoning effort"
      label={`effort: ${effort ?? "default"}`}
    >
      {efforts.length === 0 && <div className="branch-menu-empty">No levels</div>}
      {efforts.map((e) => (
        <PickerItem
          key={e}
          label={e}
          isCurrent={e === effort}
          isSwitching={picker.switching === e}
          disabled={e === effort || picker.switching !== null}
          onPick={() => void picker.switchTo(e, { effort: e })}
        />
      ))}
    </PickerShell>
  );
}
