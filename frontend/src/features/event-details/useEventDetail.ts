import { useQuery } from "@tanstack/react-query";

import { eventDetailQuery } from "@/entities/event";

// ponytail: опрос, пока сервер переводит открытое событие; ~4 мин — дальше перевод, видимо, упал
const POLL_MS = 4000;
const POLL_MAX = 60;

export function useEventDetail(id: string) {
  return useQuery({
    ...eventDetailQuery(id),
    refetchInterval: (q) =>
      q.state.data?.translation_pending && q.state.dataUpdateCount < POLL_MAX ? POLL_MS : false,
  });
}
