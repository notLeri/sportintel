import { Link } from "@tanstack/react-router";
import {
  CalendarClockIcon,
  ChartColumnIcon,
  FileTextIcon,
  LayersIcon,
  SendIcon,
  SettingsIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { can, useMe } from "@/entities/user";
import { BrandMark, Hint } from "@/shared/ui";

import { UserMenu } from "./UserMenu";

const ITEMS = [
  { to: "/", key: "nav.events", perm: null, icon: LayersIcon },
  { to: "/feed", key: "nav.feed", perm: null, icon: SendIcon },
  { to: "/articles", key: "nav.articles", perm: null, icon: FileTextIcon },
  { to: "/autopost", key: "nav.autopost", perm: "channels.manage", icon: CalendarClockIcon },
  { to: "/analytics", key: "nav.analytics", perm: "analytics.read", icon: ChartColumnIcon },
  { to: "/admin", key: "nav.admin", perm: "settings.manage", icon: SettingsIcon },
] as const;

/**
 * Навигация: на десктопе — вертикальная тёмная полоса слева (фон логотипа),
 * на телефоне — та же полоса сверху. Подпись под каждой иконкой: на касании подсказок нет.
 */
export function AppNav() {
  const { t } = useTranslation(["common", "hints"]);
  const me = useMe();
  const items = ITEMS.filter((item) => item.perm === null || can(me, item.perm));
  return (
    <nav
      aria-label={t("nav.main")}
      className="bg-rail text-rail-foreground dark:border-border sticky top-0 z-40 flex h-16 items-center gap-1 px-1.5 md:h-dvh md:w-22 md:flex-col dark:md:border-r md:gap-1 md:px-0 md:py-3"
    >
      <Link
        to="/"
        className="flex shrink-0 items-center gap-2 px-1.5 text-white md:mb-4 md:px-0"
        aria-label={t("app.name")}
      >
        <BrandMark animated className="h-7 md:h-8" />
        <span className="font-display hidden text-sm font-bold lg:hidden">{t("app.name")}</span>
      </Link>
      <ul className="flex min-w-0 flex-1 justify-around gap-0.5 overflow-x-auto md:flex-none md:flex-col md:justify-start md:overflow-visible">
        {items.map(({ to, key, icon: Icon }) => (
          <li key={to}>
            <Hint text={t(`hints:${key}`)}>
              <Link
                to={to}
                activeOptions={{ exact: to === "/", includeSearch: false }}
                className="group/nav flex transition-colors duration-150 h-14 min-w-14 flex-col items-center justify-center gap-0.5 rounded-md px-1 text-[10px] leading-tight font-semibold hover:bg-white/6 hover:text-white md:h-16 md:w-18 md:gap-1 md:text-[11px]"
                activeProps={{
                  className: "bg-white/10 text-white",
                  "aria-current": "page",
                }}
              >
                <Icon
                  aria-hidden
                  strokeWidth={2.25}
                  className="size-5 shrink-0 group-aria-[current=page]/nav:text-brand-bright"
                />
                <span className="text-center">{t(key)}</span>
              </Link>
            </Hint>
          </li>
        ))}
      </ul>
      <div className="shrink-0 md:mt-auto">
        <UserMenu />
      </div>
    </nav>
  );
}
