import { useEffect, useRef, useState } from "react";
import {
  Bell,
  BellOff,
  LayoutGrid,
  LogOut,
  Music,
  UserRound,
  Users,
} from "lucide-react";
import { TunioPlayer } from "tunio-player";
import "tunio-player/styles.css";

const ICON = 18;
const OFFICE_STREAM_ID = "71824d03-660b-4722-843a-5e8fbe9ad4c2";

interface UserMenuProps {
  missionActive: boolean;
  attentionCount: number;
  onToggleMission: () => void;
  onOpenAccounts: () => void;
  accountsNeedSignIn: boolean;
  onLogout: () => void;
  notificationsSupported: boolean;
  notificationsEnabled: boolean;
  notificationTitle: string;
  onToggleNotifications: () => void;
}

// Avatar button in the sidebar header with the app menu (music, alerts,
// accounts, Mission Control, sign out). The popover stays mounted while
// closed: the music player lives in it and would stop on unmount.
export function UserMenu({
  missionActive,
  attentionCount,
  onToggleMission,
  onOpenAccounts,
  accountsNeedSignIn,
  onLogout,
  notificationsSupported,
  notificationsEnabled,
  notificationTitle,
  onToggleNotifications,
}: UserMenuProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

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

  const run = (action: () => void) => () => {
    setOpen(false);
    action();
  };

  // What the footer icons used to signal on their own now marks the avatar.
  const alert = accountsNeedSignIn
    ? "Account sign-in needed"
    : attentionCount > 0
      ? `${attentionCount} session${attentionCount === 1 ? "" : "s"} waiting`
      : null;

  return (
    <div className={`user-menu${open ? " open" : ""}`} ref={ref}>
      <button
        type="button"
        className="user-menu-avatar"
        aria-haspopup="menu"
        aria-expanded={open}
        title={alert ?? "Menu"}
        aria-label="Menu"
        onClick={() => setOpen((v) => !v)}
      >
        <UserRound size={ICON} />
        {alert && (
          <span
            className={`user-menu-dot${accountsNeedSignIn ? " danger" : ""}`}
            aria-label={alert}
          />
        )}
      </button>
      <div className="user-menu-popover" role="menu" hidden={!open}>
        <div className="user-menu-head">
          <span className="user-menu-head-avatar">
            <UserRound size={20} />
          </span>
          <span className="user-menu-head-text">
            <span className="user-menu-head-title">Signed in</span>
            <span className="user-menu-head-sub">{window.location.host}</span>
          </span>
        </div>

        <div className="user-menu-section">
          <div className="user-menu-item user-menu-static">
            <Music size={ICON} />
            <span className="user-menu-label">Office radio</span>
            <TunioPlayer
              id={OFFICE_STREAM_ID}
              theme="dark"
              buttonOnly
              buttonOnlyClassName="codi-sidebar-play"
              buttonOnlySize={28}
            />
          </div>
          <button
            type="button"
            role="menuitemcheckbox"
            aria-checked={notificationsEnabled}
            className="user-menu-item"
            title={notificationTitle}
            disabled={!notificationsSupported}
            onClick={onToggleNotifications}
          >
            {notificationsEnabled ? <Bell size={ICON} /> : <BellOff size={ICON} />}
            <span className="user-menu-label">Notifications</span>
            <span className="user-menu-value">
              {!notificationsSupported ? "Unavailable" : notificationsEnabled ? "On" : "Off"}
            </span>
          </button>
          <button
            type="button"
            role="menuitem"
            className="user-menu-item"
            onClick={run(onOpenAccounts)}
          >
            <Users size={ICON} />
            <span className="user-menu-label">Accounts</span>
            {accountsNeedSignIn && (
              <span className="user-menu-value danger">Sign-in needed</span>
            )}
          </button>
          <button
            type="button"
            role="menuitemcheckbox"
            aria-checked={missionActive}
            className={`user-menu-item${missionActive ? " active" : ""}`}
            onClick={run(onToggleMission)}
          >
            <LayoutGrid size={ICON} />
            <span className="user-menu-label">Mission Control</span>
            {attentionCount > 0 && (
              <span className="user-menu-badge">{attentionCount}</span>
            )}
          </button>
        </div>

        <div className="user-menu-section">
          <button
            type="button"
            role="menuitem"
            className="user-menu-item"
            onClick={run(onLogout)}
          >
            <LogOut size={ICON} />
            <span className="user-menu-label">Sign out</span>
          </button>
        </div>
      </div>
    </div>
  );
}
