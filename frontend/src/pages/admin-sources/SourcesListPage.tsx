import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { useMe } from "@/entities/user";
import { isAppError } from "@/shared/api";
import { formatRelative } from "@/shared/lib/datetime";
import {
  Button,
  Checkbox,
  DataTable,
  HelpTip,
  StatusDot,
  type StatusTone,
  toast,
} from "@/shared/ui";

import { regionName } from "@/shared/lib/region";
import { cn } from "@/shared/lib/utils";
import { type AdminItem, useAdminSources, usePatchSource } from "./queries";

const LIST_HINT: Record<string, string> = {
  tier: "tier",
  owner_group: "owner_group",
  region: "region",
  health: "health",
  active: "active",
};

const HEALTH_TONE: Record<string, StatusTone> = {
  ok: "success",
  degraded: "warn",
  down: "danger",
  unknown: "neutral",
};

// Колонки по содержимому (без переносов); «Название» забирает остальную ширину.
const SHRINK = new Set([
  "tier",
  "owner_group",
  "region",
  "health",
  "last_success",
  "articles_24h",
  "active",
]);
const NUM = new Set(["articles_24h"]);

function ActiveToggle({ s }: { s: AdminItem }) {
  const { t } = useTranslation(["admin", "hints", "enums"]);
  const patch = usePatchSource(s.id);
  return (
    <Checkbox
      aria-label={t("sources.active_for", { name: s.name })}
      checked={s.active}
      onCheckedChange={(c) => {
        if (
          !window.confirm(
            c
              ? t("sources.confirm_on", { name: s.name })
              : t("sources.confirm_off", { name: s.name }),
          )
        )
          return;
        patch.mutate(
          { patch: { active: c === true }, version: s.version },
          { onError: (e) => toast.error(isAppError(e) ? e.title : "") },
        );
      }}
    />
  );
}

const TIERS = ["OFFICIAL", "A", "B", "C", "UNTRUSTED"] as const;

/** Доверие прямо в таблице: действует на статьи, собранные после смены. */
function TierSelect({ s }: { s: AdminItem }) {
  const { t } = useTranslation(["admin", "hints", "enums"]);
  const patch = usePatchSource(s.id);
  return (
    <select
      aria-label={t("sources.tier_for", { name: s.name })}
      title={t("hints:source.tier_inline")}
      disabled={patch.isPending}
      className="border-input hover:border-foreground h-8 rounded-md border bg-transparent px-1.5 text-sm"
      value={s.tier ?? ""}
      onChange={(e) =>
        patch.mutate(
          { patch: { tier: e.target.value || null }, version: s.version },
          {
            onSuccess: () => toast.success(t("sources.tier_saved", { name: s.name })),
            onError: (err) => toast.error(isAppError(err) ? err.title : ""),
          },
        )
      }
    >
      <option value="">—</option>
      {TIERS.map((o) => (
        <option key={o} value={o}>
          {t(`enums:SourceTier.${o}`)}
        </option>
      ))}
    </select>
  );
}

export function SourcesListPage() {
  const { t, i18n } = useTranslation(["admin", "hints", "enums"]);
  const me = useMe();
  const list = useAdminSources();
  if (!me.permissions.includes("sources.manage")) return <p role="alert">{t("forbidden")}</p>;
  return (
    <section aria-labelledby="src-h" className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 id="src-h" className="text-lg font-semibold">
          {t("section.sources")}
        </h2>
        <Button asChild size="sm">
          <Link to="/admin/sources/$sourceId" params={{ sourceId: "new" }}>
            {t("sources.new")}
          </Link>
        </Button>
      </div>
      <DataTable scroll aria-label={t("section.sources")}>
        <thead>
          <tr>
            {[
              "name",
              "domain",
              "tier",
              "owner_group",
              "region",
              "health",
              "last_success",
              "articles_24h",
              "active",
            ].map((c) => (
              <th
                key={c}
                scope="col"
                className={cn(
                  SHRINK.has(c) && "shrink",
                  NUM.has(c) && "num",
                  c === "active" && "text-center!",
                )}
              >
                <span className="inline-flex items-center">
                  {t(`sources.col.${c}`)}
                  {c in LIST_HINT ? <HelpTip text={t(`hints:source.${LIST_HINT[c]}`)} /> : null}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {(list.data?.items ?? []).map((s) => (
            <tr key={s.id} className={cn(!s.active && "text-muted-foreground")}>
              <td className="min-w-44">
                <Link
                  to="/admin/sources/$sourceId"
                  params={{ sourceId: s.id }}
                  className="font-medium hover:underline"
                >
                  {s.name}
                </Link>
              </td>
              <td className="text-muted-foreground">{s.domain}</td>
              <td className="shrink">
                <TierSelect s={s} />
              </td>
              <td className="shrink text-muted-foreground font-mono text-xs">
                {s.owner_group ?? "—"}
              </td>
              <td className="shrink">{regionName(s.region)}</td>
              <td className="shrink">
                <StatusDot tone={HEALTH_TONE[s.health] ?? "neutral"}>
                  {t(`sources.health.${s.health}`)}
                </StatusDot>
              </td>
              <td className="shrink text-muted-foreground">
                {formatRelative(s.last_success_at, new Date(), i18n.language)}
              </td>
              <td className="shrink num">{s.articles_24h ?? "—"}</td>
              <td className="shrink text-center">
                <ActiveToggle s={s} />
              </td>
            </tr>
          ))}
        </tbody>
      </DataTable>
    </section>
  );
}
