import {
  type InfiniteData,
  type QueryKey,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { type EventDetail, eventKeys, type EventsPage } from "@/entities/event";
import { api, isAppError, unwrap } from "@/shared/api";
import { toast } from "@/shared/ui";

export interface TransitionVars {
  to: string;
  reason?: string | null;
  comment?: string | null;
  version: number;
}

type Snapshot = [QueryKey, unknown][];

function patchLists(
  qc: ReturnType<typeof useQueryClient>,
  id: string,
  patch: (e: { status: string }) => object,
) {
  qc.setQueriesData<InfiniteData<EventsPage>>(
    { queryKey: [...eventKeys.all, "list"] },
    (old) =>
      old && {
        ...old,
        pages: old.pages.map((p) => ({
          ...p,
          items: p.items.map((e) => (e.id === id ? { ...e, ...patch(e) } : e)),
        })),
      },
  );
}

/** Переход статуса с оптимистичным обновлением всех списков и деталей (FE-T3.3 §7, §22). */
export function useTransition(eventId: string) {
  const qc = useQueryClient();
  const { t } = useTranslation(["event", "errors"]);
  return useMutation({
    mutationFn: ({ to, reason, comment, version }: TransitionVars) =>
      unwrap(
        api.POST("/api/v1/events/{event_id}/transitions", {
          params: { path: { event_id: eventId } },
          body: { to, reason: reason ?? null, comment: comment ?? null },
          headers: { "If-Match": `"${version}"` },
        }),
      ),
    onMutate: async ({ to }): Promise<Snapshot> => {
      await qc.cancelQueries({ queryKey: eventKeys.all });
      const snap = qc.getQueriesData({ queryKey: eventKeys.all });
      qc.setQueryData<EventDetail>(
        eventKeys.detail(eventId),
        (old) => old && { ...old, status: to },
      );
      patchLists(qc, eventId, () => ({ status: to }));
      return snap;
    },
    onError: (err, _vars, snap) => {
      for (const [key, data] of snap ?? []) qc.setQueryData(key, data);
      if (isAppError(err) && err.status === 412) {
        void qc.invalidateQueries({ queryKey: eventKeys.detail(eventId) });
        toast.error(t("workflow.conflict"));
      } else {
        const code = isAppError(err) ? err.code : "common.internal";
        toast.error(t(`errors:${code}`, { defaultValue: t("errors:common.internal") }));
      }
    },
    onSuccess: (detail) => {
      qc.setQueryData(eventKeys.detail(eventId), detail);
      patchLists(qc, eventId, () => detail);
    },
  });
}
