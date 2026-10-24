import { useMutation, useQueryClient } from "@tanstack/react-query";

import { eventKeys } from "@/entities/event";
import { feedKeys } from "@/entities/feed";
import { api, unwrap } from "@/shared/api";

export function useMerge(eventId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ otherId, version }: { otherId: string; version: number }) =>
      unwrap(
        api.POST("/api/v1/events/{event_id}/merge", {
          params: { path: { event_id: eventId } },
          body: { other_event_id: otherId },
          headers: { "If-Match": `"${version}"` },
        }),
      ),
    onSuccess: (d) => {
      qc.setQueryData(eventKeys.detail(eventId), d);
      void qc.invalidateQueries({ queryKey: eventKeys.all });
      void qc.invalidateQueries({ queryKey: feedKeys.all });
    },
  });
}

export function useMoveArticle(eventId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      articleId,
      targetId,
      version,
    }: {
      articleId: string;
      targetId: string | null;
      version: number;
    }) =>
      unwrap(
        api.POST("/api/v1/events/{event_id}/articles/{article_id}/move", {
          params: { path: { event_id: eventId, article_id: articleId } },
          body: { target_event_id: targetId },
          headers: { "If-Match": `"${version}"` },
        }),
      ),
    onSuccess: (r) => {
      qc.setQueryData(eventKeys.detail(eventId), r.source);
      void qc.invalidateQueries({ queryKey: eventKeys.all });
    },
  });
}
