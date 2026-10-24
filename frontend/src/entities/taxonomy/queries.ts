import { keepPreviousData, queryOptions, useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/shared/api";

import type { EntityKind } from "./types";

export const taxonomyKeys = {
  all: ["taxonomy"] as const,
  sports: () => [...taxonomyKeys.all, "sports"] as const,
  search: (q: string, kind?: EntityKind) =>
    [...taxonomyKeys.all, "search", q, kind ?? null] as const,
  ids: (ids: string[]) => [...taxonomyKeys.all, "ids", [...ids].sort()] as const,
};

export const sportsQuery = queryOptions({
  queryKey: taxonomyKeys.sports(),
  queryFn: async () => (await unwrap(api.GET("/api/v1/taxonomy/sports"))).items,
  staleTime: 5 * 60_000,
});

export function useSports() {
  return useQuery(sportsQuery);
}

/** id вида спорта → имя на языке пользователя (локализует сервер по me.locale). */
export function useSportName(): (id: string) => string {
  const { data } = useSports();
  return (id) => data?.find((s) => s.id === id)?.name ?? id;
}

/** Автодополнение: от 2 символов (BE-T2.24). */
export function useEntitySearch(q: string, kind?: EntityKind) {
  const term = q.trim();
  return useQuery({
    queryKey: taxonomyKeys.search(term, kind),
    queryFn: async () =>
      (
        await unwrap(
          api.GET("/api/v1/taxonomy/entities", { params: { query: { q: term, kind, limit: 10 } } }),
        )
      ).items,
    enabled: term.length >= 2,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
}

/** Подписи выбранных в URL сущностей. */
export function useEntitiesByIds(ids: string[]) {
  return useQuery({
    queryKey: taxonomyKeys.ids(ids),
    queryFn: async () =>
      (await unwrap(api.GET("/api/v1/taxonomy/entities", { params: { query: { ids } } }))).items,
    enabled: ids.length > 0,
    staleTime: 5 * 60_000,
  });
}
