import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { AiQueuePanel, useAiProgress } from "@/entities/ai";
import { type FeedFilters, type FeedItem, feedKeys, useFeed } from "@/entities/feed";
import { useMe, useSystemStatus } from "@/entities/user";
import { activeFiltersCount, FiltersPanel, usePersistedFilters } from "@/features/event-filters";
import { RejectDialog, useTransition } from "@/features/event-workflow";
import { usePreparePost } from "@/features/feed-take";
import { useApprovePost, useCopyPost } from "@/features/telegram-draft";
import { isAppError } from "@/shared/api";
import { useHotkey } from "@/shared/lib/hotkeys";
import { cn } from "@/shared/lib/utils";
import type { FeedSearch } from "@/shared/routing";
import { Button, Hint, Skeleton, toast } from "@/shared/ui";

import { FeedMessage } from "./FeedMessage";
import { FeedSchedule } from "./FeedSchedule";

const route = getRouteApi("/feed");

/** Фильтры адреса → query GET /feed (те же условия, что у списка событий). */
function toFeedFilters(s: FeedSearch): FeedFilters {
  return {
    sport: s.sport,
    region: s.region,
    competition: s.competition,
    relevance: s.relevance,
    reliability: s.reliability,
    source: s.source,
    source_exclude: s.xsource,
    entity: s.entity,
    conflicts: s.conflicts === "1" ? true : undefined,
  };
}

/** Действие, требующее событие: хук перехода привязан к событию, поэтому — отдельный компонент. */
function RejectFor({ item, onDone }: { item: FeedItem; onDone: () => void }) {
  const tr = useTransition(item.event.id);
  return (
    <RejectDialog
      open
      onOpenChange={(o) => !o && onDone()}
      onConfirm={(reason, comment) => {
        tr.mutate({ to: "REJECTED", reason, comment, version: item.event.version });
        onDone();
      }}
    />
  );
}

function PublishFor({ item, onDone }: { item: FeedItem; onDone: () => void }) {
  const tr = useTransition(item.event.id);
  const { t } = useTranslation("feed");
  return (
    <div
      role="alertdialog"
      aria-label={t("publish")}
      className="bg-popover fixed right-4 bottom-4 z-30 space-x-2 rounded-md border p-3 shadow"
    >
      <span>{t("publish_confirm")}</span>
      <Button
        size="sm"
        onClick={() => {
          tr.mutate({ to: "PUBLISHED", version: item.event.version });
          onDone();
        }}
      >
        {t("publish")}
      </Button>
      <Button size="sm" variant="ghost" onClick={onDone}>
        {t("cancel")}
      </Button>
    </div>
  );
}

