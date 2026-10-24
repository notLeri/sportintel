import { useInfiniteQuery } from "@tanstack/react-query";

import { eventKeys, fetchEventsPage, type EventsQueryParams } from "@/entities/event";

export const PAGE_SIZE = 50;

export function useEventsInfinite(params: EventsQueryParams, enabled = true) {
  return useInfiniteQuery({
    queryKey: eventKeys.list(params),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => fetchEventsPage({ ...params, cursor: pageParam, limit: PAGE_SIZE }),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    staleTime: 15_000,
    enabled,
  });
}
