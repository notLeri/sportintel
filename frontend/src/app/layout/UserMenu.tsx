import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { LogOutIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { logout, useMe } from "@/entities/user";
import {
  type Palette,
  PALETTES,
  setPalette,
  setTheme,
  THEME_PREFS,
  type ThemePref,
  usePalette,
  useTheme,
} from "@/shared/lib/theme";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  Hint,
  HelpTip,
} from "@/shared/ui";

function initials(name: string) {
  const parts = name.split(/[\s@._-]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "?";
}

/** Меню аккаунта: тема, палитра, выход (язык интерфейса — в настройках админа). Квадрат с инициалами — в навигационной полосе. */
export function UserMenu() {
  const me = useMe();
  const { t } = useTranslation(["auth", "enums", "common", "hints"]);
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const theme = useTheme();
  const palette = usePalette();
  const name = me.display_name || me.email;

  async function onLogout() {
    const idpLogout = await logout(queryClient);
    if (idpLogout) window.location.assign(idpLogout);
    else await navigate({ to: "/login" });
  }

  return (
    <DropdownMenu>
      <Hint text={t("hints:account")}>
        <DropdownMenuTrigger
          aria-label={t("common:account")}
          className="bg-brand-bright text-[#0b1220] flex size-11 rounded-full items-center justify-center text-sm font-bold md:mx-auto md:size-12"
        >
          <span aria-hidden>{initials(name)}</span>
          <span className="sr-only">{name}</span>
        </DropdownMenuTrigger>
      </Hint>
      <DropdownMenuContent side="right" align="end" sideOffset={8} className="w-64">
        <DropdownMenuLabel className="space-y-0.5">
          <span className="block truncate">{name}</span>
          <span className="text-muted-foreground block text-xs font-normal">
            {t(`enums:Role.${me.role}`)}
          </span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-muted-foreground text-xs font-normal">
          {t("common:theme.label")}
        </DropdownMenuLabel>
        <DropdownMenuRadioGroup value={theme} onValueChange={(v) => setTheme(v as ThemePref)}>
          {THEME_PREFS.map((p) => (
            <DropdownMenuRadioItem key={p} value={p}>
              {t(`common:theme.${p}`)}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-muted-foreground flex items-center text-xs font-normal">
          {t("common:palette.label")}
          <HelpTip text={t("hints:palette")} />
        </DropdownMenuLabel>
        <DropdownMenuRadioGroup value={palette} onValueChange={(v) => setPalette(v as Palette)}>
          {PALETTES.map((p) => (
            <DropdownMenuRadioItem key={p} value={p} onSelect={(e) => e.preventDefault()}>
              <span
                aria-hidden
                data-palette-swatch={p}
                className="ring-border size-3.5 rounded-full ring-1"
              />
              {t(`common:palette.${p}`)}
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => void onLogout()}>
          <LogOutIcon aria-hidden />
          {t("auth:logout")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
