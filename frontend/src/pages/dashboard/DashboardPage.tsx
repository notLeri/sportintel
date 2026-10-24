import { type InfiniteData, useQueryClient } from "@tanstack/react-query";
import { ArrowLeftIcon, SlidersHorizontalIcon, XIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { eventKeys, type EventsPage } from "@/entities/event";
import { useMe } from "@/entities/user";
import {
  activeFiltersCount,
  FiltersPanel,
  periodError,
  toApiFilters,
  useDashboardSearch,
  usePersistedFilters,
} from "@/features/event-filters";
import { EventDetails } from "@/features/event-details";
import { BriefPanel } from "@/features/event-brief";
import { EventList } from "@/features/event-list";
import {
  EditButton,
  EditEventForm,
  MergeButton,
  MoveArticleMenu,
  OverrideAssessmentPopover,
  UpdatesSinceEditBanner,
} from "@/features/event-edit";
import { HistoryTab } from "@/features/event-history";
import { WorkflowActions } from "@/features/event-workflow";
import { DraftPanel } from "@/features/telegram-draft";
import { SearchBox } from "@/features/event-search";
import { CreateEventDialog } from "@/features/manual-ingest";
import { cn } from "@/shared/lib/utils";
import { Button, Hint } from "@/shared/ui";

export function DashboardPage() {
  const { t } = useTranslation(["common", "event", "dashboard", "hints"]);
  const me = useMe();
  const { search, set, reset } = useDashboardSearch();
  usePersistedFilters(me.id);
  // Режим правки привязан к событию: смена события его закрывает.
  const [editingId, setEditingId] = useState<string | undefined>();
  const [showFilters, setShowFilters] = useState(false);
  useEffect(() => {
    if (!showFilters) return;
    const onKey = (k: KeyboardEvent) => k.key === "Escape" && setShowFilters(false);
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [showFilters]);
  const editing = editingId !== undefined && editingId === search.event;
  const setEditing = (on: boolean) => setEditingId(on ? search.event : undefined);
  const filters = { ...search, event: undefined };
  const key = JSON.stringify(filters);
  // eslint-disable-next-line react-hooks/exhaustive-deps -- ключ — сериализованные фильтры; окно периода фиксируется при их смене
  const params = useMemo(() => toApiFilters(filters, new Date()), [key]);
  const blocked = periodError(search) || params.relevance?.length === 0;
  const selectEvent = (id: string | undefined) => set({ event: id });
  const qc = useQueryClient();
  // После отклонения выбор переходит на следующее событие списка (как j, FE-T3.3 §12).
  const selectNext = () => {
    const items =
      qc
        .getQueryData<InfiniteData<EventsPage>>(eventKeys.list(params))
        ?.pages.flatMap((p) => p.items) ?? [];
    const i = items.findIndex((x) => x.id === search.event);
    selectEvent(items[i + 1]?.id ?? items[i - 1]?.id);
  };
  const filtersCount = activeFiltersCount(search);
  return (
    // Пока событие не открыто, список занимает всю ширину; открытое событие — справа.
    <div
      data-fill-screen
      className={cn(
        "grid h-full",
        search.event
          ? "md:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] xl:grid-cols-[15.5rem_minmax(0,1fr)_minmax(0,1.15fr)]"
          : "xl:grid-cols-[15.5rem_minmax(0,1fr)]",
      )}
    >
      <h1 className="sr-only">{t("nav.events")}</h1>
      <div
        id="filters-panel"
        className={cn(
          "overflow-auto border-r px-4 py-5 max-xl:hidden xl:block",
          showFilters &&
            "max-xl:bg-background max-xl:fixed max-xl:inset-0 max-xl:z-50 max-xl:block max-md:top-16 md:max-xl:left-22 md:max-xl:w-80 md:max-xl:border-r md:max-xl:shadow-float",
        )}
      >
        {showFilters ? (
          <Button
            variant="outline"
            size="sm"
            className="mb-4 xl:hidden"
            onClick={() => setShowFilters(false)}
          >
            <XIcon aria-hidden />
            {t("common:close")}
          </Button>
        ) : null}
        <FiltersPanel timeZone={me.timezone} />
      </div>
      <section
        aria-label={t("nav.events")}
        className={cn("flex min-h-0 flex-col md:border-r", search.event && "max-md:hidden")}
      >
        <div className="flex items-start gap-2 px-3 py-3">
          <div className="min-w-0 flex-1">
            <SearchBox hotkeys={me.hotkeys_enabled} />
          </div>
          <Hint text={t("hints:filters_toggle")}>
            <Button
              variant="outline"
              size="icon"
              className="relative xl:hidden"
              aria-expanded={showFilters}
              aria-controls="filters-panel"
              aria-label={t("dashboard:filters_title")}
              onClick={() => setShowFilters((v) => !v)}
            >
              <SlidersHorizontalIcon aria-hidden />
              {filtersCount ? (
                <span className="bg-attention text-attention-foreground absolute -top-1.5 -right-1.5 min-w-4 px-0.5 text-[10px] font-bold">
                  {filtersCount}
                </span>
              ) : null}
            </Button>
          </Hint>
          <CreateEventDialog onCreated={(id) => selectEvent(id)} />
        </div>
        <EventList
          params={params}
          enabled={!blocked}
          hotkeys={me.hotkeys_enabled}
          onClearFilters={reset}
          onOpenDetails={() => document.getElementById("event-title")?.focus()}
        />
      </section>
      {search.event ? (
        <div className="min-h-0 overflow-auto">
          <Button
            variant="ghost"
            size="sm"
            className="m-2 md:hidden"
            onClick={() => selectEvent(undefined)}
          >
            <ArrowLeftIcon aria-hidden />
            {t("dashboard:list_label")}
          </Button>
          <EventDetails
            key={search.event}
            eventId={search.event}
            timeZone={me.timezone}
            onClose={() => selectEvent(undefined)}
            slots={{
              actions: (e) => (
                <>
                  <EditButton onClick={() => setEditing(true)} />
                  <MergeButton event={e} />
                  <WorkflowActions event={e} onRejected={selectNext} />
                </>
              ),
              articleAction: (e, a) => <MoveArticleMenu event={e} article={a} />,
              relevanceAction: (e) => <OverrideAssessmentPopover event={e} kind="relevance" />,
              reliabilityAction: (e) => <OverrideAssessmentPopover event={e} kind="reliability" />,
              edit: (e) =>
                editing ? (
                  <EditEventForm event={e} onDone={() => setEditing(false)} />
                ) : (
                  <UpdatesSinceEditBanner event={e} />
                ),
              history: (e) => <HistoryTab eventId={e.id} timeZone={me.timezone} />,
              brief: (e) => <BriefPanel event={e} />,
              draft: (e) => <DraftPanel event={e} timeZone={me.timezone} />,
            }}
            onSelectEvent={selectEvent}
            onAddEntity={(id) => set({ entity: [...new Set([...(search.entity ?? []), id])] })}
          />
        </div>
      ) : null}
    </div>
  );
}
