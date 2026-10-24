import { useQueryClient } from "@tanstack/react-query";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useCallback, useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";
import { ArrowUpIcon } from "lucide-react";

import { eventDetailQuery, type EventsQueryParams } from "@/entities/event";
import { useHotkey } from "@/shared/lib/hotkeys";
import { useMediaQuery } from "@/shared/lib/useMediaQuery";
import { Button, Skeleton } from "@/shared/ui";

import { EventRow } from "./EventRow";
import { NARROW_QUERY, ROW_HEIGHT, ROW_HEIGHT_NARROW, rowId } from "./rowMeta";
import { useEventsInfinite } from "./useEventsInfinite";
import { useEventUpdates } from "./useEventUpdates";
import { useSelectedEvent } from "./useSelectedEvent";

export function EventList({
  params,
  enabled = true,
  hotkeys = true,
  onClearFilters,
  onOpenDetails,
}: {
  params: EventsQueryParams;
  enabled?: boolean;
  hotkeys?: boolean;
  onClearFilters: () => void;
  onOpenDetails?: () => void;
}) {
  const { t } = useTranslation("dashboard");
  const qc = useQueryClient();
  const list = useEventsInfinite(params, enabled);
  const items = useMemo(() => list.data?.pages.flatMap((p) => p.items) ?? [], [list.data]);
  const [selected, select] = useSelectedEvent();
  const scrollRef = useRef<HTMLDivElement>(null);
  const rowHeight = useMediaQuery(NARROW_QUERY) ? ROW_HEIGHT_NARROW : ROW_HEIGHT;
  const virtual = useVirtualizer({
    count: items.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => rowHeight,
    overscan: 8,
    initialRect: { width: 600, height: 800 },
  });
  useEffect(() => virtual.measure(), [rowHeight, virtual]);
  const updates = useEventUpdates(params, enabled, () => virtual.scrollToOffset(0));
  const prefetch = useCallback((id: string) => void qc.prefetchQuery(eventDetailQuery(id)), [qc]);

  const vItems = virtual.getVirtualItems();
  const last = vItems[vItems.length - 1];
  useEffect(() => {
    if (
      last &&
      last.index >= items.length - 5 &&
      list.hasNextPage &&
      !list.isFetchingNextPage &&
      !list.isError
    )
      void list.fetchNextPage();
  }, [last, items.length, list]);

  const move = (delta: number) => {
    if (!items.length) return;
    const i = items.findIndex((e) => e.id === selected);
    const next = Math.min(items.length - 1, Math.max(0, i < 0 ? 0 : i + delta));
    virtual.scrollToIndex(next, { align: "auto" }); // строка смонтирована до смены aria-activedescendant
    const target = items[next];
    if (target) select(target.id);
  };
  useHotkey("j", () => move(1), { enabled: hotkeys });
  useHotkey("k", () => move(-1), { enabled: hotkeys });
  useHotkey("Enter", () => selected && onOpenDetails?.(), { enabled: hotkeys });

  if (!enabled) return null;
  if (list.isPending)
    return (
      <div className="space-y-px border-t" aria-busy="true">
        {Array.from({ length: 8 }, (_, i) => (
          <Skeleton key={i} style={{ height: rowHeight - 1 }} className="w-full rounded-none" />
        ))}
      </div>
    );
  if (list.isError && !items.length)
    return (
      <div role="alert" className="space-y-3 border-t px-3 py-8">
        <p>{t("list_failed")}</p>
        <Button variant="outline" onClick={() => void list.refetch()}>
          {t("common:retry")}
        </Button>
      </div>
    );
  if (!items.length)
    return (
      <div className="space-y-3 border-t px-3 py-8">
        <div aria-hidden className="flex gap-1">
          <span className="border-input size-4 rounded-[3px] border-[1.5px]" />
          <span className="border-input size-4 rounded-[3px] border-[1.5px]" />
          <span className="bg-brand size-4 rounded-[3px]" />
        </div>
        <p className="text-muted-foreground max-w-[40ch]">{t("empty")}</p>
        <Button variant="outline" onClick={onClearFilters}>
          {t("clear_filters")}
        </Button>
      </div>
    );

  const inList = items.some((e) => e.id === selected);
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div aria-live="polite" className="min-h-0">
        {updates.newCount > 0 ? (
          <button
            type="button"
            className="enter-drop bg-attention text-attention-foreground hover:bg-attention/85 flex w-full items-center gap-2 px-3 py-2 text-left text-sm font-semibold"
            onClick={updates.applyNew}
          >
            <ArrowUpIcon aria-hidden className="size-4" strokeWidth={2.5} />
            {updates.overflow
              ? t("new_events_overflow")
              : t("new_events", { count: updates.newCount })}
          </button>
        ) : null}
      </div>
      <div
        ref={scrollRef}
        role="listbox"
        aria-label={t("list_label")}
        aria-activedescendant={selected && inList ? rowId(selected) : undefined}
        tabIndex={0}
        className="min-h-0 flex-1 overflow-auto border-t outline-offset-[-2px]"
      >
        <div style={{ height: virtual.getTotalSize(), position: "relative" }}>
          {vItems.map((v) => {
            const e = items[v.index];
            if (!e) return null;
            return (
              <div
                key={e.id}
                className="row-slot"
                style={{
                  position: "absolute",
                  top: 0,
                  left: 0,
                  right: 0,
                  transform: `translateY(${v.start}px)`,
                }}
              >
                <EventRow
                  e={e}
                  selected={e.id === selected}
                  fresh={updates.fresh.has(e.id) ? v.index : undefined}
                  height={rowHeight}
                  onSelect={select}
                  onPrefetch={prefetch}
                />
              </div>
            );
          })}
        </div>
      </div>
      {list.isError && items.length ? (
        <div role="alert" className="flex items-center gap-2 p-2 text-sm">
          {t("next_page_failed")}
          <Button size="sm" variant="outline" onClick={() => void list.fetchNextPage()}>
            {t("common:retry")}
          </Button>
        </div>
      ) : null}
    </div>
  );
}
