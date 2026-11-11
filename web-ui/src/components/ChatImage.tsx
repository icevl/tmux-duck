import { useState } from "react";
import { ExternalLink, ImageOff } from "lucide-react";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

// Raster images the backend will serve inline (/api/image); mirrors
// INLINE_IMAGE_TYPES in web/api.py.
export const IMAGE_PATH_RE = /\.(png|jpe?g|gif|webp)$/i;

/** Where the browser loads an image an agent referenced by host path. */
export function imageUrlForPath(path: string): string {
  return `/api/image?path=${encodeURIComponent(path)}`;
}

/** A host path (or ~/ path) rather than a URL. */
export function isHostPath(src: string): boolean {
  return (src.startsWith("/") && !src.startsWith("/api/")) || src.startsWith("~/");
}

interface Props {
  src: string;
  alt?: string;
  className?: string;
}

// An image in the chat (an agent's screenshot, an attachment): a bounded
// thumbnail that opens full-size in a lightbox.
export function ChatImage({ src, alt, className }: Props) {
  const [open, setOpen] = useState(false);
  const [failed, setFailed] = useState(false);
  const label = alt || src.split(/[/=]/).pop() || "image";

  if (failed) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs text-muted-foreground">
        <ImageOff className="size-3.5" /> {label}
      </span>
    );
  }
  return (
    <>
      <button
        type="button"
        data-slot="chat-image"
        title={label}
        onClick={() => setOpen(true)}
        className={cn(
          "my-1.5 block max-w-full cursor-zoom-in overflow-hidden rounded-lg border bg-muted/40 transition hover:border-foreground/25",
          className,
        )}
      >
        <img
          src={src}
          alt={label}
          loading="lazy"
          onError={() => setFailed(true)}
          className="block max-h-80 w-auto max-w-full object-contain"
        />
      </button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent
          className="flex max-h-[96vh] w-fit max-w-[96vw] flex-col gap-2 p-2 sm:max-w-[96vw]"
          onClick={() => setOpen(false)}
        >
          <DialogTitle className="sr-only">{label}</DialogTitle>
          <img
            src={src}
            alt={label}
            className="max-h-[88vh] w-auto max-w-[calc(96vw-1rem)] cursor-zoom-out rounded-md object-contain"
          />
          <div className="flex items-center justify-between gap-3 px-1 text-xs text-muted-foreground">
            <span className="truncate">{label}</span>
            <a
              href={src}
              target="_blank"
              rel="noopener noreferrer"
              onClick={(e) => e.stopPropagation()}
              className="inline-flex shrink-0 items-center gap-1 hover:text-foreground"
            >
              <ExternalLink className="size-3.5" /> Open original
            </a>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

/** Images attached to a message (screenshots from tool results). */
export function MessageImages({ images }: { images?: string[] | null }) {
  if (!images?.length) return null;
  return (
    <div className="mt-1.5 flex flex-wrap gap-2 font-sans">
      {images.map((src) => (
        <ChatImage key={src} src={src} alt="Screenshot" />
      ))}
    </div>
  );
}
