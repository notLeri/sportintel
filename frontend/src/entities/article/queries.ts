import { useInfiniteQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/shared/api";

import type { ArticleFilters } from "./types";

export const articleKeys = {
  all: ["articles"] as const,
  list: (f: ArticleFilters) => [...articleKeys.all, "list", f] as const,
  detail: (id: string) => [...articleKeys.all, "detail", id] as const,
};

export function useArticlesInfinite(filters: ArticleFilters) {
  return useInfiniteQuery({
    queryKey: articleKeys.list(filters),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/articles", {
          params: {
            query: {
              source: filters.source.length ? filters.source : undefined,
              state: filters.state.length ? filters.state : undefined,
              from: filters.from,
              to: filters.to,
              q: filters.q,
              cursor: pageParam,
              limit: 50,
            },
          },
        }),
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
}
