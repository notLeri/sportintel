import { memo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { AiEventStatus, AiWait } from "@/entities/ai";
import { TelegramPreview } from "@/entities/draft";
import { RelevanceBadge, ReliabilityBadge, StatusChip } from "@/entities/event";
import type { FeedItem, FeedPage } from "@/entities/feed";
import { useSportName } from "@/entities/taxonomy";
import { DisclaimerBlock } from "@/features/telegram-draft";
import { formatRelative } from "@/shared/lib/datetime";
import { cn } from "@/shared/lib/utils";
import { Badge, Button, Hint } from "@/shared/ui";

export interface FeedActions {
  onApprove?: (item: FeedItem) => void;
  onPrepare?: (item: FeedItem) => void;
  onSchedule?: (item: FeedItem) => void;
  onReject?: (item: FeedItem) => void;
  onCopy?: (item: FeedItem) => void;
  onOpen: (item: FeedItem) => void;
  onPublish?: (item: FeedItem) => void;
}

function Message({
  item,
  posinset,
  setsize,
  selected,
  channelName,
  channels,
  actions,
  preparing,
  aiWrites,
  approving,
  scheduleForm,
  onFocus,
}: {
  item: FeedItem;
  posinset: number;
  setsize: number;
  selected: boolean;
  channelName: string;
  channels: FeedPage["channels"];
  actions: FeedActions;
  preparing: boolean;
  /** «Переписать» пишет ИИ (а не шаблон) — показываем, сколько ждать. */
  aiWrites: boolean;
  approving: boolean;
  scheduleForm: ReactNode;
  onFocus: () => void;
}) {
  const { t, i18n } = useTranslation(["feed", "dashboard", "hints"]);
  const sportName = useSportName();
  const e = item.event;
  const d = item.draft;
  // пост не на языке ни одного канала — запланировать его нельзя, только подготовить заново
  const wrongLang = Boolean(d && channels.length && !channels.some((c) => c.language === d.lang));
  // одобрить можно сам первый вариант — правки нужны, только если он не удался
  const approvable = Boolean(d?.body_tg_html.trim() && !wrongLang && e.status !== "READY");
  const canSchedule = Boolean(actions.onSchedule && d?.body_tg_html.trim() && !wrongLang);
  return (
    <article
      aria-labelledby={`feed-title-${e.id}`}
      aria-posinset={posinset}
      aria-setsize={setsize}
      data-testid={`feed-message-${e.id}`}
      // ARIA feed pattern: статьи ленты фокусируемы (навигация j/k)
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex
      tabIndex={0}
      onFocus={onFocus}
      className={cn(
        "space-y-2 rounded-lg border p-3 outline-none",
        selected && "ring-primary ring-2",
      )}
    >
      <h2 id={`feed-title-${e.id}`} className="font-medium">
        {item.title}
      </h2>
      {item.summary && !d ? (
        <p className="text-muted-foreground line-clamp-4 text-sm">{item.summary}</p>
      ) : null}
      <div className="flex flex-wrap items-center gap-1 text-xs">
        {e.sport_id ? <Badge variant="outline">{sportName(e.sport_id)}</Badge> : null}
        <RelevanceBadge level={e.relevance} />
        <ReliabilityBadge level={e.reliability} />
        {e.status !== "NEW" ? <StatusChip status={e.status} /> : null}
        <span className="text-muted-foreground">
          {formatRelative(e.last_article_at, new Date(), i18n.language)}
        </span>
      </div>
      {item.sources.length ? (
        <p className="text-muted-foreground text-xs">
          {t("dashboard:sources", { count: e.source_count })}:{" "}
          {item.sources.slice(0, 5).map((s, i) => (
            <span key={s.url}>
              {i ? ", " : ""}
              <a href={s.url} target="_blank" rel="noreferrer" className="hover:underline">
                {s.name}
              </a>
            </span>
          ))}
        </p>
      ) : null}
      {d ? (
        <div className="space-y-1">
          <div className="flex items-center justify-between gap-2 text-xs">
            <span className="text-muted-foreground">
              {t("post_for", { lang: d.lang })} ·{" "}
              {d.origin === "ai"
                ? t("origin.llm")
                : d.origin === "human"
                  ? t("origin.human")
                  : t("origin.template")}
            </span>
          </div>
          <DisclaimerBlock text={d.disclaimer_text ?? null} />
          <TelegramPreview
            tgHtml={d.body_tg_html}
            imageUrl={d.image_url ?? null}
            channelName={channelName}
          />
          {wrongLang ? (
            <p className="text-warn text-xs">
              {t("wrong_lang", {
                lang: d.lang,
                channels: channels.map((c) => `${c.name} (${c.language})`).join(", "),
              })}
            </p>
          ) : null}
        </div>
      ) : null}
      {preparing ? (
        <AiWait kind="rewrite" active={aiWrites} />
      ) : (
        <AiEventStatus eventId={e.id} kinds={["post", "rewrite"]} />
      )}
      <div className="flex flex-wrap gap-1">
        {actions.onApprove && approvable ? (
          <Hint text={t("hints:feed.approve")}>
            <Button
              size="sm"
              aria-keyshortcuts="a"
              disabled={approving}
              onClick={() => actions.onApprove?.(item)}
            >
              {t("approve")}
            </Button>
          </Hint>
        ) : null}
        {canSchedule ? (
          <Hint text={t("hints:feed.schedule")}>
            <Button
              size="sm"
              variant="outline"
              aria-keyshortcuts="s"
              onClick={() => actions.onSchedule?.(item)}
            >
              {t("schedule")}
            </Button>
          </Hint>
        ) : null}
        {actions.onPrepare ? (
          <Hint text={t(d ? "hints:feed.rewrite" : "hints:feed.prepare")}>
            <Button
              size="sm"
              variant={d && !wrongLang ? "outline" : "default"}
              aria-keyshortcuts="p"
              disabled={preparing}
              onClick={() => actions.onPrepare?.(item)}
            >
              {preparing ? t("preparing") : d ? t("rewrite") : t("prepare")}
            </Button>
          </Hint>
        ) : null}
        {actions.onPublish && e.status === "READY" ? (
          <Hint text={t("hints:feed.publish")}>
            <Button size="sm" onClick={() => actions.onPublish?.(item)}>
              {t("publish")}
            </Button>
          </Hint>
        ) : null}
        {actions.onCopy ? (
          <Hint text={t("hints:draft.copy")}>
            <Button
              size="sm"
              variant="outline"
              aria-keyshortcuts="c"
              disabled={!d}
              onClick={() => actions.onCopy?.(item)}
            >
              {t("common:telegram.copy")}
            </Button>
          </Hint>
        ) : null}
        <Hint text={t("hints:feed.edit")}>
          <Button
            size="sm"
            variant="ghost"
            aria-keyshortcuts="Enter"
            onClick={() => actions.onOpen(item)}
          >
            {t("edit")}
          </Button>
        </Hint>
        {actions.onReject ? (
          <Hint text={t("hints:feed.reject")}>
            <Button
              size="sm"
              variant="ghost"
              aria-keyshortcuts="r"
              onClick={() => actions.onReject?.(item)}
            >
              {t("reject")}
            </Button>
          </Hint>
        ) : null}
      </div>
      {scheduleForm}
    </article>
  );
}

export const FeedMessage = memo(Message);
