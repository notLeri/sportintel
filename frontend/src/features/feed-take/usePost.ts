import { useMutation, useQueryClient } from "@tanstack/react-query";

import { eventKeys } from "@/entities/event";
import { feedKeys } from "@/entities/feed";
import { api, unwrap } from "@/shared/api";

const ifMatch = (version: number) => ({ "If-Match": `"${version}"` });

/** «Подготовить пост» из ленты: берёт событие в работу и пишет пост (ИИ — на языке канала). */
export function usePreparePost() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { eventId: string; version: number; mode: "llm" | "template" }) =>
      unwrap(
        api.POST("/api/v1/feed/{event_id}:prepare", {
          params: { path: { event_id: v.eventId } },
          headers: ifMatch(v.version),
          body: { mode: v.mode },
        }),
      ),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: feedKeys.all });
      void qc.invalidateQueries({ queryKey: eventKeys.all });
    },
  });
}

/** «Запланировать» = «Готово» + закрепление в календаре канала. */
export function useSchedulePost() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { eventId: string; version: number; channelId: string; publishAt: string }) =>
      unwrap(
        api.POST("/api/v1/feed/{event_id}:schedule", {
          params: { path: { event_id: v.eventId } },
          headers: ifMatch(v.version),
          body: { channel_id: v.channelId, publish_at: v.publishAt },
        }),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: feedKeys.all });
      void qc.invalidateQueries({ queryKey: eventKeys.all });
      void qc.invalidateQueries({ queryKey: ["channels"] });
    },
  });
}
