import { ModalShell } from "./ModalShell";
interface Props {
  title: string;
  body?: string;
  confirmLabel?: string;
  danger?: boolean;
  onConfirm: () => void | Promise<void>;
  onCancel: () => void;
}

export function ConfirmDialog({
  title,
  body,
  confirmLabel = "OK",
  danger,
  onConfirm,
  onCancel,
}: Props) {
  return (
    <ModalShell title={title} onClose={onCancel}>
        {body && <p style={{ color: "var(--text-1)" }}>{body}</p>}
        <div className="modal-actions">
          <button onClick={onCancel}>Cancel</button>
          <button
            className={danger ? "danger" : "primary"}
            onClick={() => onConfirm()}
          >
            {confirmLabel}
          </button>
        </div>
      </ModalShell>
  );
}
