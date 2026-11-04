import {
  Bell,
  ChevronDown,
  BellOff,
  Binary,
  Globe,
  LayoutGrid,
  LogOut,
  Mic,
  Monitor,
  Moon,
  Radar,
  Sparkles,
  Sun,
  Type,
  UserRound,
  Users,
  Zap,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuCheckboxItem,
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
import { Fragment, useState, type ReactNode } from "react";
import { useIsNarrow } from "@/lib/useIsNarrow";
import { applyTextSize, readTextSize, TEXT_SIZES, type TextSize } from "@/lib/textSize";
import {
  DICTATION_LANGUAGES,
  readDictationLanguage,
  saveDictationLanguage,
  type DictationLanguage,
} from "@/lib/dictation";
import {
  GLASS_THEMES,
  isSciFi,
  isRetro,
  RETRO_THEMES,
  SCI_FI_THEMES,
  useTheme,
  type ThemePreference,
} from "@/lib/theme";

// One avatar look for the header button and the menu's own header row.
const AVATAR =
  "inline-flex size-7 items-center justify-center rounded-full bg-secondary text-foreground ring-[1.5px] ring-brand/70";

const THEMES: { value: ThemePreference; label: string; icon: typeof Sun }[] = [
  { value: "light", label: "Light", icon: Sun },
  { value: "dark", label: "Dark", icon: Moon },
  { value: "system", label: "System", icon: Monitor },
  { value: "matrix", label: "The Matrix", icon: Binary },
  { value: "cyberpunk", label: "Cyberpunk", icon: Zap },
  { value: "nostromo", label: "Nostromo", icon: Radar },
  { value: "web1995", label: "Web 1995", icon: Globe },
  { value: "aurora", label: "Aurora Glass", icon: Sparkles },
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

interface MenuSectionProps {
  id: string;
  narrow: boolean;
  openId: string | null;
  onOpenChange: (id: string | null) => void;
  trigger: ReactNode;
  children: ReactNode;
}

// A submenu: a flyout beside the menu on desktop; on a phone, where the menu
// already spans the screen, it expands in place under its row (one at a time).
function MenuSection({ id, narrow, openId, onOpenChange, trigger, children }: MenuSectionProps) {
  if (!narrow) {
    return (
      <DropdownMenuSub>
        <DropdownMenuSubTrigger>{trigger}</DropdownMenuSubTrigger>
        <DropdownMenuSubContent className="rounded-xl p-1.5">{children}</DropdownMenuSubContent>
      </DropdownMenuSub>
    );
  }
  const open = openId === id;
  return (
    <>
      <DropdownMenuItem
        aria-expanded={open}
        onSelect={(e) => {
          e.preventDefault();
          onOpenChange(open ? null : id);
        }}
      >
        {trigger}
        <ChevronDown className={cn("transition-transform", open && "rotate-180")} />
      </DropdownMenuItem>
      {open && <div className="mb-1 ml-4 border-l pl-1">{children}</div>}
    </>
  );
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
  const { preference, setPreference, effects, setEffects } = useTheme();
  const [dictationLang, setDictationLang] = useState(readDictationLanguage);
  const [textSize, setTextSize] = useState(readTextSize);
  // Phones: submenus expand inline (no room beside the menu for a flyout).
  const narrow = useIsNarrow();
  const [openSection, setOpenSection] = useState<string | null>(null);
  const dictationLabel = DICTATION_LANGUAGES.find((l) => l.value === dictationLang)?.label;
  const themeLabel = THEMES.find((t) => t.value === preference)?.label;

  // What the old footer icons signalled on their own now marks the avatar.
  const alert = accountsNeedSignIn
    ? "Account sign-in needed"
    : attentionCount > 0
      ? `${attentionCount} session${attentionCount === 1 ? "" : "s"} waiting`
      : null;

  return (
    <DropdownMenu modal={false} onOpenChange={(open) => !open && setOpenSection(null)}>
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
            <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-warning px-1.5 text-[length:calc(11px*var(--ts,1))] font-bold text-black">
              {attentionCount}
            </span>
          )}
        </DropdownMenuItem>
        <MenuSection
          id="theme"
          narrow={narrow}
          openId={openSection}
          onOpenChange={setOpenSection}
          trigger={
            <>
                {(() => {
                  const Icon = THEMES.find((t) => t.value === preference)?.icon ?? Monitor;
                  return <Icon />;
                })()}
                <span className="flex-1">Theme</span>
                <span className="text-xs text-muted-foreground">{themeLabel}</span>
            </>
          }
        >
            <DropdownMenuRadioGroup
              value={preference}
              onValueChange={(v) => setPreference(v as ThemePreference)}
            >
              {THEMES.map(({ value, label, icon: Icon }) => (
                <Fragment key={value}>
                  {(value === SCI_FI_THEMES[0] ||
                    value === RETRO_THEMES[0] ||
                    value === GLASS_THEMES[0]) && (
                    <>
                      <DropdownMenuSeparator />
                      <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
                        {isSciFi(value) ? "Sci-fi" : isRetro(value) ? "Retro" : "Glass"}
                      </DropdownMenuLabel>
                    </>
                  )}
                  <DropdownMenuRadioItem value={value}>
                    <Icon />
                    {label}
                  </DropdownMenuRadioItem>
                </Fragment>
              ))}
            </DropdownMenuRadioGroup>
            {preference === "matrix" && (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuCheckboxItem
                  checked={effects}
                  onCheckedChange={(on) => setEffects(on === true)}
                  onSelect={(e) => e.preventDefault()}
                >
                  Digital rain
                </DropdownMenuCheckboxItem>
              </>
            )}
        </MenuSection>
        <MenuSection
          id="text-size"
          narrow={narrow}
          openId={openSection}
          onOpenChange={setOpenSection}
          trigger={
            <>
                <Type />
                <span className="flex-1">Text size</span>
                <span className="text-xs text-muted-foreground">
                  {TEXT_SIZES.find((s) => s.value === textSize)?.label}
                </span>
            </>
          }
        >
            <DropdownMenuRadioGroup
              value={textSize}
              onValueChange={(v) => {
                setTextSize(v as TextSize);
                applyTextSize(v as TextSize);
              }}
            >
              {TEXT_SIZES.map((s) => (
                <DropdownMenuRadioItem
                  key={s.value}
                  value={s.value}
                  onSelect={(e) => e.preventDefault()}
                >
                  <span style={{ fontSize: `${Math.round(14 * s.zoom)}px` }}>{s.label}</span>
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
        </MenuSection>
        <MenuSection
          id="dictation"
          narrow={narrow}
          openId={openSection}
          onOpenChange={setOpenSection}
          trigger={
            <>
                <Mic />
                <span className="flex-1">Dictation</span>
                <span className="text-xs text-muted-foreground">
                  {dictationLang === "auto" ? "Auto" : dictationLabel}
                </span>
            </>
          }
        >
            <DropdownMenuLabel className="text-xs font-normal text-muted-foreground">
              Speech language
            </DropdownMenuLabel>
            <DropdownMenuRadioGroup
              value={dictationLang}
              onValueChange={(v) => {
                setDictationLang(v as DictationLanguage);
                saveDictationLanguage(v as DictationLanguage);
              }}
            >
              {DICTATION_LANGUAGES.map((l) => (
                <DropdownMenuRadioItem key={l.value} value={l.value}>
                  {l.label}
                </DropdownMenuRadioItem>
              ))}
            </DropdownMenuRadioGroup>
        </MenuSection>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={onLogout}>
          <LogOut />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