export function FeedPage() {
  const { t } = useTranslation(["feed", "common", "hints", "dashboard"]);
  const me = useMe();
  const search = route.useSearch();
  const routeNavigate = route.useNavigate();
  const navigate = useNavigate();
  const tab = search.tab ?? "suggested";
  usePersistedFilters(me.id, "feed");
  const [showFilters, setShowFilters] = useState(false);
  const feed = useFeed(tab, toFeedFilters(search));
  const items = feed.data?.pages.flatMap((p) => p.items) ?? [];
  const channels = feed.data?.pages[0]?.channels ?? [];
  const prepare = usePreparePost();
  // ИИ дописал пост в фоне — лента обновляется сразу, а не через минуту
  const qc = useQueryClient();
  const aiDone = useAiProgress().data?.queues.find((q) => q.kind === "post")?.done_24h;
  useEffect(() => {
    if (aiDone !== undefined) void qc.invalidateQueries({ queryKey: feedKeys.all });
  }, [aiDone, qc]);
  const approve = useApprovePost();
  // ИИ пишет пост, если модель подключена; иначе — шаблон
  const mode = useSystemStatus()?.ai.llm.available ? "llm" : "template";
  const [preparing, setPreparing] = useState<ReadonlySet<string>>(new Set());
  const [scheduling, setScheduling] = useState<string | null>(null);
  const { copy, fallback } = useCopyPost();
  const [active, setActive] = useState(0);
  const [rejecting, setRejecting] = useState<FeedItem | null>(null);
  const [publishing, setPublishing] = useState<FeedItem | null>(null);
  const canTransition = me.permissions.includes("events.transition");
  const canWrite = me.permissions.includes("drafts.write");
  const canApprove = (me.allowed_transitions.DRAFT ?? []).some((o) => o.to === "READY");
  const canPublish = (me.allowed_transitions.READY ?? []).some((o) => o.to === "PUBLISHED");

  const open = (i: FeedItem) =>
    void navigate({ to: "/events/$eventId", params: { eventId: i.event.id } });
  const doCopy = (i: FeedItem) =>
    i.draft &&
    copy({
      draftId: i.draft.id,
      versionN: i.draft.version_n,
      tgHtml: i.draft.body_tg_html,
    });
  const doPrepare = (i: FeedItem) => {
    const id = i.event.id;
    setPreparing((s) => new Set(s).add(id));
    prepare.mutate(
      { eventId: id, version: i.event.version, mode },
      {
        onError: (e) =>
          toast.error(
            isAppError(e) && e.status === 412
              ? t("changed")
              : isAppError(e)
                ? (e.fieldErrors[0]?.message ?? e.title)
                : t("prepare_failed"),
          ),
        onSettled: () =>
          setPreparing((s) => {
            const n = new Set(s);
            n.delete(id);
            return n;
          }),
      },
    );
  };
  const errorToast = (e: unknown) =>
    toast.error(
      isAppError(e) && e.status === 412
        ? t("changed")
        : isAppError(e)
          ? (e.fieldErrors[0]?.message ?? e.title)
          : t("approve_failed"),
    );
  const doApprove = (i: FeedItem) =>
    approve.mutate(
      { eventId: i.event.id, version: i.event.version },
      { onSuccess: () => toast.success(t("approved")), onError: errorToast },
    );
  const actions =
    tab === "suggested"
      ? {
          onApprove: canApprove ? doApprove : undefined,
          onPrepare: canWrite ? doPrepare : undefined,
          onSchedule:
            canApprove && channels.length ? (i: FeedItem) => setScheduling(i.event.id) : undefined,
          onReject: canTransition ? setRejecting : undefined,
          onOpen: open,
        }
      : { onCopy: doCopy, onOpen: open, onPublish: canPublish ? setPublishing : undefined };

  const focusAt = (i: number) => {
    const next = Math.min(items.length - 1, Math.max(0, i));
    setActive(next);
    document
      .querySelector<HTMLElement>(`[data-testid="feed-message-${items[next]?.event.id}"]`)
      ?.focus();
  };
  const hot = { enabled: me.hotkeys_enabled && !rejecting && !scheduling };
  const cur = items[active];
  useHotkey("j", () => focusAt(active + 1), hot);
  useHotkey("k", () => focusAt(active - 1), hot);
  useHotkey("a", () => cur && actions.onApprove?.(cur), hot);
  useHotkey("p", () => cur && actions.onPrepare?.(cur), hot);
  useHotkey("s", () => cur && actions.onSchedule?.(cur), hot);
  useHotkey("r", () => cur && actions.onReject?.(cur), hot);
  useHotkey("c", () => cur && actions.onCopy?.(cur), hot);
  useHotkey("Enter", () => cur && open(cur), hot);

  return (
    <div className="xl:grid xl:grid-cols-[15.5rem_minmax(0,1fr)]">
      <div
        id="feed-filters"
        className={cn("px-4 py-5 xl:block xl:border-r", showFilters ? "border-b" : "max-xl:hidden")}
      >
        <FiltersPanel timeZone={me.timezone} scope="feed" />
      </div>
      <section className="mx-auto w-full max-w-2xl space-y-4 p-4" aria-labelledby="feed-h">
        <header className="flex flex-wrap items-center justify-between gap-2">
          <h1 id="feed-h" className="font-display text-2xl font-bold">
            {t("common:nav.feed")}
          </h1>
          <Button
            size="sm"
            variant="outline"
            className="xl:hidden"
            aria-expanded={showFilters}
            aria-controls="feed-filters"
            onClick={() => setShowFilters((x) => !x)}
          >
            {t("dashboard:filters_title")}
            {activeFiltersCount(search) ? ` (${activeFiltersCount(search)})` : ""}
          </Button>
          <div role="tablist" aria-label={t("tabs")} className="flex gap-1">
            {(["suggested", "channel"] as const).map((x) => (
              <Hint key={x} text={t(`hints:feed.${x}`)}>
                <Button
                  role="tab"
                  size="sm"
                  aria-selected={tab === x}
                  variant={tab === x ? "default" : "outline"}
                  onClick={() =>
                    void routeNavigate({
                      search: (p) => ({ ...p, tab: x === "suggested" ? undefined : x }),
                      replace: true,
                    })
                  }
                >
                  {t(`tab.${x}`)}
                </Button>
              </Hint>
            ))}
          </div>
        </header>
        {tab === "suggested" ? <AiQueuePanel kinds={["post", "rewrite", "translate"]} /> : null}
        {feed.isPending ? (
          <div className="space-y-3" aria-busy="true">
            {Array.from({ length: 3 }, (_, i) => (
              <Skeleton key={i} className="h-48 w-full" />
            ))}
          </div>
        ) : feed.isError ? (
          <div role="alert" className="space-y-2">
            <p>{t("load_failed")}</p>
            <Button variant="outline" onClick={() => void feed.refetch()}>
              {t("common:retry")}
            </Button>
          </div>
        ) : items.length === 0 ? (
          <div className="text-muted-foreground space-y-1">
            <p className="font-medium">{tab === "suggested" ? t("empty") : t("empty_channel")}</p>
            {tab === "suggested" ? <p className="text-sm">{t("empty_hint")}</p> : null}
          </div>
        ) : (
          // ponytail: без виртуализации — страницы по 20 и «Carregar mais»; react-virtual, если ленты станут длинными.
          <div
            role="feed"
            aria-busy={feed.isFetchingNextPage}
            aria-label={t(`tab.${tab}`)}
            className="space-y-4"
          >
            {items.map((item, i) => (
              <FeedMessage
                key={item.event.id}
                item={item}
                posinset={i + 1}
                setsize={feed.hasNextPage ? -1 : items.length}
                selected={i === active}
                channelName={channels[0]?.name ?? t("channel_name")}
                channels={channels}
                actions={actions}
                preparing={preparing.has(item.event.id)}
                aiWrites={mode === "llm"}
                approving={approve.isPending && approve.variables?.eventId === item.event.id}
                scheduleForm={
                  scheduling === item.event.id ? (
                    <FeedSchedule
                      item={item}
                      channels={channels}
                      timeZone={me.timezone}
                      onDone={() => setScheduling(null)}
                    />
                  ) : null
                }
                onFocus={() => setActive(i)}
              />
            ))}
            {feed.hasNextPage ? (
              <Button
                variant="outline"
                className="w-full"
                disabled={feed.isFetchingNextPage}
                onClick={() => void feed.fetchNextPage()}
              >
                {t("more")}
              </Button>
            ) : null}
          </div>
        )}
        {rejecting ? <RejectFor item={rejecting} onDone={() => setRejecting(null)} /> : null}
        {publishing ? <PublishFor item={publishing} onDone={() => setPublishing(null)} /> : null}
        {fallback}
      </section>
    </div>
  );
}
