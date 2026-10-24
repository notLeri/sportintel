import { useInfiniteQuery } from "@tanstack/react-query";

import { api, unwrap } from "@/shared/api";

import type { FeedFilters, FeedTab } from "./types";

export const feedKeys = {
  all: ["feed"] as const,
  list: (tab: FeedTab, f: FeedFilters) => [...feedKeys.all, tab, f] as const,
};

export function useFeed(tab: FeedTab, filters: FeedFilters) {
  return useInfiniteQuery({
    queryKey: feedKeys.list(tab, filters),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/feed", {
          params: {
            query: {
              tab,
              ...filters,
              cursor: pageParam,
              limit: 20,
            },
          },
        }),
      ),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    staleTime: 15_000,
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
  });
}
