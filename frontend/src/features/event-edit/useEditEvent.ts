import { useMutation, useQueryClient } from "@tanstack/react-query";

import { eventKeys } from "@/entities/event";
import { api, unwrap } from "@/shared/api";

export function useEditEvent(eventId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ patch, version }: { patch: Record<string, unknown>; version: number }) =>
      unwrap(
        api.PATCH("/api/v1/events/{event_id}", {
          params: { path: { event_id: eventId } },
          body: patch,
          headers: { "If-Match": `"${version}"` },
        }),
      ),
    onSuccess: (d) => {
      qc.setQueryData(eventKeys.detail(eventId), d);
      void qc.invalidateQueries({ queryKey: [...eventKeys.all, "list"] });
    },
  });
}

export function useRegenerateSummary(eventId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (version: number) =>
      unwrap(
        api.POST("/api/v1/events/{event_id}/summary:regenerate", {
          params: { path: { event_id: eventId } },
          headers: { "If-Match": `"${version}"` },
        }),
      ),
    onSuccess: (d) => qc.setQueryData(eventKeys.detail(eventId), d),
  });
}
