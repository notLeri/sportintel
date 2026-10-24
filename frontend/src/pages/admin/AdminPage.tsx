import { Link, Navigate, Outlet, useLocation } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { useMe } from "@/entities/user";
import { Placeholder } from "@/shared/ui";

// Первый доступный раздел открывается по «Управлению»: обычно «Обработка»
const SECTIONS = [
  { to: "/admin/pipeline", perm: "pipeline.manage", key: "pipeline" },
  { to: "/admin/sources", perm: "sources.manage", key: "sources" },
  { to: "/admin/relevance", perm: "settings.manage", key: "relevance" },
  { to: "/admin/taxonomy", perm: "taxonomy.manage", key: "taxonomy" },
  { to: "/admin/settings", perm: "settings.manage", key: "settings" },
  { to: "/admin/users", perm: "users.manage", key: "users" },
] as const;

/** Оболочка админки: разделы по правам пользователя. */
export function AdminPage() {
  const { t } = useTranslation(["admin", "common"]);
  const me = useMe();
  const sections = SECTIONS.filter((s) => me.permissions.includes(s.perm));
  const { pathname } = useLocation();
  const first = sections[0];
  if (first && pathname.replace(/\/$/, "") === "/admin") return <Navigate to={first.to} replace />;
  return (
    <div className="mx-auto max-w-[120rem] space-y-4 p-6 xl:px-8">
      <h1 className="font-display text-2xl font-bold">{t("common:nav.admin")}</h1>
      <nav aria-label={t("sections")} className="flex flex-wrap gap-2 border-b pb-2">
        {sections.map((s) => (
          <Link
            key={s.to}
            to={s.to}
            className="hover:bg-accent data-[status=active]:bg-secondary data-[status=active]:text-foreground rounded-md px-2.5 py-1.5 text-sm font-medium"
          >
            {t(`section.${s.key}`)}
          </Link>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}

/** Раздел ещё не реализован. */
export function AdminSectionPlaceholder() {
  const { t } = useTranslation("common");
  return <Placeholder title={t("placeholder.title")} />;
}
