import { useInfiniteQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useMe } from "@/entities/user";
import { api, unwrap } from "@/shared/api";
import { formatDateTime } from "@/shared/lib/datetime";
import { Button } from "@/shared/ui";

import { describeAction } from "./describeAction";

const historyKeys = { event: (id: string) => ["audit", "event", id] as const };

/** «Histórico» события (FE-T4.7); виден с правом audit.read. */
export function HistoryTab({ eventId, timeZone }: { eventId: string; timeZone: string }) {
  const { t } = useTranslation(["event", "enums"]);
  const me = useMe();
  const allowed = me.permissions.includes("audit.read");
  const q = useInfiniteQuery({
    queryKey: historyKeys.event(eventId),
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) =>
      unwrap(
        api.GET("/api/v1/audit", {
          params: { query: { event_id: eventId, cursor: pageParam, limit: 50 } },
        }),
      ),
    getNextPageParam: (p) => p.next_cursor ?? undefined,
    enabled: allowed,
  });
  if (!allowed) return null;
  const items = q.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <section aria-labelledby="history-h" className="space-y-2 border-t pt-4">
      <h3 id="history-h" className="font-medium">
        {t("history.title")}
      </h3>
      {q.isPending ? <p aria-busy="true">…</p> : null}
      <ol className="space-y-1 text-sm">
        {items.map((e) => (
          <li key={e.id} className="flex gap-2">
            <time className="text-muted-foreground shrink-0 text-xs" dateTime={e.at}>
              {formatDateTime(e.at, timeZone)}
            </time>
            <span>{describeAction(e, t)}</span>
          </li>
        ))}
      </ol>
      {q.hasNextPage ? (
        <Button
          size="sm"
          variant="outline"
          disabled={q.isFetchingNextPage}
          onClick={() => void q.fetchNextPage()}
        >
          {t("history.more")}
        </Button>
      ) : null}
    </section>
  );
}
