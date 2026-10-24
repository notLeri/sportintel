import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { TelegramPreview } from "@/entities/draft";
import type { EventDetail } from "@/entities/event";
import { can, useMe } from "@/entities/user";
import { api, isAppError, unwrap } from "@/shared/api";
import { formatDateTime, formatRelative } from "@/shared/lib/datetime";
import { AiContentMark, Badge, Button, HelpTip, Hint } from "@/shared/ui";

const LANGS = ["ru", "en", "pt-BR"] as const;
type BriefLang = (typeof LANGS)[number];
const POLL_MS = 3000;
const POLL_LIMIT_MS = 180_000; // локальная модель: до ~30 с на бриф, плюс очередь

/** 404 — брифа ещё нет: это не ошибка, а пустое состояние. */
async function fetchBrief(eventId: string, lang: BriefLang) {
  try {
    return await unwrap(
      api.GET("/api/v1/events/{event_id}/briefs/{lang}", {
        params: { path: { event_id: eventId, lang } },
      }),
    );
  } catch (e) {
    if (isAppError(e) && e.status === 404) return null;
    throw e;
  }
}

export function BriefPanel({ event }: { event: EventDetail }) {
  const { t, i18n } = useTranslation(["event", "hints"]);
  const me = useMe();
  const [lang, setLang] = useState<BriefLang>(i18n.language === "ru" ? "ru" : "en");
  const [polling, setPolling] = useState(false);
  const q = useQuery({
    queryKey: ["brief", event.id, lang],
    queryFn: () => fetchBrief(event.id, lang),
    staleTime: 30_000,
    // Опрос только после «Сгенерировать», пока бриф не появится или не выйдет время.
    refetchInterval: polling ? POLL_MS : false,
  });
  const gen = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/events/{event_id}/briefs/{lang}:generate", {
          params: { path: { event_id: event.id, lang } },
        }),
      ),
    onSuccess: () => setPolling(true),
  });
  const b = q.data;
  // Опрос после «Сгенерировать»: до появления брифа или до лимита времени.
  useEffect(() => {
    if (b && polling) setPolling(false);
  }, [b, polling]);
  useEffect(() => {
    if (!polling) return;
    const timer = setTimeout(() => setPolling(false), POLL_LIMIT_MS);
    return () => clearTimeout(timer);
  }, [polling]);
  const waiting = polling && !b;
  const unavailable = isAppError(gen.error) && gen.error.status === 422;

  return (
    <section aria-label={t("brief.title")} className="space-y-3 border-t pt-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-medium">
          {t("brief.title")}
          <HelpTip text={t("hints:event.brief")} />
        </h3>
        <Hint text={t("hints:event.brief_lang")}>
          <select
            aria-label={t("brief.language")}
            value={lang}
            onChange={(e) => {
              setLang(e.target.value as BriefLang);
              setPolling(false);
            }}
            className="rounded-md border bg-background px-2 py-1 text-sm"
          >
            {LANGS.map((l) => (
              <option key={l} value={l}>
                {t(`brief.lang.${l}`)}
              </option>
            ))}
          </select>
        </Hint>
        {can(me, "drafts.write") ? (
          <Hint text={t(b ? "hints:event.brief_regenerate" : "hints:event.brief_generate")}>
            <Button
              size="sm"
              variant={b ? "outline" : "default"}
              disabled={gen.isPending || waiting}
              onClick={() => gen.mutate()}
            >
              {waiting ? t("brief.generating") : b ? t("brief.regenerate") : t("brief.generate")}
            </Button>
          </Hint>
        ) : null}
      </div>

      {unavailable ? (
        <p role="status" className="text-muted-foreground text-sm">
          {t("brief.ai_unavailable")}
        </p>
      ) : null}
      {q.isError ? (
        <p role="alert" className="text-destructive text-sm">
          {t("brief.load_failed")}
        </p>
      ) : null}
      {!b && !q.isPending && !waiting && !unavailable ? (
        <p className="text-muted-foreground text-sm">{t("brief.empty")}</p>
      ) : null}
      {waiting ? (
        <p aria-busy="true" className="text-muted-foreground text-sm">
          {t("brief.waiting")}
        </p>
      ) : null}

      {b ? (
        <div className="grid gap-3 lg:grid-cols-2">
          <div className="space-y-2 text-sm">
            <AiContentMark variant="block" />
            {b.stale ? (
              <p className="bg-warn-bg text-warn px-2 py-1 text-xs">{t("brief.stale")}</p>
            ) : null}
            <p className="font-medium">{b.brief.headline}</p>
            <p className="flex flex-wrap items-center gap-1">
              <Hint text={t(`hints:brief_status.${b.brief.status}`)}>
                <Badge variant="secondary">{t(`brief.status.${b.brief.status}`)}</Badge>
              </Hint>
              <span className="text-muted-foreground">
                {formatDateTime(event.occurred_at, me.timezone)}
              </span>
            </p>
            <p>{b.brief.summary.join(" ")}</p>
            <Field label={t("brief.affected")} hint={t("hints:event.brief_affected")}>
              {(b.brief.affected ?? []).join(", ") || "—"}
            </Field>
            <Field label={t("brief.impact")} hint={t("hints:event.brief_impact")}>
              {b.brief.impact || "—"}
            </Field>
            {b.brief.actions?.length ? (
              <Field label={t("brief.actions")} hint={t("hints:event.brief_actions")}>
                <ul className="list-disc pl-5">
                  {b.brief.actions.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              </Field>
            ) : null}
            <Field label={t("brief.sources")} hint={t("hints:event.brief_sources")}>
              <span className="flex flex-wrap gap-x-2">
                {b.brief.source_refs.map((n) => {
                  const s = b.sources.find((x) => x.n === n);
                  return s ? (
                    <a
                      key={n}
                      href={s.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="underline"
                    >
                      {s.name}
                    </a>
                  ) : null;
                })}
              </span>
            </Field>
            <p className="text-muted-foreground text-xs">
              {t("brief.meta", {
                model: b.model,
                when: formatRelative(b.created_at),
              })}
            </p>
          </div>
          <TelegramPreview
            tgHtml={b.tg_html}
            imageUrl={null}
            channelName={t("draft_panel.preview")}
          />
        </div>
      ) : null}
    </section>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <span className="font-medium">
        {label}
        <HelpTip text={hint} />:
      </span>{" "}
      {children}
    </div>
  );
}
