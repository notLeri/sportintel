import { useMutation, useQueryClient } from "@tanstack/react-query";

import { draftKeys } from "@/entities/draft";
import { eventKeys } from "@/entities/event";
import { feedKeys } from "@/entities/feed";
import { api, unwrap } from "@/shared/api";
import { newIdempotencyKey } from "@/shared/lib/idempotency";

export type DraftMode = "template" | "llm" | "empty" | "brief";
export type PostLang = "ru" | "en";

export function useGenerateDraft(eventId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      mode,
      draftId,
      lang,
    }: {
      mode: DraftMode;
      draftId?: string;
      lang?: PostLang;
    }) =>
      draftId
        ? unwrap(
            api.POST("/api/v1/drafts/{draft_id}:regenerate", {
              params: { path: { draft_id: draftId } },
              body: { mode: mode === "empty" ? null : mode, lang },
            }),
          )
        : unwrap(
            api.POST("/api/v1/events/{event_id}/drafts", {
              params: { path: { event_id: eventId } },
              body: { mode, lang },
              headers: { "Idempotency-Key": newIdempotencyKey() },
            }),
          ),
    onSuccess: (d) => {
      qc.setQueryData(draftKeys.detail(d.id), d);
      void qc.invalidateQueries({ queryKey: eventKeys.detail(eventId) });
      void qc.invalidateQueries({ queryKey: feedKeys.all });
    },
  });
}

export interface SaveVars {
  version: number;
  body_tg_html: string;
  image_url: string | null;
}

/** Сохранение версии — не оптимистичное (FE-T3.12 §7). */
export function useSaveDraft(draftId: string, eventId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ version, ...body }: SaveVars) =>
      unwrap(
        api.PATCH("/api/v1/drafts/{draft_id}", {
          params: { path: { draft_id: draftId } },
          // дисклеймер в пост не входит, убирать его нечего
          body: { ...body, disclaimer_removed: false },
          headers: { "If-Match": `"${version}"` },
        }),
      ),
    onSuccess: (d) => {
      qc.setQueryData(draftKeys.detail(draftId), d);
      void qc.invalidateQueries({ queryKey: eventKeys.detail(eventId) });
      void qc.invalidateQueries({ queryKey: [...eventKeys.all, "list"] });
      void qc.invalidateQueries({ queryKey: feedKeys.all });
    },
  });
}

/** Перевод текущей версии на ru/en → новая версия; одинаковый текст сервер переводит один раз. */
export function useTranslateDraft(draftId: string, eventId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (lang: PostLang) =>
      unwrap(
        api.POST("/api/v1/drafts/{draft_id}:translate", {
          params: { path: { draft_id: draftId } },
          body: { lang },
        }),
      ),
    onSuccess: (d) => {
      qc.setQueryData(draftKeys.detail(draftId), d);
      void qc.invalidateQueries({ queryKey: eventKeys.detail(eventId) });
    },
  });
}

/** «Одобрить» текущий вариант поста («Готово») — из любого статуса до «Готово», в т. ч. новое событие. */
export function useApprovePost() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { eventId: string; version: number }) =>
      unwrap(
        api.POST("/api/v1/feed/{event_id}:approve", {
          params: { path: { event_id: v.eventId } },
          headers: { "If-Match": `"${v.version}"` },
        }),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: feedKeys.all });
      void qc.invalidateQueries({ queryKey: eventKeys.all });
      void qc.invalidateQueries({ queryKey: ["channels"] });
    },
  });
}
