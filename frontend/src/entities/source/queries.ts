import { queryOptions, useQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/shared/api";

export const sourceKeys = {
  all: ["sources"] as const,
  brief: () => [...sourceKeys.all, "brief"] as const,
};

export const sourcesBriefQuery = queryOptions({
  queryKey: sourceKeys.brief(),
  queryFn: async () =>
    (await unwrap(api.GET("/api/v1/sources", { params: { query: { view: "brief" } } }))).items,
  staleTime: 10 * 60_000,
});

export function useSourcesBrief() {
  return useQuery(sourcesBriefQuery);
}
