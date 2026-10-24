// i18n-ns: event — t передаётся из HistoryTab (useTranslation(["event", "enums"])).
import type { TFunction } from "i18next";

import type { components } from "@/shared/api";

export type AuditEntry = components["schemas"]["AuditEntryItem"];

// Каталог BE-T3.1 AuditAction: у каждого действия есть перевод history.actions.<action>.
export const AUDIT_ACTIONS = [
  "auth.login",
  "auth.logout",
  "auth.login_denied",
  "source.created",
  "source.updated",
  "article.manual_added",
  "event.created_manual",
  "event.edited",
  "event.transitioned",
  "event.summary_regenerate_requested",
  "event.relevance_overridden",
  "event.reliability_overridden",
  "event.merged",
  "event.article_moved",
  "event.conflict_resolved",
  "draft.generation_requested",
  "draft.saved",
  "draft.copied",
  "draft.disclaimer_removed",
  "settings.updated",
  "user.created",
  "user.updated",
  "taxonomy.sport_created",
  "taxonomy.sport_updated",
  "taxonomy.entity_created",
  "taxonomy.entity_updated",
  "taxonomy.alias_added",
  "taxonomy.alias_removed",
  "taxonomy.unlinked_resolved",
  "pipeline.retried",
] as const;

const str = (v: unknown) => (v === null || v === undefined ? "" : String(v));

/** Человекочитаемое описание записи аудита на языке UI (FE-T4.7). */
export function describeAction(e: AuditEntry, t: TFunction): string {
  const who = e.actor?.name ?? t("history.system");
  const before = (e.before ?? {}) as Record<string, unknown>;
  const after = (e.after ?? {}) as Record<string, unknown>;
  const vars: Record<string, string> = { who, reason: e.reason ?? "" };
  if (e.action === "event.transitioned") {
    vars.from = t(`enums:EventStatus.${str(before.status)}`, { defaultValue: str(before.status) });
    vars.to = t(`enums:EventStatus.${str(after.status)}`, { defaultValue: str(after.status) });
    if (after.status === "REJECTED") {
      const reason = t(`enums:RejectionReason.${str(after.rejection_reason)}`, {
        defaultValue: str(after.rejection_reason),
      });
      return t("history.actions.event.rejected", {
        who,
        reason,
        comment: after.rejection_comment ? ` — ${str(after.rejection_comment)}` : "",
      });
    }
  }
  if (e.action === "event.edited")
    vars.fields = Object.keys(after)
      .map((f) => t(`edit.fields.${f}`, { defaultValue: f }))
      .join(", ");
  if (e.action === "event.merged")
    vars.count = String(((after.articles as unknown[]) ?? []).length);
  if (e.action === "draft.saved" || e.action === "draft.copied")
    vars.n = str(after.n ?? after.version_n);
  if (e.action === "event.relevance_overridden" || e.action === "event.reliability_overridden")
    vars.level = str(after.level) || t("history.auto");
  return t(`history.actions.${e.action}`, vars);
}
