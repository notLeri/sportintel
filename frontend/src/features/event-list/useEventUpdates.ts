import { type InfiniteData, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  eventKeys,
  fetchEventsPage,
  type EventsPage,
  type EventsQueryParams,
} from "@/entities/event";

export const POLL_MS = 30_000;
export const UPDATES_LIMIT = 100;
// Дольше анимации (задержка + 1.8s подсветки) с запасом на ответ сервера после applyNew.
const FRESH_MS = 4000;

/**
 * Polling `updated_since` (FE-T2.26 §7): известные события обновляются в кэше списка,
 * новые копятся в pendingNew и вставляются только по applyNew() — список не «прыгает».
 */
export function useEventUpdates(params: EventsQueryParams, enabled: boolean, onApply?: () => void) {
  const qc = useQueryClient();
  const listKey = eventKeys.list(params);
  const list = qc.getQueryData<InfiniteData<EventsPage>>(listKey);
  const firstServerTime = list?.pages[0]?.serverTime ?? null;
  const since = useRef<string | null>(null);
  const [pending, setPending] = useState<Set<string>>(new Set());
  const [overflow, setOverflow] = useState(false);
  // Только что вставленные по applyNew() — строки играют анимацию появления, потом набор очищается.
  const [fresh, setFresh] = useState<ReadonlySet<string>>(new Set());
  const pendingRef = useRef(pending);
  pendingRef.current = pending;

  useEffect(() => {
    if (!fresh.size) return;
    const id = setTimeout(() => setFresh(new Set()), FRESH_MS);
    return () => clearTimeout(id);
  }, [fresh]);

  useEffect(() => {
    since.current = firstServerTime; // новая выборка или перезагрузка — заново от её времени
    setPending(new Set());
    setOverflow(false);
  }, [firstServerTime]);

  useQuery({
    queryKey: eventKeys.updates(params),
    enabled: enabled && firstServerTime !== null,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: false,
    staleTime: POLL_MS,
    queryFn: async () => {
      if (document.visibilityState !== "visible" || !since.current) return null;
      const page = await fetchEventsPage({
        ...params,
        updated_since: since.current,
        limit: UPDATES_LIMIT,
      });
      const fresh = new Map(page.items.map((e) => [e.id, e]));
      const known = new Set<string>();
      qc.setQueryData<InfiniteData<EventsPage>>(
        listKey,
        (old) =>
          old && {
            ...old,
            pages: old.pages.map((p) => ({
              ...p,
              items: p.items.map((e) => {
                const upd = fresh.get(e.id);
                if (!upd) return e;
                known.add(e.id);
                return upd;
              }),
            })),
          },
      );
      const added = page.items.filter((e) => !known.has(e.id)).map((e) => e.id);
      if (added.length) setPending((prev) => new Set([...prev, ...added]));
      if (page.items.length >= UPDATES_LIMIT) setOverflow(true);
      since.current = page.serverTime ?? since.current;
      return page.serverTime;
    },
  });

  const applyNew = useCallback(() => {
    setFresh(pendingRef.current);
    setPending(new Set());
    setOverflow(false);
    void qc.invalidateQueries({ queryKey: listKey, exact: true });
    onApply?.();
  }, [qc, listKey, onApply]);

  return { newCount: pending.size, overflow, applyNew, fresh };
}
