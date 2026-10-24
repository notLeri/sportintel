import { queryOptions } from "@tanstack/react-query";

import { api, unwrap } from "@/shared/api";

import type { EventsPage, EventsQueryParams } from "./types";

export const eventKeys = {
  all: ["events"] as const,
  list: (p: EventsQueryParams) => [...eventKeys.all, "list", p] as const,
  updates: (p: EventsQueryParams) => [...eventKeys.all, "updates", p] as const,
  detail: (id: string) => [...eventKeys.all, "detail", id] as const,
};

/** Страница списка + X-Server-Time (следующий updated_since для polling, BE-T2.21). */
export async function fetchEventsPage(query: EventsQueryParams): Promise<EventsPage> {
  let serverTime: string | null = null;
  const data = await unwrap(
    api.GET("/api/v1/events", { params: { query } }).then((r) => {
      serverTime = r.response.headers.get("X-Server-Time");
      return r;
    }),
  );
  return { ...data, serverTime };
}

export const eventDetailQuery = (id: string) =>
  queryOptions({
    queryKey: eventKeys.detail(id),
    staleTime: 10_000,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/events/{event_id}", {
          params: {
            path: { event_id: id },
            query: { include: ["articles", "related", "draft", "conflicts"] },
          },
        }),
      ),
  });
