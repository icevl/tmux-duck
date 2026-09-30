import { forwardRef, useEffect, useState, type ComponentProps, type ReactNode } from "react";
import { Gauge, Sparkles } from "lucide-react";
import { api, type ModelCatalog } from "../api";
import { formatModel, modelMatch } from "../models";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";

type ModelChange = { model?: string; effort?: string };

interface PickerProps {
  windowId: string;
  model: string | null;
  effort: string | null;
  onSwitch: (change: ModelChange) => Promise<void>;
}

// The small labelled buttons in the composer footer (branch, model, effort).
export const ComposerChip = forwardRef<
  HTMLButtonElement,
  ComponentProps<"button"> & { icon: ReactNode }
>(function ComposerChip({ icon, className, children, ...props }, ref) {
  return (
    <button
      ref={ref}
      type="button"
      data-slot="composer-chip"
      // Survives a Radix trigger replacing data-slot; themes style chips by it.
      data-chip=""
      className={cn(
        "inline-flex h-7 max-w-[14rem] items-center gap-1.5 rounded-md px-2 text-xs text-muted-foreground transition-colors",
        "hover:bg-accent hover:text-accent-foreground data-[state=open]:bg-accent data-[state=open]:text-accent-foreground",
        "focus-visible:ring-2 focus-visible:ring-ring/50 focus-visible:outline-none",
        "[&_svg]:size-3.5 [&_svg]:shrink-0",
        className,
      )}
      {...props}
    >
      {icon}
      <span className="truncate">{children}</span>
    </button>
  );
});

// Catalog fetched on open: Codex's list comes from its own models cache and
// can change between releases.
function useCatalog(windowId: string, open: boolean) {
  const [catalog, setCatalog] = useState<ModelCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setCatalog(null);
    setError(null);
    api
      .listModels(windowId)
      .then((c) => !cancelled && setCatalog(c))
      .catch((err: Error) => !cancelled && setError(err.message));
    return () => {
      cancelled = true;
    };
  }, [open, windowId]);
  return { catalog, error };
}

function useSwitch(onSwitch: PickerProps["onSwitch"], close: () => void) {
  const [switching, setSwitching] = useState<string | null>(null);
  const run = async (key: string, change: ModelChange) => {
    setSwitching(key);
    try {
      await onSwitch(change);
      close();
    } catch {
      // Parent already surfaced the error; keep the menu open for retry.
    } finally {
      setSwitching(null);
    }
  };
  return { switching, run };
}

function CatalogNote({ catalog }: { catalog: ModelCatalog }) {
  return (
    <>
      <DropdownMenuSeparator />
      <p className="px-2 py-1.5 text-[11px] leading-snug text-muted-foreground">
        {catalog.restarts
          ? "Codex restarts the session to switch (history is kept)."
          : "Claude also saves it as the default for new sessions."}
      </p>
    </>
  );
}

function Status({ error }: { error: string | null }) {
  return <p className="px-2 py-1.5 text-xs text-muted-foreground">{error ?? "Loading…"}</p>;
}

// Composer picker for the agent's model.
export function ModelMenu({ windowId, model, onSwitch }: PickerProps) {
  const [open, setOpen] = useState(false);
  const { catalog, error } = useCatalog(windowId, open);
  const { switching, run } = useSwitch(onSwitch, () => setOpen(false));
  return (
    <DropdownMenu open={open} onOpenChange={setOpen} modal={false}>
      <DropdownMenuTrigger asChild>
        <ComposerChip icon={<Sparkles />} title="Switch model">
          {formatModel(model) ?? "Default model"}
        </ComposerChip>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className="w-60">
        <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
          Model
        </DropdownMenuLabel>
        {!catalog && <Status error={error} />}
        {catalog?.models.map((m) => {
          const match = modelMatch(m.id, model);
          return (
            <DropdownMenuItem
              key={m.id}
              // Only a sure match is disabled: a 1M-or-not unknown keeps both
              // context-window variants pickable.
              disabled={match === "exact" || switching !== null}
              onSelect={(e) => {
                e.preventDefault();
                void run(m.id, { model: m.id });
              }}
            >
              <span className="flex w-3 justify-center text-brand">
                {match ? "•" : switching === m.id ? "…" : ""}
              </span>
              <span className={cn(match && "font-medium")}>{m.label}</span>
            </DropdownMenuItem>
          );
        })}
        {catalog && <CatalogNote catalog={catalog} />}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

// Reasoning effort, offered per the current model's supported levels.
export function EffortMenu({ windowId, model, effort, onSwitch }: PickerProps) {
  const [open, setOpen] = useState(false);
  const { catalog, error } = useCatalog(windowId, open);
  const { switching, run } = useSwitch(onSwitch, () => setOpen(false));
  const models = catalog?.models ?? [];
  const efforts =
    (models.find((m) => modelMatch(m.id, model) !== null) ?? models[0])?.efforts ?? [];
  return (
    <DropdownMenu open={open} onOpenChange={setOpen} modal={false}>
      <DropdownMenuTrigger asChild>
        <ComposerChip icon={<Gauge />} title="Switch reasoning effort">
          {effort ?? "Default effort"}
        </ComposerChip>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" side="top" className="w-52">
        <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
          Reasoning effort
        </DropdownMenuLabel>
        {!catalog && <Status error={error} />}
        {catalog && efforts.length === 0 && <Status error="No levels" />}
        {efforts.map((e) => (
          <DropdownMenuItem
            key={e}
            disabled={e === effort || switching !== null}
            onSelect={(ev) => {
              ev.preventDefault();
              void run(e, { effort: e });
            }}
          >
            <span className="flex w-3 justify-center text-brand">
              {e === effort ? "•" : switching === e ? "…" : ""}
            </span>
            <span className={cn("capitalize", e === effort && "font-medium")}>{e}</span>
          </DropdownMenuItem>
        ))}
        {catalog && <CatalogNote catalog={catalog} />}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
