import type { ReactNode } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

interface ModalShellProps {
  title: ReactNode;
  description?: ReactNode;
  onClose: () => void;
  className?: string;
  children: ReactNode;
}

// Every app dialog: shadcn Dialog (focus trap, Esc, overlay click, mobile
// full-width) around the dialog's own rows and `.modal-actions` footer.
// Mounted only while shown, so it is always open.
export function ModalShell({
  title,
  description,
  onClose,
  className,
  children,
}: ModalShellProps) {
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent
        className={cn(
          "max-h-[calc(100dvh-2rem)] gap-4 overflow-y-auto rounded-2xl sm:max-w-[440px]",
          className,
        )}
        onOpenAutoFocus={(e) => {
          // Let the dialog's own autoFocus field win over Radix's first-focusable.
          if ((e.currentTarget as HTMLElement).querySelector("[autofocus]")) {
            e.preventDefault();
          }
        }}
      >
        <DialogTitle className="pr-6 text-lg font-semibold tracking-tight">
          {title}
        </DialogTitle>
        {description ? (
          <DialogDescription>{description}</DialogDescription>
        ) : (
          <DialogDescription className="sr-only">{title}</DialogDescription>
        )}
        {children}
      </DialogContent>
    </Dialog>
  );
}
