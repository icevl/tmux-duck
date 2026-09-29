import { ModalShell } from "./ModalShell";
import { useEffect, useState } from "react";
import { api } from "../api";

interface Props {
  windowId: string;
  onClose: () => void;
}

export function ScreenshotModal({ windowId, onClose }: Props) {
  const [bust, setBust] = useState(Date.now());

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const url = `${api.screenshotUrl(windowId)}&_=${bust}`;

  return (
    <ModalShell title="Screenshot" onClose={onClose} className="screenshot-modal sm:max-w-[1000px]">
        <img src={url} alt="Terminal screenshot" />
        <div className="modal-actions">
          <button onClick={() => setBust(Date.now())}>↻ Refresh</button>
          <button className="primary" onClick={onClose}>
            Close
          </button>
        </div>
      </ModalShell>
  );
}
