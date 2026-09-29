import {
  Bell,
  BellOff,
  LayoutGrid,
  LogOut,
  Monitor,
  Moon,
  Music,
  Sun,
  UserRound,
  Users,
} from "lucide-react";
import { TunioPlayer } from "tunio-player";
import "tunio-player/styles.css";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import { useTheme, type ThemePreference } from "@/lib/theme";

const OFFICE_STREAM_ID = "71824d03-660b-4722-843a-5e8fbe9ad4c2";

const THEMES: { value: ThemePreference; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
];

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

// Avatar button in the sidebar header with the app menu. The content is
// force-mounted and only hidden while closed: the music player lives in it
// and would stop playing on unmount.
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
  const { preference, resolved, setPreference } = useTheme();
  const themeLabel = THEMES.find((t) => t.value === preference)?.label;

  // What the old footer icons signalled on their own now marks the avatar.
  const alert = accountsNeedSignIn
    ? "Account sign-in needed"
    : attentionCount > 0
      ? `${attentionCount} session${attentionCount === 1 ? "" : "s"} waiting`
      : null;

  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          data-slot="avatar-trigger"
          aria-label="Menu"
          title={alert ?? "Menu"}
          className="relative inline-flex size-9 items-center justify-center rounded-full bg-secondary text-foreground ring-2 ring-brand/70 ring-offset-2 ring-offset-sidebar transition hover:ring-brand data-[state=open]:ring-brand"
        >
          <UserRound className="size-[18px]" />
          {alert && (
            <span
              aria-label={alert}
              className={cn(
                "absolute -top-0.5 -right-0.5 size-2.5 rounded-full ring-2 ring-sidebar",
                accountsNeedSignIn ? "bg-destructive" : "bg-warning",
              )}
            />
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        forceMount
        align="end"
        sideOffset={8}
        collisionPadding={12}
        className="w-64 rounded-xl p-1.5 data-[state=closed]:hidden"
      >
        <DropdownMenuLabel className="flex items-center gap-3 px-2 py-2 font-normal">
          <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-full ring-2 ring-brand/70">
            <UserRound className="size-5" />
          </span>
          <span className="flex min-w-0 flex-col">
            <span className="text-sm font-medium">Signed in</span>
            <span className="truncate text-xs text-muted-foreground">
              {window.location.host}
            </span>
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />

        {/* Not a menu item: the play button toggles the stream in place. */}
        <div className="flex h-10 items-center gap-2 rounded-md px-2 text-sm">
          <Music className="size-4 text-muted-foreground" />
          <span className="flex-1">Office radio</span>
          <TunioPlayer
            id={OFFICE_STREAM_ID}
            theme={resolved}
            buttonOnly
            buttonOnlyClassName="codi-sidebar-play"
            buttonOnlySize={28}
          />
        </div>
        <DropdownMenuItem
          disabled={!notificationsSupported}
          title={notificationTitle}
          onSelect={(e) => {
            e.preventDefault();
            onToggleNotifications();
          }}
        >
          {notificationsEnabled ? <Bell /> : <BellOff />}
          <span className="flex-1">Notifications</span>
          <span className="text-xs text-muted-foreground">
            {!notificationsSupported ? "Unavailable" : notificationsEnabled ? "On" : "Off"}
          </span>
        </DropdownMenuItem>
        <DropdownMenuItem onSelect={onOpenAccounts}>
          <Users />
          <span className="flex-1">Accounts</span>
          {accountsNeedSignIn && (
            <span className="text-xs text-destructive">Sign-in needed</span>
          )}
        </DropdownMenuItem>
        <DropdownMenuItem
          onSelect={onToggleMission}
          className={cn(missionActive && "bg-accent")}
        >
          <LayoutGrid />
          <span className="flex-1">Mission Control</span>
          {attentionCount > 0 && (
            <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-warning px-1.5 text-[11px] font-bold text-black">
              {attentionCount}
            </span>
          )}
        </DropdownMenuItem>
        <DropdownMenuSub>
          <DropdownMenuSubTrigger>
            {preference === "light" ? <Sun /> : preference === "dark" ? <Moon /> : <Monitor />}
            <span className="flex-1">Theme</span>
            <span className="text-xs text-muted-foreground">{themeLabel}</span>
          </DropdownMenuSubTrigger>
          <DropdownMenuSubContent className="rounded-xl p-1.5">
            <DropdownMenuRadioGroup
              value={preference}
              onValueChange={(v) => setPreference(v as ThemePreference)}
            >
              {THEMES.map(({ value, label, icon: Icon }) => (
                <DropdownMenuRadioItem key={value} value={value}>
                  <Icon />
                  {label}
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
          </DropdownMenuSubContent>
        </DropdownMenuSub>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={onLogout}>
          <LogOut />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
