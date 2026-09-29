import {
  Bell,
  Binary,
  BellOff,
  LayoutGrid,
  LogOut,
  Monitor,
  Moon,
  Sun,
  UserRound,
  Users,
} from "lucide-react";
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

// One avatar look for the header button and the menu's own header row.
const AVATAR =
  "inline-flex size-7 items-center justify-center rounded-full bg-secondary text-foreground ring-[1.5px] ring-brand/70";

const THEMES: { value: ThemePreference; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
  { value: "matrix", label: "The Matrix", icon: Binary },
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

// Avatar button in the sidebar header with the app menu.
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
  const { preference, setPreference } = useTheme();
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
          className={cn(AVATAR, "relative transition hover:ring-brand data-[state=open]:ring-brand")}
        >
          <UserRound className="size-3.5" />
          {alert && (
            <span
              aria-label={alert}
              className={cn(
                "absolute -top-0.5 -right-0.5 size-2 rounded-full ring-2 ring-sidebar",
                accountsNeedSignIn ? "bg-destructive" : "bg-warning",
              )}
            />
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="end"
        sideOffset={8}
        collisionPadding={12}
        className="w-64 rounded-xl p-1.5"
      >
        <DropdownMenuLabel className="flex items-center gap-3 px-2 py-2 font-normal">
          <span className={cn(AVATAR, "shrink-0")}>
            <UserRound className="size-3.5" />
          </span>
          <span className="flex min-w-0 flex-col">
            <span className="text-sm font-medium">Signed in</span>
            <span className="truncate text-xs text-muted-foreground">
              {window.location.host}
            </span>
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />

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
            {(() => {
              const Icon = THEMES.find((t) => t.value === preference)?.icon ?? Monitor;
              return <Icon />;
            })()}
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
