import { queryOptions } from "@tanstack/react-query";

import { api, unwrap } from "@/shared/api";

export const draftKeys = {
  all: ["drafts"] as const,
  detail: (id: string) => [...draftKeys.all, id] as const,
  version: (id: string, n: number) => [...draftKeys.all, id, "v", n] as const,
};

/** Опрос только пока идёт генерация; при размонтировании TanStack останавливает его сам (§22). */
export const draftQuery = (id: string) =>
  queryOptions({
    queryKey: draftKeys.detail(id),
    staleTime: 10_000,
    queryFn: () =>
      unwrap(api.GET("/api/v1/drafts/{draft_id}", { params: { path: { draft_id: id } } })),
    refetchInterval: (q) => (q.state.data?.state === "generating" ? 1500 : false),
  });

export const draftVersionQuery = (id: string, n: number) =>
  queryOptions({
    queryKey: draftKeys.version(id, n),
    staleTime: Infinity, // версии неизменяемы
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/drafts/{draft_id}/versions/{n}", {
          params: { path: { draft_id: id, n } },
        }),
      ),
  });
